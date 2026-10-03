import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from visit_workflow import VisitStore
from healthcare_statistics import operational_report, capacity_report, public_annual_report
from healthcare_ml import evaluate_demand, validate_weekly
from lombardia_data import snapshot, verify_snapshot

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
START = NOW + timedelta(days=10)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = VisitStore(Path(self.tmp.name) / 'visits.sqlite3')

    def book(self, patient, **context):
        return self.store.book(patient, 'CARDIO', 'AMB01', START, 30, 'TEST', now=NOW,
                               organisation='ENTE', **context)

    def test_site_independence_and_global_clinician_conflict(self):
        self.book('P1', site='MILANO', clinician='MED1', regime='SSN')
        self.book('P2', site='MONZA', clinician='MED2', regime='ALPI')
        with self.assertRaises(ValueError):
            self.book('P3', site='MONZA', clinician='MED1')
        with self.assertRaises(ValueError):
            self.book('p1', site='COMO')
        visit = self.store.book('P4', 'CARDIO', 'AMB01', START+timedelta(hours=1), 30, 'TEST', now=NOW, organisation='ENTE', site='COMO', clinician='MED1')
        with self.assertRaises(ValueError):
            self.store.reschedule(visit, START, 30, 'TEST', expected_status='prenotata', now=NOW)

    def test_migration_preserves_old_rows_unknown_request(self):
        path = Path(self.tmp.name) / 'legacy.sqlite3'
        with closing(sqlite3.connect(path)) as conn:
            conn.execute('CREATE TABLE visits(id TEXT PRIMARY KEY,patient_code TEXT,service TEXT,resource TEXT,starts_at TEXT,ends_at TEXT,status TEXT,created_at TEXT,executed_at TEXT)')
            conn.execute('INSERT INTO visits VALUES(?,?,?,?,?,?,?,?,?)', ('OLD', 'P', 'S', 'R', START.isoformat(), (START+timedelta(minutes=30)).isoformat(), 'prenotata', NOW.isoformat(), None))
            conn.commit()
        migrated = VisitStore(path)
        row = migrated.list_visits()[0]
        self.assertEqual(row['id'], 'OLD')
        self.assertEqual(row['regime'], 'NON_INDICATO')
        self.assertIsNone(row['requested_at'])
        self.assertEqual(VisitStore(path).list_visits(), migrated.list_visits())

    def test_no_show_denominator_and_missing_wait(self):
        completed = self.book('P1', site='A', regime='SSN', priority='B', access_kind='PRIMO', requested_at=NOW-timedelta(days=2))
        absent = self.book('P2', site='B', regime='ALPI')
        cancelled = self.book('P3', site='C', regime='SSN')
        self.store.change_status(cancelled, 'annullata', 'TEST', expected_status='prenotata', now=NOW)
        self.book('P4', site='D')
        for old, new in [('prenotata', 'confermata'), ('confermata', 'accettata'), ('accettata', 'eseguita')]:
            self.store.change_status(completed, new, 'TEST', expected_status=old, now=START)
        self.store.change_status(absent, 'non_presentato', 'TEST', expected_status='prenotata', now=START)
        report = operational_report(self.store.dataframe(), as_of=START+timedelta(days=1))
        self.assertEqual(report.resolved_due.sum(), 2)
        self.assertEqual(report.no_show.sum(), 1)
        self.assertEqual(report.cancelled.sum(), 1)
        self.assertEqual(report.overdue_unresolved.sum(), 1)
        self.assertEqual(report.missing_request.sum(), 3)
        self.assertEqual(report.wait_observed.sum(), 1)
        self.assertEqual(report.loc[report.site == 'A', 'request_to_current_slot_median_days'].iloc[0], 12)
        self.assertTrue(pd.isna(report.loc[report.site == 'D', 'no_show_rate'].iloc[0]))

    def test_quality_rejects_duplicate_and_future_snapshot(self):
        self.book('P1', site='A')
        df = self.store.dataframe()
        with self.assertRaises(ValueError):
            operational_report(pd.concat([df, df]), as_of=NOW)
        with self.assertRaises(ValueError):
            operational_report(df, as_of=NOW-timedelta(days=1))

    def test_capacity_missing_zero_and_distinct_regimes(self):
        base = {'organisation': 'E', 'site': 'S', 'period': '2030-01'}
        booked = pd.DataFrame([base | {'regime': r, 'booked_minutes': 30} for r in ['SSN', 'ALPI', 'SOLVENZA']])
        capacity = pd.DataFrame([base | {'regime': 'SSN', 'available_minutes': 60}, base | {'regime': 'ALPI', 'available_minutes': 0}])
        result = capacity_report(booked, capacity).set_index('regime')
        self.assertEqual(result.loc['SSN', 'saturation'], .5)
        self.assertTrue(pd.isna(result.loc['ALPI', 'saturation']))
        self.assertFalse(result.loc['SOLVENZA', 'capacity_known'])

    def test_annual_gaps_do_not_claim_yoy(self):
        base = {'cod_ats_erogazione': 'A', 'desc_ats_erogazione': 'ATS', 'pubb_priv': 'PRIVATO', 'source_rows': 1, 'cod_class_priorita': 'NON_INDICATA'}
        df = pd.DataFrame([base | {'anno': y, 'volume': v} for y, v in [(2020, 100), (2022, 200), (2023, 220)]])
        report = public_annual_report(df)
        self.assertTrue(pd.isna(report.yoy_fraction.iloc[1]))
        self.assertAlmostEqual(report.yoy_fraction.iloc[2], .1)
        self.assertNotIn('regime', report.columns)


class MachineLearningTests(unittest.TestCase):
    def series(self):
        return pd.DataFrame({'week': pd.date_range('2024-01-01', periods=80, freq='7D'), 'requests': np.arange(80)+20, 'complete': True})

    def test_chronological_holdout_and_nonnegative_future(self):
        df = self.series()
        metrics, heldout, future = evaluate_demand(df)
        self.assertEqual(len(heldout), 12)
        self.assertLess(metrics['training_end'], metrics['holdout_start'])
        self.assertEqual(heldout.baseline.iloc[0], df.requests.iloc[-13])
        self.assertTrue((future.predicted_requests >= 0).all())
        self.assertGreater(future.week.min(), heldout.week.max())

    def test_future_target_does_not_leak_into_earlier_predictions(self):
        df = self.series()
        _, original, _ = evaluate_demand(df)
        df.loc[79, 'requests'] = 10000
        _, changed, _ = evaluate_demand(df)
        np.testing.assert_allclose(original.prediction, changed.prediction)

    def test_missing_incomplete_insufficient_weeks_rejected(self):
        df = self.series()
        for invalid in [df.drop(index=10), df.iloc[:30], df.assign(complete=False), df.assign(requests=-1)]:
            with self.assertRaises(ValueError):
                validate_weekly(invalid)

    def test_zero_only_training_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_demand(self.series().assign(requests=0))


class SnapshotTests(unittest.TestCase):
    def test_coverage_failure_preserves_previous_file(self):
        def fetch(url):
            if '/api/views/' in url:
                return {'id': '6n7g-5p5e', 'licenseId': 'CC0_10', 'rowsUpdatedAt': 1}
            if 'count' in url:
                return [{'rows': '2'}]
            return [{'name': 'ONE'}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'geografia.json'
            path.write_text('PREVIOUS', encoding='utf-8')
            with self.assertRaises(ValueError):
                snapshot('geografia', folder, fetch)
            self.assertEqual(path.read_text(), 'PREVIOUS')

    def test_snapshot_hash_detects_corruption(self):
        def fetch(url):
            if '/api/views/' in url:
                return {'id': '6n7g-5p5e', 'name': 'test', 'licenseId': 'CC0_10', 'rowsUpdatedAt': 1}
            if 'count' in url:
                return [{'rows': '1'}]
            return [{'name': 'ONE'}]
        with tempfile.TemporaryDirectory() as folder:
            _, payload = snapshot('geografia', folder, fetch)
            self.assertTrue(verify_snapshot(payload))
            payload['rows'][0]['name'] = 'TWO'
            with self.assertRaises(ValueError):
                verify_snapshot(payload)


if __name__ == '__main__':
    unittest.main()

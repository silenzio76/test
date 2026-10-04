import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from public_derivations import derive_annual_production, export_derivation_package, VERSION


def row(year, volume, code='001', nature='PUBBLICO', label='ATS sintetica', priority='B'):
    return dict(anno=str(year), volume=str(volume), source_rows='1',
                cod_ats_erogazione=code, desc_ats_erogazione=label, pubb_priv=nature,
                cod_branca='001', desc_branca='Branca sintetica', cod_class_priorita=priority)


def snapshot(rows):
    return dict(dataset_id='qm4z-s92m', rows=rows, title='Fonte sintetica',
                source_rows=len(rows), downloaded_rows=len(rows), query={},
                rows_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest())


class DerivationTests(unittest.TestCase):
    def test_gaps_zero_base_and_isolated_cohorts(self):
        payload = snapshot([row(2020, 10), row(2021, 15), row(2023, 20),
                            row(2020, 0, nature='PRIVATO'), row(2021, 8, nature='PRIVATO')])
        frame, recipe = derive_annual_production(payload)
        public = frame.loc[frame.pubb_priv == 'PUBBLICO'].set_index('anno')
        self.assertEqual(public.loc[2021, 'yoy_absolute'], 5)
        self.assertEqual(public.loc[2021, 'yoy_pct'], 50)
        self.assertEqual(public.loc[2023, 'previous_available_year'], 2021)
        self.assertEqual(public.loc[2023, 'missing_years_count'], 1)
        self.assertTrue(pd.isna(public.loc[2023, 'yoy_absolute']))
        self.assertEqual(public.loc[2023, 'comparison_status'], 'missing_years')
        private = frame.loc[(frame.pubb_priv == 'PRIVATO') & (frame.anno == 2021)].iloc[0]
        self.assertEqual(private.yoy_absolute, 8)
        self.assertTrue(pd.isna(private.yoy_pct))
        self.assertEqual(private.comparison_status, 'zero_previous_volume')
        self.assertEqual(recipe['version'], VERSION)
        self.assertEqual(frame.cod_ats_erogazione.unique().tolist(), ['001'])
        self.assertTrue(all(item['source_volume'] == item['derived_volume'] for item in recipe['reconciliation_by_year']))

    def test_label_changes_do_not_split_codes_and_unknowns_have_explicit_denominator(self):
        payload = snapshot([row(2020, 10), row(2021, 4, label='ATS rinominata', priority=''),
                            row(2021, 6, label='Altra descrizione', priority='P')])
        original = copy.deepcopy(payload)
        frame, recipe = derive_annual_production(payload)
        current = frame.loc[frame.anno == 2021].iloc[0]
        self.assertEqual(current.ats_label_variants, 2)
        self.assertEqual(current.yoy_absolute, 0)
        self.assertEqual(current.unknown_priority_volume, 4)
        self.assertEqual(current.unknown_priority_pct, 40)
        self.assertEqual(payload, original)
        self.assertEqual(current.coverage_status, 'unverified')
        self.assertTrue(all(set(['formula', 'source_columns', 'unit', 'null_rule', 'version']) <= set(item) for item in recipe['columns']))

    def test_invalid_values_schema_and_altered_source_rejected(self):
        for column, value in [('volume', '-1'), ('volume', 'inf'), ('volume', '1.5'),
                              ('source_rows', '0'), ('anno', '2020.5'), ('cod_ats_erogazione', 1)]:
            record = row(2020, 1)
            record[column] = value
            with self.subTest(column=column, value=value), self.assertRaises((ValueError, TypeError)):
                derive_annual_production(snapshot([record]))
        payload = snapshot([row(2020, 1)])
        payload['rows'][0]['volume'] = '100'
        with self.assertRaises(ValueError):
            derive_annual_production(payload)
        with self.assertRaises(ValueError):
            derive_annual_production(snapshot([]))

    def test_atomic_package_preserves_source_codes_and_detects_corruption(self):
        payload = snapshot([row(2020, 1), row(2021, 3)])
        with tempfile.TemporaryDirectory() as folder:
            path = export_derivation_package(payload, folder)
            self.assertEqual(json.loads((path / 'source.json').read_text(encoding='utf-8')), payload)
            records = list(csv.DictReader(io.StringIO((path / 'annual.csv').read_text(encoding='utf-8'))))
            self.assertEqual(records[0]['cod_ats_erogazione'], '001')
            self.assertEqual(export_derivation_package(payload, folder), path)
            (path / 'annual.csv').write_text('corrupted', encoding='utf-8')
            with self.assertRaises(ValueError):
                export_derivation_package(payload, folder)
            self.assertEqual((path / 'annual.csv').read_text(encoding='utf-8'), 'corrupted')
            self.assertFalse(list(Path(folder).glob('.annual-production-*')))

    def test_failed_publication_preserves_existing_package_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            old = export_derivation_package(snapshot([row(2020, 1)]), folder)
            before = {p.name: p.read_bytes() for p in old.iterdir()}
            with patch('public_derivations.os.replace', side_effect=OSError('simulated failure')):
                with self.assertRaises(OSError):
                    export_derivation_package(snapshot([row(2020, 2)]), folder)
            self.assertEqual({p.name: p.read_bytes() for p in old.iterdir()}, before)
            self.assertFalse(list(Path(folder).glob('.annual-production-*')))


class DerivationUITests(unittest.TestCase):
    def test_recipe_preview_export_and_stale_state(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication, QMessageBox
        from healthcare_analysis_tab import HealthcareAnalysisTab
        from visit_workflow import VisitStore
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder / 'synthetic.json'
            path.write_text(json.dumps(snapshot([row(2020, 1), row(2021, 2)])), encoding='utf-8')
            tab = HealthcareAnalysisTab(VisitStore(folder / 'visits.sqlite3'), lambda *_: None)
            tab.analysis_choice.setCurrentIndex(3)
            self.assertFalse(tab.export_derivations_button.isEnabled())
            with patch.object(QMessageBox, 'warning') as warning:
                tab.annual_derivations(path)
                warning.assert_not_called()
            self.assertEqual(len(tab.frame), 2)
            self.assertGreater(tab.recipe_table.rowCount(), 0)
            self.assertTrue(tab.result_tabs.isTabEnabled(1))
            with patch.object(QMessageBox, 'warning') as warning:
                tab.export_derivations(folder / 'export')
                warning.assert_not_called()
            self.assertEqual(len(list((folder / 'export').glob('annual-production-*'))), 1)
            tab.analysis_choice.setCurrentIndex(0)
            self.assertIsNone(tab.derivation_payload)
            self.assertFalse(tab.export_derivations_button.isEnabled())
            self.assertFalse(tab.result_tabs.isTabEnabled(1))
            with patch.object(QMessageBox, 'warning'):
                tab.annual_derivations(folder / 'missing.json')
            self.assertTrue(tab.frame.empty)
            self.assertFalse(tab.publish_button.isEnabled())
            tab.close()
            app.processEvents()

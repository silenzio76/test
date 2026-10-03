import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from visit_workflow import VisitStore, validate_visit_dataframe

NOW = datetime(2030, 1, 1, 8, tzinfo=timezone.utc)
START = NOW + timedelta(hours=1)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = VisitStore(Path(self.tmp.name) / "visits.sqlite3")

    def book(self, patient="P001", resource="A01", start=START, duration=30):
        return self.store.book(patient, "Cardiologia", resource, start, duration, "OP01", now=NOW)

    def transition(self, visit, target, expected, now=START):
        self.store.change_status(visit, target, "OP02", expected_status=expected, now=now)

    def test_full_workflow_and_persistence(self):
        visit = self.book()
        for before, after in [("prenotata", "confermata"), ("confermata", "accettata"), ("accettata", "eseguita")]:
            self.transition(visit, after, before)
        reopened = VisitStore(self.store.path)
        row = reopened.list_visits()[0]
        self.assertEqual(row["status"], "eseguita")
        self.assertEqual(row["executed_at"], START.isoformat())
        self.assertEqual(len(reopened.history(visit)), 4)
        self.assertEqual(reopened.history(visit)[-1]["actor"], "OP02")

    def test_resource_overlap_rolls_back(self):
        visit = self.book()
        with self.assertRaises(ValueError):
            self.book("P002", "a01", START + timedelta(minutes=10))
        self.assertEqual(len(self.store.list_visits()), 1)
        self.assertEqual(len(self.store.history(visit)), 1)

    def test_patient_overlap_across_resources(self):
        self.book()
        with self.assertRaises(ValueError):
            self.book("p001", "A02")

    def test_adjacent_slots_and_independent_resources(self):
        self.book()
        self.book("P002", start=START + timedelta(minutes=30))
        self.book("P003", "A02")
        self.assertEqual(len(self.store.list_visits()), 3)

    def test_cancel_frees_slot_and_is_terminal(self):
        visit = self.book()
        self.transition(visit, "annullata", "prenotata", now=NOW)
        self.book("P002")
        with self.assertRaises(ValueError):
            self.transition(visit, "confermata", "annullata")

    def test_skip_states_and_stale_update_rejected(self):
        visit = self.book()
        with self.assertRaises(ValueError):
            self.transition(visit, "eseguita", "prenotata")
        self.transition(visit, "confermata", "prenotata", now=NOW)
        with self.assertRaises(ValueError):
            self.transition(visit, "annullata", "prenotata")
        self.assertEqual(len(self.store.history(visit)), 2)

    def test_future_completion_and_no_show_rejected(self):
        visit = self.book()
        with self.assertRaises(ValueError):
            self.transition(visit, "non_presentato", "prenotata", now=NOW)
        self.transition(visit, "confermata", "prenotata", now=NOW)
        self.transition(visit, "accettata", "confermata", now=NOW)
        with self.assertRaises(ValueError):
            self.transition(visit, "eseguita", "accettata", now=NOW)
        self.assertIsNone(self.store.list_visits()[0]["executed_at"])

    def test_invalid_input_does_not_write(self):
        for duration in (0, -1, 481, True, 1.5):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                self.book(duration=duration)
        for start in (START.replace(tzinfo=None), NOW - timedelta(seconds=1)):
            with self.assertRaises(ValueError):
                self.book(start=start)
        with self.assertRaises(ValueError):
            self.book(patient=" ")
        self.assertEqual(self.store.list_visits(), [])

    def test_timezone_normalization_detects_same_instant(self):
        self.book()
        local = START.astimezone(timezone(timedelta(hours=2)))
        with self.assertRaises(ValueError):
            self.book("P002", start=local)

    def test_reschedule_conflict_is_atomic(self):
        first = self.book()
        second = self.book("P002", start=START + timedelta(hours=1))
        with self.assertRaises(ValueError):
            self.store.reschedule(first, START + timedelta(hours=1), 30, "OP02", expected_status="prenotata", now=NOW)
        self.assertEqual(self.store.list_visits()[0]["starts_at"], START.isoformat())
        self.assertEqual(len(self.store.history(first)), 1)
        self.assertEqual(len(self.store.history(second)), 1)

    def test_reschedule_resets_confirmation_and_frees_old_slot(self):
        visit = self.book()
        self.transition(visit, "confermata", "prenotata", now=NOW)
        self.store.reschedule(visit, START + timedelta(hours=1), 20, "OP02", expected_status="confermata", now=NOW)
        self.book("P002")
        self.assertEqual(self.store.list_visits()[-1]["status"], "prenotata")
        self.assertEqual(len(self.store.history(visit)), 3)

    def test_backward_event_time_rejected(self):
        visit = self.book()
        self.transition(visit, "confermata", "prenotata", now=START)
        with self.assertRaises(ValueError):
            self.transition(visit, "accettata", "confermata", now=NOW)

    def test_no_show_frees_slot(self):
        visit = self.book()
        self.transition(visit, "non_presentato", "prenotata")
        self.store.book("P002", "Cardiologia", "A01", START, 30, "OP01", now=START)

    def test_sql_text_stays_data(self):
        self.book(patient="P'; DROP TABLE visits; --")
        self.assertEqual(len(self.store.list_visits()), 1)

    @unittest.skipUnless(importlib.util.find_spec("pandas"), "pandas non disponibile")
    def test_analytics_excludes_identifiers_and_counts_states(self):
        self.book()
        other = self.book("P002", "A02")
        self.transition(other, "annullata", "prenotata", now=NOW)
        frame = self.store.analytics()
        self.assertEqual(list(frame.columns), ["service", "status", "visits"])
        self.assertEqual(frame.visits.sum(), 2)
        self.assertNotIn("patient_code", frame.columns)

    @unittest.skipUnless(importlib.util.find_spec("pandera"), "pandera non disponibile")
    def test_pandera_accepts_valid_data_rejects_corruption(self):
        self.book()
        frame = self.store.dataframe()
        validate_visit_dataframe(frame)
        broken = frame.copy()
        broken.loc[0, "status"] = "eseguita"
        with self.assertRaises(Exception):
            validate_visit_dataframe(broken)
        broken = frame.copy()
        broken.loc[0, "ends_at"] = (START - timedelta(minutes=1)).isoformat()
        with self.assertRaises(Exception):
            validate_visit_dataframe(broken)


if importlib.util.find_spec("hypothesis"):
    from hypothesis import given, settings, strategies as st

    class GeneratedConflictTests(unittest.TestCase):
        @settings(max_examples=25, deadline=None)
        @given(duration=st.integers(min_value=2, max_value=240), offset=st.integers(min_value=0, max_value=239))
        def test_overlap_and_boundary(self, duration, offset):
            with tempfile.TemporaryDirectory() as folder:
                store = VisitStore(Path(folder) / "visits.sqlite3")
                store.book("P1", "Visita", "A1", START, duration, "OP", now=NOW)
                new_start = START + timedelta(minutes=offset)
                if offset < duration:
                    with self.assertRaises(ValueError):
                        store.book("P2", "Visita", "A1", new_start, 30, "OP", now=NOW)
                else:
                    store.book("P2", "Visita", "A1", new_start, 30, "OP", now=NOW)

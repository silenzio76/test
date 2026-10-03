import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("PySide6") and importlib.util.find_spec("pandas"), "Qt/pandas non disponibili")
class VisitUiTests(unittest.TestCase):
    def test_tab_booking_selection_and_report_bridge(self):
        from PySide6.QtWidgets import QApplication
        from visit_workflow import VisitStore
        from visit_tab import VisitTab
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            store = VisitStore(Path(folder) / "visits.sqlite3")
            now = datetime.now(timezone.utc)
            visit = store.book("P1", "Visita", "A1", now + timedelta(days=1), 30, "OP", now=now)
            datasets = []
            tab = VisitTab(lambda frame, label: datasets.append((frame, label)), store=store)
            self.assertEqual(tab.table.rowCount(), 1)
            tab.table.selectRow(0)
            app.processEvents()
            self.assertEqual(tab.selected()["id"], visit)
            self.assertIn("confermata", [tab.target.itemText(i) for i in range(tab.target.count())])
            tab.actor.setText("OP2")
            tab.target.setCurrentText("confermata")
            tab.change_status()
            self.assertEqual(store.list_visits()[0]["status"], "confermata")
            tab.publish()
            self.assertEqual(datasets[0][0].visits.sum(), 1)
            self.assertNotIn("patient_code", datasets[0][0].columns)
            csv_path = Path(folder) / "visits.csv"
            csv_path.write_text("original", encoding="utf-8")
            with patch("visit_tab.QFileDialog.getSaveFileName", return_value=(str(csv_path), "CSV")):
                tab.export()
            self.assertIn("patient_code", csv_path.read_text(encoding="utf-8-sig"))
            self.assertFalse(list(Path(folder).glob("*.tmp")))
            tab.filter.setCurrentText("eseguita")
            self.assertEqual(tab.table.rowCount(), 0)
            self.assertFalse(tab.change.isEnabled())
            tab.close()

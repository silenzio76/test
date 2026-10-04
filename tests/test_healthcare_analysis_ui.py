import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from healthcare_analysis_tab import HealthcareAnalysisTab
from visit_workflow import VisitStore
from PySide6.QtWidgets import QApplication, QMessageBox


class AnalysisUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_source_change_and_failed_analysis_cannot_publish_previous_result(self):
        with tempfile.TemporaryDirectory() as folder:
            published = []
            tab = HealthcareAnalysisTab(VisitStore(Path(folder) / 'visits.sqlite3'),
                                       lambda frame, label: published.append(frame))
            self.assertFalse(tab.publish_button.isEnabled())
            self.assertFalse(tab.future_button.isEnabled())
            tab.show_frame(pd.DataFrame({'count': [2]}), 'Synthetic')
            tab.publish()
            self.assertEqual(published[0]['count'].tolist(), [2])
            tab.analysis_choice.setCurrentIndex(1)
            self.assertTrue(tab.frame.empty)
            self.assertFalse(tab.publish_button.isEnabled())
            tab.show_frame(pd.DataFrame({'count': [3]}), 'Synthetic previous')
            with patch.object(QMessageBox, 'warning'):
                tab.public(Path(folder) / 'missing.json')
            self.assertTrue(tab.frame.empty)
            self.assertFalse(tab.publish_button.isEnabled())
            self.assertIn('non completata', tab.status.text())
            tab.publish()
            self.assertEqual(len(published), 1)
            tab.close()

    def test_failed_ml_discards_forecast_but_cancel_preserves_current_analysis(self):
        with tempfile.TemporaryDirectory() as folder:
            tab = HealthcareAnalysisTab(VisitStore(Path(folder) / 'visits.sqlite3'), lambda *_: None)
            tab.analysis_choice.setCurrentIndex(2)
            tab.future = pd.DataFrame({'requests': [10]})
            tab.future_button.setEnabled(True)
            tab.show_frame(pd.DataFrame({'count': [1]}), 'Synthetic previous')
            with patch('healthcare_analysis_tab.QFileDialog.getOpenFileName', return_value=('', 'CSV')):
                tab.ml()
            self.assertFalse(tab.frame.empty)
            path = Path(folder) / 'bad.csv'
            path.write_text('wrong\n1\n', encoding='utf-8')
            with patch('healthcare_analysis_tab.QFileDialog.getOpenFileName', return_value=(str(path), 'CSV')), patch.object(QMessageBox, 'warning'):
                tab.ml()
            self.assertTrue(tab.future.empty)
            self.assertTrue(tab.frame.empty)
            self.assertFalse(tab.future_button.isEnabled())
            self.assertFalse(tab.publish_button.isEnabled())
            tab.close()

"""Smoke semantic navigation, import/report bridge, exports and small-window UI.

Optional --screenshots DIRECTORY writes synthetic-data QA images without downloads.
"""
import argparse
import csv
import json
import hashlib
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

parser = argparse.ArgumentParser()
parser.add_argument('--screenshots', type=Path)
args = parser.parse_args()

with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    os.environ['HEALTHREPORT_VISITS_DB'] = str(folder / 'visits.sqlite3')
    os.environ['HEALTHREPORT_STAGING_DB'] = str(folder / 'staging.sqlite3')
    os.environ['MPLCONFIGDIR'] = str(folder / 'matplotlib')
    import dependency_manager
    with patch.object(dependency_manager, 'ensure_dependencies_before_startup'):
        import main
    from PySide6.QtGui import QFontDatabase, QFont
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    app = main.QApplication.instance() or main.QApplication([])
    # Offscreen Windows does not enumerate the OS font registry in this runtime.
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        if font_id >= 0:
            app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    window = main.MainWindow()
    unexpected_warning = patch.object(main.QMessageBox, 'warning', side_effect=AssertionError('Unexpected UI warning'))
    unexpected_warning.start()
    window.resize(1200, 800)
    window.show()
    app.processEvents()
    assert window.tabs.count() == 5
    from external_staging import PROFILE
    source = folder / 'geography.csv'
    with source.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=PROFILE.values())
        writer.writeheader()
        row = {field: '' for field in PROFILE.values()}
        row.update(codice_struttura_di_ricovero='000001', descrizione_struttura_di='Struttura sintetica QA', cap='00100')
        writer.writerow(row)
    window.navigate('import')
    panel = window.import_tab
    panel.choose_source(source)
    panel.validate_button.setFocus()
    QTest.keyClick(panel.validate_button, Qt.Key.Key_Space)
    assert panel.import_button.isEnabled()
    panel.import_button.setFocus()
    QTest.keyClick(panel.import_button, Qt.Key.Key_Space)
    assert panel.batch_id
    panel.match()
    assert panel.frame.external_code.tolist() == ['000001']
    with patch.object(main.QMessageBox, 'information'):
        panel.publish_button.click()
    assert window.tabs.currentWidget() is window.pages['report']
    assert window.raw_df.external_code.tolist() == ['000001']
    assert 'geografia' in window.dataset_context.text().lower()
    exported = []
    with patch.object(window, '_rpt_export', side_effect=exported.append):
        for i in range(window.rpt_format_combo.count()):
            window.rpt_format_combo.setCurrentIndex(i)
            window.rpt_export_button.click()
    assert exported == ['pdf', 'xlsx', 'html', 'pptx', 'png', 'csv', 'odt']
    window.visit_tab.store.book('QA-SYNTHETIC', 'Visita sintetica', 'AMB-QA',
        datetime.now(timezone.utc) + timedelta(days=1), 20, 'QA')
    window.visit_tab.refresh()
    window.healthcare_tab.operational()
    assert not window.healthcare_tab.frame.empty
    annual_rows = [dict(anno=str(year), volume=str(volume), source_rows='1',
        cod_ats_erogazione='001', desc_ats_erogazione='ATS sintetica', pubb_priv='PUBBLICO',
        cod_branca='001', desc_branca='Branca sintetica', cod_class_priorita='B')
        for year, volume in [(2024, 10), (2025, 12)]]
    annual_source = folder / 'annual-synthetic.json'
    annual_source.write_text(json.dumps(dict(dataset_id='qm4z-s92m', title='Fonte sintetica QA',
        rows=annual_rows, source_rows=2, downloaded_rows=2, query={},
        rows_sha256=hashlib.sha256(json.dumps(annual_rows, sort_keys=True).encode()).hexdigest())), encoding='utf-8')
    window.healthcare_tab.analysis_choice.setCurrentIndex(3)
    window.healthcare_tab.annual_derivations(annual_source)
    assert window.healthcare_tab.frame.yoy_pct.dropna().tolist() == [20.0]
    assert window.healthcare_tab.result_tabs.isTabEnabled(1)
    window.healthcare_tab.export_derivations(folder / 'derivations')
    packages = list((folder / 'derivations').glob('annual-production-*'))
    assert len(packages) == 1
    assert {p.name for p in packages[0].iterdir()} == {'source.json', 'annual.csv', 'recipe.json', 'manifest.json'}
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    for key, page in window.pages.items():
        window.navigate(key)
        app.processEvents()
        assert window.tabs.currentWidget() is page
        assert window.width() == 1200, f'{key} expands window to {window.width()}'
        assert window.height() == 800, f'{key} expands window to height {window.height()}'
        if args.screenshots:
            assert window.grab().save(str(args.screenshots / f'workspace-{key}.png'))
    if args.screenshots:
        window.navigate('analytics')
        window.healthcare_tab.result_tabs.setCurrentIndex(1)
        app.processEvents()
        assert window.grab().save(str(args.screenshots / 'workspace-derivation-rules.png'))
    window.resize(1000, 700)
    window.navigate('visits')
    app.processEvents()
    assert window.width() == 1000
    assert window.height() == 700
    if args.screenshots:
        assert window.grab().save(str(args.screenshots / 'workspace-visits-small.png'))
    window.close()
    unexpected_warning.stop()
    app.processEvents()
    print('PASS: semantic routes, keyboard import, report publication, seven export callbacks, annual recipe/package, 1200x800 and 1000x700 layouts.')

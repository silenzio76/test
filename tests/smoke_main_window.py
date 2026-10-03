"""Exercise the real main window without bootstrap downloads or patient data."""
import os
from pathlib import Path
import tempfile
import sys
import json
import hashlib
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

with tempfile.TemporaryDirectory() as folder:
    os.environ["HEALTHREPORT_VISITS_DB"] = str(Path(folder) / "visits.sqlite3")
    os.environ["MPLCONFIGDIR"] = str(Path(folder) / "matplotlib")
    import dependency_manager
    with patch.object(dependency_manager, "ensure_dependencies_before_startup"):
        import main
    app = main.QApplication.instance() or main.QApplication([])
    window = main.MainWindow()
    assert window.tabs.count() == 4
    assert window.tabs.tabText(3) == "Visite sanitarie"
    assert window.tabs.tabText(2) == 'Statistica sanitaria e ML'
    from datetime import datetime, timedelta, timezone
    store = window.visit_tab.store
    store.book("SYNTHETIC-1", "Visita demo", "AMB-DEMO", datetime.now(timezone.utc) + timedelta(days=1), 20, "TEST")
    window.visit_tab.refresh()
    with patch.object(main.QMessageBox, "information", return_value=None):
        window.visit_tab.publish()
    assert list(window.raw_df.columns) == ["service", "status", "visits"]
    assert window.raw_df.visits.sum() == 1
    assert len(window.working_df) == 1
    window.healthcare_tab.operational()
    assert window.healthcare_tab.frame.bookings.sum() == 1
    rows = [{'anno': '2025', 'cod_ats_erogazione': 'TEST', 'desc_ats_erogazione': 'ATS sintetica',
             'pubb_priv': 'TEST', 'cod_branca': 'TEST', 'desc_branca': 'Branca sintetica',
             'cod_class_priorita': 'B', 'volume': '10', 'source_rows': '1'}]
    snapshot = {'dataset_id': 'qm4z-s92m', 'title': 'Fixture sintetica', 'source_updated_at': 'TEST',
                'rows': rows, 'source_rows': 1, 'downloaded_rows': 1, 'query': {'$group': 'anno,cod_ats_erogazione,pubb_priv,cod_branca,cod_class_priorita'},
                'rows_sha256': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
    snapshot_path = Path(folder) / 'synthetic_public.json'
    from lombardia_data import atomic_json
    atomic_json(snapshot_path, snapshot)
    window.healthcare_tab.public(snapshot_path)
    assert not window.healthcare_tab.frame.empty
    assert 'pubb_priv' in window.healthcare_tab.frame.columns
    window.close()
    app.processEvents()
    print("PASS: finestra reale, quattro schede, prenotazione, ETL/Report, indicatori e snapshot sintetico autonomo.")

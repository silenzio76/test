"""Healthcare analytics connected to the visit store and public snapshots."""
import json
from pathlib import Path
import pandas as pd
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox
from healthcare_statistics import operational_report, public_annual_report
from lombardia_data import specialistica_frame


class HealthcareAnalysisTab(QWidget):
    def __init__(self, store, publish_dataset, parent=None):
        super().__init__(parent)
        self.store, self.publish_dataset = store, publish_dataset
        self.frame = pd.DataFrame()
        self.future = pd.DataFrame()
        self.layout = QVBoxLayout(self)
        explanation = QLabel('Statistiche per ente, sede, prestazione, regime, priorità e accesso.\n'
                             'I dati regionali descrivono produzione SSR; le previsioni richiedono richieste settimanali interne complete.')
        explanation.setWordWrap(True)
        self.layout.addWidget(explanation)
        actions = QHBoxLayout()
        for caption, callback in [('Indicatori visite', self.operational), ('Produzione Lombardia', self.public),
                                  ('Valuta previsione domanda CSV', self.ml), ('Previsioni future', self.show_future), ('Invia tabella ai Report', self.publish)]:
            button = QPushButton(caption)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.layout.addLayout(actions)
        self.status = QLabel('Selezionare un’analisi. Nessun modello è addestrato automaticamente.')
        self.status.setWordWrap(True)
        self.layout.addWidget(self.status)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.layout.addWidget(self.table)

    def show_frame(self, frame, label):
        self.frame = frame
        self.label = label
        self.table.clear()
        self.table.setColumnCount(len(frame.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        # Display bounded rows; publication always uses the full table.
        self.table.setRowCount(min(1000, len(frame)))
        for i, row in enumerate(frame.head(1000).itertuples(index=False, name=None)):
            for j, value in enumerate(row):
                self.table.setItem(i, j, QTableWidgetItem('' if pd.isna(value) else str(value)))
        self.table.resizeColumnsToContents()
        self.status.setText(f'{label} — {len(frame)} righe; anteprima fino a 1.000 righe.')

    def run(self, action):
        try:
            action()
        except Exception as exc:
            QMessageBox.warning(self, 'Analisi non disponibile', str(exc))

    def operational(self):
        self.run(lambda: self.show_frame(operational_report(self.store.dataframe()), 'Indicatori dello snapshot corrente'))

    def public(self, snapshot_path=None):
        def action():
            path = Path(snapshot_path) if snapshot_path else Path(__file__).parent / 'data' / 'public' / 'specialistica.json'
            if not path.exists():
                raise ValueError('Snapshot assente. Eseguire python lombardia_data.py --dataset specialistica.')
            payload = json.loads(path.read_text(encoding='utf-8'))
            from lombardia_data import verify_snapshot
            verify_snapshot(payload)
            self.show_frame(public_annual_report(specialistica_frame(payload)), 'Produzione SSR annuale per ATS e natura erogatore')
            self.status.setText(self.status.text() + f" Fonte: {payload['title']}; aggiornata {payload['source_updated_at']}. pubb_priv indica l’erogatore, non SSN/ALPI.")
        self.run(action)

    def ml(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Serie di richieste settimanali: week, requests, complete', '', 'CSV (*.csv)')
        if not path:
            return
        self.future = pd.DataFrame()
        def action():
            from healthcare_ml import evaluate_demand
            frame = pd.read_csv(path)
            metrics, heldout, future = evaluate_demand(frame)
            self.show_frame(heldout, 'Validazione cronologica della domanda: ultime 12 settimane')
            self.status.setText(f"MAE modello: {metrics['model']['mae']:.2f}; riferimento ultima settimana: {metrics['last_week_baseline']['mae']:.2f}. "
                                f"Migliora il riferimento: {metrics['better_than_baseline_mae']}. Previsione futura di 4 settimane disponibile nei Report dopo la validazione. Nessun impiego automatico sulle prenotazioni.")
            self.future = future
        self.run(action)

    def show_future(self):
        if self.future.empty:
            self.status.setText('Prima valutare una serie settimanale completa; nessuna previsione disponibile.')
            return
        self.show_frame(self.future, 'Previsione ricorsiva delle richieste; stime senza intervalli calibrati')

    def publish(self):
        if self.frame.empty:
            return
        self.run(lambda: self.publish_dataset(self.frame.copy(), self.label))

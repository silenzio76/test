"""Healthcare analytics connected to the visit store and public snapshots."""
import json
from pathlib import Path
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QGroupBox, QComboBox, QSplitter, QTabWidget
from healthcare_statistics import operational_report, public_annual_report
from lombardia_data import specialistica_frame


class HealthcareAnalysisTab(QWidget):
    def __init__(self, store, publish_dataset, parent=None):
        super().__init__(parent)
        self.store, self.publish_dataset = store, publish_dataset
        self.frame = pd.DataFrame()
        self.future = pd.DataFrame()
        self.label = ''
        self.derivation_payload = None
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(16, 16, 16, 16)
        self.root_layout.setSpacing(12)
        from workspace_ui import heading
        self.root_layout.addWidget(heading('Statistica sanitaria',
            'Scegli il dato da analizzare. Importazioni e corrispondenze si trovano in Import e anagrafiche.'))
        split = QSplitter(Qt.Orientation.Horizontal)
        options = QGroupBox('Fonte e metodo')
        controls = QVBoxLayout(options)
        self.analysis_choice = QComboBox()
        self.analysis_choice.addItems(['Registro visite', 'Produzione regionale', 'Domanda settimanale CSV', 'Derivazioni annuali SSR'])
        controls.addWidget(self.analysis_choice)
        self.method_description = QLabel()
        self.method_description.setWordWrap(True)
        controls.addWidget(self.method_description)
        self.calculate_button = QPushButton('Calcola indicatori')
        self.calculate_button.setProperty('primary', True)
        self.calculate_button.clicked.connect(self.calculate_selected)
        controls.addWidget(self.calculate_button)
        self.future_button = QPushButton('Mostra previsioni future')
        self.future_button.clicked.connect(self.show_future)
        controls.addWidget(self.future_button)
        self.export_derivations_button = QPushButton('Esporta dati e regole')
        self.export_derivations_button.clicked.connect(self.export_derivations)
        controls.addWidget(self.export_derivations_button)
        controls.addStretch()
        boundary = QLabel('I volumi annuali non ricostruiscono richieste settimanali o assenze.\n'
                         'Nessun modello modifica le prenotazioni.')
        boundary.setWordWrap(True)
        controls.addWidget(boundary)
        results = QWidget()
        result_layout = QVBoxLayout(results)
        result_layout.setContentsMargins(12, 0, 0, 0)
        self.status = QLabel('Selezionare un’analisi. Nessun modello è addestrato automaticamente.')
        self.status.setWordWrap(True)
        result_layout.addWidget(self.status)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(self.table, 'Risultati')
        self.recipe_table = QTableWidget()
        self.recipe_table.setAlternatingRowColors(True)
        self.recipe_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_tabs.addTab(self.recipe_table, 'Regole e unità')
        result_layout.addWidget(self.result_tabs, 1)
        self.publish_button = QPushButton('Invia tabella ai Report')
        self.publish_button.clicked.connect(self.publish)
        result_layout.addWidget(self.publish_button)
        split.addWidget(options)
        split.addWidget(results)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 800])
        self.root_layout.addWidget(split, 1)
        self.analysis_choice.currentIndexChanged.connect(self.update_selection)
        self.update_selection()

    def clear_result(self):
        self.frame = pd.DataFrame()
        self.label = ''
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.publish_button.setEnabled(False)
        self.derivation_payload = None
        self.recipe_table.clear()
        self.recipe_table.setRowCount(0)
        self.recipe_table.setColumnCount(0)
        self.result_tabs.setCurrentIndex(0)
        self.result_tabs.setTabEnabled(1, False)
        self.export_derivations_button.setEnabled(False)

    def update_selection(self, *_):
        self.clear_result()
        descriptions = [
            'Lista aperta, esecuzioni e assenze del registro locale. Attese solo con richiesta verificata.',
            'Produzione SSR annuale per ATS e natura dell’erogatore. Fonte pubblica aggregata, distinta dal regime SSN/ALPI.',
            'Random Forest: almeno 52 settimane consecutive complete per una sola coorte; include richieste non prenotate.',
            'Deriva variazioni e controlli sui volumi SSR annuali. Anteprima, formule versionate, anni mancanti e riconciliazione con la fonte.',
        ]
        selected = self.analysis_choice.currentIndex()
        self.method_description.setText(descriptions[selected])
        self.calculate_button.setText(['Calcola indicatori', 'Analizza produzione', 'Scegli CSV e valuta', 'Genera e verifica colonne'][selected])
        self.future_button.setEnabled(selected == 2 and not self.future.empty)
        self.status.setText('Nessun risultato per questa selezione. Avvia l’analisi dalla colonna a sinistra.')

    def calculate_selected(self):
        [self.operational, self.public, self.ml, self.annual_derivations][self.analysis_choice.currentIndex()]()

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
        self.publish_button.setEnabled(not frame.empty)

    def run(self, action, *, clear=True):
        if clear:
            self.clear_result()
            self.status.setText('Analisi in corso…')
        try:
            action()
        except Exception as exc:
            self.clear_result()
            self.future = pd.DataFrame()
            self.future_button.setEnabled(False)
            self.status.setText(f'Analisi non completata: {exc}')
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
        self.future_button.setEnabled(False)
        def action():
            from healthcare_ml import evaluate_demand
            frame = pd.read_csv(path)
            metrics, heldout, future = evaluate_demand(frame)
            self.show_frame(heldout, 'Validazione cronologica della domanda: ultime 12 settimane')
            self.status.setText(f"MAE modello: {metrics['model']['mae']:.2f}; riferimento ultima settimana: {metrics['last_week_baseline']['mae']:.2f}. "
                                f"Migliora il riferimento: {metrics['better_than_baseline_mae']}. Previsione futura di 4 settimane disponibile nei Report dopo la validazione. Nessun impiego automatico sulle prenotazioni.")
            self.future = future
            self.future_button.setEnabled(not future.empty)
        self.run(action)

    def annual_derivations(self, snapshot_path=None):
        def action():
            from public_derivations import derive_annual_production
            path = Path(snapshot_path) if snapshot_path else Path(__file__).parent / 'data' / 'public' / 'specialistica.json'
            payload = json.loads(path.read_text(encoding='utf-8'))
            frame, recipe = derive_annual_production(payload)
            self.show_frame(frame, f"Derivazioni SSR annuali; dati osservati; ricetta {recipe['version']}")
            columns = ['column', 'formula', 'source_columns', 'unit', 'null_rule', 'version']
            self.recipe_table.setColumnCount(len(columns))
            self.recipe_table.setHorizontalHeaderLabels(['Colonna', 'Formula', 'Colonne sorgente', 'Unità', 'Regola sui nulli', 'Versione'])
            self.recipe_table.setRowCount(len(recipe['columns']))
            for i, definition in enumerate(recipe['columns']):
                for j, key in enumerate(columns):
                    value = definition[key]
                    self.recipe_table.setItem(i, j, QTableWidgetItem(', '.join(value) if isinstance(value, list) else str(value)))
            self.recipe_table.resizeColumnsToContents()
            self.derivation_payload = payload
            self.result_tabs.setTabEnabled(1, True)
            self.export_derivations_button.setEnabled(True)
            gaps = int((frame.comparison_status == 'missing_years').sum())
            self.status.setText(self.status.text() + f" Fonte: {payload.get('title', payload['dataset_id'])}; "
                f"aggiornata {payload.get('source_updated_at', 'non indicato')}. Totali riconciliati per anno; "
                f"{gaps} confronti con anni mancanti. Copertura annuale non certificata. Ricetta {recipe['version']}.")
        self.run(action)

    def export_derivations(self, output=None):
        if self.derivation_payload is None:
            return
        output = output or QFileDialog.getExistingDirectory(self, 'Cartella per dati originali, derivazioni, regole e manifest')
        if not output:
            return
        def action():
            from public_derivations import export_derivation_package
            path = export_derivation_package(self.derivation_payload, output)
            self.status.setText(f'Pacchetto verificato: {path}. Fonte originale, annual.csv, ricetta e hash conservati insieme.')
        self.run(action, clear=False)

    def show_future(self):
        if self.future.empty:
            self.status.setText('Prima valutare una serie settimanale completa; nessuna previsione disponibile.')
            return
        self.show_frame(self.future, 'Previsione ricorsiva delle richieste; stime senza intervalli calibrati')

    def publish(self):
        if self.frame.empty:
            return
        self.run(lambda: self.publish_dataset(self.frame.copy(), self.label), clear=False)

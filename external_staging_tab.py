"""Embedded import workspace; no connection to the operational visit store."""
import os
from pathlib import Path
from datetime import date
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFormLayout, QScrollArea, QWidget, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QLineEdit)
from external_staging import PROFILE, StagingStore, load_geography, preview, counts


class GeographyImportTab(QWidget):
    def __init__(self, publish_dataset, parent=None, staging_path=None):
        super().__init__(parent)
        self.publish_dataset = publish_dataset
        path = staging_path or os.environ.get('HEALTHREPORT_STAGING_DB') or Path(__file__).parent / 'data' / 'external_staging.sqlite3'
        self.store = StagingStore(path)
        self.rows, self.metadata, self.document, self.batch_id = [], {}, None, None
        self.frame = pd.DataFrame()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        from workspace_ui import heading
        layout.addWidget(heading('Import e anagrafiche',
            '1. Scegli la fonte e le colonne.  2. Verifica le righe.  3. Conferma il lotto.  4. Controlla le corrispondenze.'))
        label = QLabel('Tracciato: geografia strutture di ricovero Lombardia (6n7g-5p5e), snapshot JSON o CSV con virgola.\n'
                       'Fonte storica: non certifica sedi ambulatoriali attuali. Nessuna modifica alle visite.\n'
                       'Le corrispondenze richiedono codici esatti, periodo, fonte e revisore; nessuna associazione per nome.')
        label.setWordWrap(True)
        layout.addWidget(label)
        actions = QHBoxLayout()
        self.load_button = QPushButton('Scegli fonte')
        self.load_button.clicked.connect(lambda: self.choose_source())
        self.validate_button = QPushButton('Verifica e anteprima')
        self.validate_button.clicked.connect(self.validate)
        self.import_button = QPushButton('Conferma import in staging')
        self.import_button.setProperty('primary', True)
        self.import_button.clicked.connect(self.commit)
        for button in (self.load_button, self.validate_button, self.import_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(170)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        self.columns = {}
        for field in PROFILE:
            combo = QComboBox()
            combo.currentTextChanged.connect(self.invalidate)
            captions = {'external_code': 'Codice struttura', 'name': 'Denominazione',
                        'ats': 'ATS', 'address': 'Indirizzo', 'postcode': 'CAP', 'city': 'Località'}
            form.addRow(captions[field], combo)
            self.columns[field] = combo
        scroll.setWidget(form_widget)
        layout.addWidget(scroll)
        matching = QHBoxLayout()
        mapping_button = QPushButton('Carica corrispondenze revisionate CSV')
        mapping_button.clicked.connect(lambda: self.choose_crosswalk())
        matching.addWidget(mapping_button)
        layout.addLayout(matching)
        matching = QHBoxLayout()
        matching.addWidget(QLabel('Validità alla data (AAAA-MM-GG):'))
        self.as_of = QLineEdit(date.today().isoformat())
        self.as_of.setMaximumWidth(160)
        self.as_of.textChanged.connect(self.clear_result)
        matching.addWidget(self.as_of)
        self.match_button = QPushButton('Verifica corrispondenze')
        self.match_button.clicked.connect(self.match)
        matching.addWidget(self.match_button)
        layout.addLayout(matching)
        self.status = QLabel('Scegliere una fonte. Nessun lotto importato in questa sessione.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.publish_button = QPushButton('Invia tabella e provenienza ai Report')
        self.publish_button.clicked.connect(self.publish)
        layout.addWidget(self.publish_button)
        self.invalidate()

    def clear_result(self, *_):
        self.frame = pd.DataFrame()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.publish_button.setEnabled(False)

    def invalidate(self, *_):
        self.document, self.batch_id = None, None
        self.import_button.setEnabled(False)
        self.match_button.setEnabled(False)
        self.validate_button.setEnabled(bool(self.rows))
        self.clear_result()
        self.status.setText('Mapping da verificare; nessun risultato corrente disponibile.')

    def show_frame(self, frame):
        self.frame = frame
        self.table.setColumnCount(len(frame.columns))
        self.table.setHorizontalHeaderLabels(list(frame.columns))
        self.table.setRowCount(min(len(frame), 1000))
        for i, row in enumerate(frame.head(1000).itertuples(index=False, name=None)):
            for j, value in enumerate(row):
                self.table.setItem(i, j, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.publish_button.setEnabled(not frame.empty)

    def error(self, exc):
        self.clear_result()
        self.status.setText(f'Operazione fallita: {exc}')
        QMessageBox.warning(self, 'Importazione non completata', str(exc))

    def choose_source(self, path=None):
        path = path or QFileDialog.getOpenFileName(self, 'Fonte geografica', '', 'Geografia (*.json *.csv)')[0]
        if not path:
            return
        self.rows, self.metadata = [], {}
        self.invalidate()
        try:
            self.rows, self.metadata = load_geography(path)
            available = sorted(set().union(*(row.keys() for row in self.rows)))
            for field, combo in self.columns.items():
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(available)
                combo.setCurrentIndex(combo.findText(PROFILE[field]))
                combo.blockSignals(False)
            self.validate_button.setEnabled(True)
            self.status.setText(f"{len(self.rows)} righe lette da {Path(path).name}; aggiornamento: "
                                f"{self.metadata.get('source_updated_at', 'non certificato')}. Verificare il mapping.")
        except Exception as exc:
            self.error(exc)

    def provenance(self):
        return {'source_file_sha256': self.metadata['file_sha256'],
                'source_updated_at': self.metadata.get('source_updated_at', 'non certificato'),
                'source_limits': self.metadata.get('limits', ''),
                'namespace': 'lombardia:6n7g-5p5e:ricovero',
                'batch_id': self.batch_id or 'anteprima non importata'}

    def validate(self):
        self.invalidate()
        try:
            self.document = preview(self.rows, self.metadata,
                                    {field: combo.currentText() for field, combo in self.columns.items()})
            tally = counts(self.document)
            self.show_frame(pd.DataFrame([dict(row['values'], row_number=row['row_number'],
                validation_status=row['status'], reasons='; '.join(row['reasons']),
                **self.provenance()) for row in self.document['records']]))
            self.status.setText(f"Fonte {tally['source']} = valide {tally['valid']} + scartate {tally['rejected']}. "
                                'Conferma salva tutte le righe e i motivi nel lotto; non importa visite.')
            self.import_button.setEnabled(True)
        except Exception as exc:
            self.document = None
            self.error(exc)

    def commit(self):
        try:
            if self.document is None:
                raise ValueError('Verificare prima la fonte e il mapping.')
            self.batch_id, inserted = self.store.import_batch(self.document)
            self.clear_result()
            self.match_button.setEnabled(True)
            self.status.setText(f"Lotto {self.batch_id[:12]}: {'importato' if inserted else 'già presente, nessun duplicato'}. "
                                'Verificare le corrispondenze per la data scelta.')
        except Exception as exc:
            self.error(exc)

    def choose_crosswalk(self, path=None):
        path = path or QFileDialog.getOpenFileName(self, 'Corrispondenze approvate (template geography_crosswalk.csv)', '', 'CSV (*.csv)')[0]
        if not path:
            return
        self.clear_result()
        try:
            tally = self.store.import_crosswalk(path)
            self.status.setText(f"Corrispondenze: {tally['source']} righe = {tally['inserted']} nuove + {tally['existing']} già presenti. "
                                'Intervalli sovrapposti saranno segnalati come ambigui.')
        except Exception as exc:
            self.error(exc)

    def match(self):
        self.clear_result()
        try:
            if self.batch_id is None:
                raise ValueError('Confermare prima il lotto in staging.')
            rows = self.store.match(self.batch_id, self.as_of.text())
            frame = pd.DataFrame([dict(row, **self.provenance()) for row in rows])
            mapped = sum(row['mapping_status'] == 'mapped' for row in rows)
            ambiguous = sum(row['mapping_status'] == 'ambiguous' for row in rows)
            ratio = f'{100 * mapped / len(rows):.1f}%' if rows else 'non definita'
            self.show_frame(frame)
            self.status.setText(f"Valide {len(rows)}: associate {mapped} ({ratio}), ambigue {ambiguous}, "
                                f"non associate {len(rows) - mapped - ambiguous}. "
                                'Denominatore: righe valide del lotto; fonte storica, nessuna conferma delle sedi attuali.')
        except Exception as exc:
            self.error(exc)

    def publish(self):
        if not self.frame.empty:
            try:
                self.publish_dataset(self.frame.copy(), 'Staging geografia Lombardia: validazione/corrispondenze con provenienza')
            except Exception as exc:
                self.error(exc)

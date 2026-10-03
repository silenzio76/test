"""Appointment tab embedded into the existing HealthReport Studio window."""
import os
from datetime import timezone
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QDateTimeEdit, QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
    QMessageBox, QHeaderView, QLabel, QFileDialog,
)
from visit_workflow import VisitStore, TRANSITIONS, STATES, ENUMS


class VisitTab(QWidget):
    def __init__(self, publish_dataset, parent=None, *, store=None):
        super().__init__(parent)
        self.publish_dataset = publish_dataset
        path = Path(os.environ.get("HEALTHREPORT_VISITS_DB", str(Path(__file__).parent / "data" / "visits.sqlite3")))
        self.store = store or VisitStore(path)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Prenotazione → conferma → accettazione → esecuzione. Identificare il paziente con un codice."))
        form = QFormLayout()
        self.patient = QLineEdit()
        self.service = QLineEdit()
        self.resource = QLineEdit()
        self.actor = QLineEdit()
        self.starts = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self.starts.setCalendarPopup(True)
        self.starts.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.duration = QSpinBox()
        self.duration.setRange(1, 480)
        self.duration.setValue(30)
        self.duration.setSuffix(" min")
        for label, field in [("Codice paziente", self.patient), ("Prestazione", self.service),
                             ("Risorsa / ambulatorio", self.resource), ("Operatore", self.actor),
                             ("Appuntamento (ora locale)", self.starts), ("Durata", self.duration)]:
            form.addRow(label, field)
        layout.addLayout(form)
        context_form = QFormLayout()
        self.context = {}
        for name, caption in [('organisation', 'Struttura / ente'), ('site', 'Sede'), ('clinician', 'Codice professionista condiviso fra sedi')]:
            self.context[name] = QLineEdit()
            context_form.addRow(caption, self.context[name])
        for name, caption in [('regime', 'Regime'), ('priority', 'Priorità'), ('access_kind', 'Accesso'), ('service_kind', 'Tipo prestazione')]:
            field = QComboBox()
            field.addItems(ENUMS[name])
            field.setCurrentIndex(field.count() - 1)
            self.context[name] = field
            context_form.addRow(caption, field)
        self.requested = QDateTimeEdit(QDateTime.currentDateTime())
        self.requested.setCalendarPopup(True)
        self.requested.setDisplayFormat('dd/MM/yyyy HH:mm')
        from PySide6.QtWidgets import QCheckBox
        self.request_known = QCheckBox('Data della richiesta verificata')
        self.request_known.setChecked(False)
        context_form.addRow(self.request_known, self.requested)
        layout.addLayout(context_form)
        actions = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItems(["Tutti"] + list(STATES))
        self.filter.currentTextChanged.connect(self.refresh)
        self.target = QComboBox()
        actions.addWidget(self.filter)
        for caption, callback in [("Prenota", self.book), ("Aggiorna", self.refresh)]:
            button = QPushButton(caption)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addWidget(self.target)
        self.change = QPushButton("Registra stato")
        self.change.clicked.connect(self.change_status)
        actions.addWidget(self.change)
        button = QPushButton("Riprogramma con data e durata del modulo")
        button.clicked.connect(self.reschedule)
        actions.addWidget(button)
        layout.addLayout(actions)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["ID", "Paziente", "Prestazione", "Risorsa", "Appuntamento", "Stato", "Eseguita il", 'Ente', 'Sede', 'Regime'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.table)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        reports = QHBoxLayout()
        for caption, callback in [("Storico selezionata", self.history),
                                  ("Invia riepilogo ai Report", self.publish),
                                  ("Esporta prenotazioni CSV", self.export),
                                  ("Verifica qualità (Pandera)", self.validate)]:
            button = QPushButton(caption)
            button.clicked.connect(callback)
            reports.addWidget(button)
        layout.addLayout(reports)
        self.refresh()

    def selected(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectionModel().selectedRows():
            raise ValueError("Selezionare una prenotazione.")
        return self.rows[row]

    def selection_changed(self):
        self.target.clear()
        try:
            self.target.addItems(TRANSITIONS[self.selected()["status"]])
        except ValueError:
            pass
        self.change.setEnabled(self.target.count() > 0)

    def refresh(self, *_):
        try:
            rows = self.store.list_visits()
            state = self.filter.currentText()
            self.rows = [row for row in rows if state == "Tutti" or row["status"] == state]
            self.table.setRowCount(0)
            for i, row in enumerate(self.rows):
                self.table.insertRow(i)
                values = [row[k] for k in ["id", "patient_code", "service", "resource", "starts_at", "status", "executed_at", 'organisation', 'site', 'regime']]
                for j, value in enumerate(values):
                    if value and j in (4, 6):
                        value = QDateTime.fromString(value, Qt.DateFormat.ISODate).toLocalTime().toString("dd/MM/yyyy HH:mm")
                    self.table.setItem(i, j, QTableWidgetItem(str(value or "")))
            counts = {s: sum(r["status"] == s for r in rows) for s in STATES}
            self.summary.setText(f"Totale: {len(rows)} | " + " | ".join(f"{s}: {n}" for s, n in counts.items()))
            self.selection_changed()
        except Exception as exc:
            QMessageBox.warning(self, "Elenco prenotazioni", str(exc))

    def run_action(self, action):
        try:
            action()
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Operazione non completata", str(exc))

    def start_time(self):
        # Qt resolves the host's local timezone/DST before conversion to UTC.
        return self.starts.dateTime().toUTC().toPython().replace(tzinfo=timezone.utc)

    def book(self):
        context = {k: (v.currentText() if isinstance(v, QComboBox) else v.text().strip()) for k, v in self.context.items()}
        for name in ('organisation', 'site'):
            context[name] = context[name] or 'NON_INDICATA'
        requested = self.requested.dateTime().toUTC().toPython().replace(tzinfo=timezone.utc) if self.request_known.isChecked() else None
        self.run_action(lambda: self.store.book(self.patient.text(), self.service.text(), self.resource.text(),
                                               self.start_time(), self.duration.value(), self.actor.text(), requested_at=requested, **context))

    def change_status(self):
        def action():
            row = self.selected()
            self.store.change_status(row["id"], self.target.currentText(), self.actor.text(), expected_status=row["status"])
        self.run_action(action)

    def reschedule(self):
        def action():
            row = self.selected()
            self.store.reschedule(row["id"], self.start_time(), self.duration.value(), self.actor.text(), expected_status=row["status"])
        self.run_action(action)

    def history(self):
        try:
            events = self.store.history(self.selected()["id"])
            text = "\n".join(f"{e['occurred_at']} | {e['actor']} | {e['old_status'] or 'creazione'} → {e['new_status']}" for e in events)
            QMessageBox.information(self, "Storico prenotazione (UTC)", text)
        except Exception as exc:
            QMessageBox.warning(self, "Storico", str(exc))

    def publish(self):
        self.run_action(lambda: self.publish_dataset(self.store.analytics(), "Flussi visite: riepilogo per prestazione e stato"))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Esporta prenotazioni", "prenotazioni.csv", "CSV (*.csv)")
        if path:
            def action():
                import tempfile
                target = Path(path)
                fd, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
                os.close(fd)
                try:
                    frame = self.store.dataframe()
                    frame.to_csv(name, index=False, encoding="utf-8-sig")
                    import pandas as pd
                    saved = pd.read_csv(name, dtype=str, keep_default_na=False)
                    if list(saved.columns) != list(frame.columns) or len(saved) != len(frame):
                        raise ValueError("Verifica esportazione fallita.")
                    os.replace(name, target)
                finally:
                    if Path(name).exists():
                        Path(name).unlink()
            self.run_action(action)

    def validate(self):
        from dependency_manager import require_optional
        if not require_optional("pandera", reason="validazione dei flussi di prenotazione"):
            return
        try:
            from visit_workflow import validate_visit_dataframe
            frame = self.store.dataframe()
            if frame.empty:
                QMessageBox.information(self, "Qualità dati", "Nessuna prenotazione da verificare.")
                return
            validate_visit_dataframe(frame)
            QMessageBox.information(self, "Qualità dati", f"Verificate {len(frame)} prenotazioni: nessun errore di schema.")
        except Exception as exc:
            QMessageBox.warning(self, "Qualità dati", str(exc))

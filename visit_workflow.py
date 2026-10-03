"""Transactional local workflow for appointments; contains no clinical records."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import uuid

STATES = ("prenotata", "confermata", "accettata", "eseguita", "annullata", "non_presentato")
TRANSITIONS = {
    "prenotata": ("confermata", "annullata", "non_presentato"),
    "confermata": ("accettata", "annullata", "non_presentato"),
    "accettata": ("eseguita", "annullata"),
    "eseguita": (), "annullata": (), "non_presentato": (),
}
DIMENSIONS = {
    'organisation': 'NON_INDICATA', 'site': 'NON_INDICATA',
    'regime': 'NON_INDICATO', 'priority': 'NON_INDICATA',
    'access_kind': 'NON_INDICATO', 'service_kind': 'NON_INDICATO',
    'clinician': '',
}
ENUMS = {
    'regime': ('SSN', 'ALPI', 'SOLVENZA', 'NON_INDICATO'),
    'priority': ('U', 'B', 'D', 'P', 'NON_INDICATA'),
    'access_kind': ('PRIMO', 'CONTROLLO', 'NON_INDICATO'),
    'service_kind': ('VISITA', 'STRUMENTALE', 'ALTRO', 'NON_INDICATO'),
}


def timestamp(value):
    """Require explicit timezone, normalize to UTC for ordering and conflicts."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Data e ora devono includere il fuso orario.")
    return value.astimezone(timezone.utc)


def required(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo obbligatorio: {label}.")
    return value.strip()


class VisitStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS visits (
                    id TEXT PRIMARY KEY, patient_code TEXT NOT NULL,
                    service TEXT NOT NULL, resource TEXT NOT NULL,
                    starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                      ('prenotata','confermata','accettata','eseguita','annullata','non_presentato')),
                    created_at TEXT NOT NULL, executed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS visit_schedule ON visits(resource, starts_at);
                CREATE TABLE IF NOT EXISTS visit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    visit_id TEXT NOT NULL REFERENCES visits(id),
                    old_status TEXT, new_status TEXT NOT NULL,
                    actor TEXT NOT NULL, occurred_at TEXT NOT NULL
                );
            """)
            # executescript ends the earlier transaction; migrate atomically.
            conn.execute('BEGIN IMMEDIATE')
            columns = {r['name'] for r in conn.execute('PRAGMA table_info(visits)')}
            for name, default in DIMENSIONS.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE visits ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")
            if 'requested_at' not in columns:
                conn.execute('ALTER TABLE visits ADD COLUMN requested_at TEXT')

    @contextmanager
    def _transaction(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _conflict(conn, patient, resource, start, end, exclude="", *, organisation='NON_INDICATA', site='NON_INDICATA', clinician=''):
        row = conn.execute("""
            SELECT id FROM visits WHERE id != ?
            AND status NOT IN ('annullata','non_presentato')
            AND ((resource = ? COLLATE NOCASE AND organisation = ? COLLATE NOCASE AND site = ? COLLATE NOCASE)
                 OR patient_code = ? COLLATE NOCASE OR (? != '' AND clinician = ? COLLATE NOCASE))
            AND starts_at < ? AND ends_at > ? LIMIT 1
        """, (exclude, resource, organisation, site, patient, clinician, clinician, end, start)).fetchone()
        if row:
            raise ValueError("Orario sovrapposto per il paziente o la risorsa.")

    def book(self, patient_code, service, resource, starts_at, duration_minutes, actor, *, now=None, requested_at=None, **dimensions):
        patient = required(patient_code, "codice paziente")
        service = required(service, "prestazione")
        resource = required(resource, "risorsa")
        actor = required(actor, "operatore")
        if set(dimensions) - set(DIMENSIONS):
            raise ValueError('Dimensioni sconosciute: ' + ', '.join(sorted(set(dimensions) - set(DIMENSIONS))))
        context = {**DIMENSIONS, **dimensions}
        for name in DIMENSIONS:
            if name == 'clinician' and not isinstance(context[name], str):
                raise ValueError('Codice professionista non valido.')
            context[name] = required(context[name], name) if name != 'clinician' else context[name].strip()
        for name, values in ENUMS.items():
            if context[name] not in values:
                raise ValueError(f'Valore non valido per {name}.')
        if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int) or not 1 <= duration_minutes <= 480:
            raise ValueError("Durata consentita: da 1 a 480 minuti interi.")
        current = timestamp(now or datetime.now(timezone.utc))
        start = timestamp(starts_at)
        requested = timestamp(requested_at) if requested_at is not None else None
        if requested is not None and requested > current:
            raise ValueError('La richiesta non può essere successiva alla prenotazione.')
        if start < current:
            raise ValueError("La nuova prenotazione non può essere nel passato.")
        end = start + timedelta(minutes=duration_minutes)
        visit_id = str(uuid.uuid4())
        with self._transaction() as conn:
            self._conflict(conn, patient, resource, start.isoformat(), end.isoformat(),
                           organisation=context['organisation'], site=context['site'], clinician=context['clinician'])
            conn.execute("INSERT INTO visits(id,patient_code,service,resource,starts_at,ends_at,status,created_at,executed_at) VALUES (?,?,?,?,?,?,?,?,?)", (
                visit_id, patient, service, resource, start.isoformat(), end.isoformat(),
                "prenotata", current.isoformat(), None))
            names = list(DIMENSIONS) + ['requested_at']
            conn.execute('UPDATE visits SET ' + ','.join(f'{name}=?' for name in names) + ' WHERE id=?',
                         tuple(context.values()) + (requested.isoformat() if requested else None, visit_id))
            conn.execute("INSERT INTO visit_events(visit_id,old_status,new_status,actor,occurred_at) VALUES (?,NULL,?,?,?)",
                         (visit_id, "prenotata", actor, current.isoformat()))
        return visit_id

    def change_status(self, visit_id, target, actor, *, expected_status, now=None):
        actor = required(actor, "operatore")
        current = timestamp(now or datetime.now(timezone.utc))
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
            if row is None:
                raise ValueError("Prenotazione non trovata.")
            if row["status"] != expected_status:
                raise ValueError("Stato modificato da un altro operatore: aggiornare l'elenco.")
            if target not in TRANSITIONS[row["status"]]:
                raise ValueError(f"Passaggio non consentito: {row['status']} → {target}.")
            if current < timestamp(row["created_at"]):
                raise ValueError("L'evento precede la creazione della prenotazione.")
            latest = conn.execute("SELECT occurred_at FROM visit_events WHERE visit_id=? ORDER BY seq DESC LIMIT 1",
                                  (visit_id,)).fetchone()
            if latest and current < timestamp(latest[0]):
                raise ValueError("L'evento precede l'ultimo aggiornamento.")
            if target in ("eseguita", "non_presentato") and current < timestamp(row["starts_at"]):
                raise ValueError("Esecuzione o assenza non registrabile prima dell'appuntamento.")
            conn.execute("UPDATE visits SET status=?, executed_at=? WHERE id=?", (
                target, current.isoformat() if target == "eseguita" else None, visit_id))
            conn.execute("INSERT INTO visit_events(visit_id,old_status,new_status,actor,occurred_at) VALUES (?,?,?,?,?)",
                         (visit_id, row["status"], target, actor, current.isoformat()))

    def reschedule(self, visit_id, starts_at, duration_minutes, actor, *, expected_status, now=None):
        actor = required(actor, "operatore")
        current = timestamp(now or datetime.now(timezone.utc))
        start = timestamp(starts_at)
        if start < current:
            raise ValueError("Il nuovo appuntamento non può essere nel passato.")
        if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int) or not 1 <= duration_minutes <= 480:
            raise ValueError("Durata consentita: da 1 a 480 minuti interi.")
        end = start + timedelta(minutes=duration_minutes)
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
            if row is None or row["status"] != expected_status:
                raise ValueError("Prenotazione assente o stato modificato: aggiornare l'elenco.")
            if row["status"] not in ("prenotata", "confermata"):
                raise ValueError("Solo le prenotazioni non accettate possono essere riprogrammate.")
            last = conn.execute("SELECT occurred_at FROM visit_events WHERE visit_id=? ORDER BY seq DESC LIMIT 1", (visit_id,)).fetchone()
            if current < timestamp(last[0]):
                raise ValueError("L'evento precede l'ultimo aggiornamento.")
            self._conflict(conn, row["patient_code"], row["resource"], start.isoformat(), end.isoformat(), visit_id,
                           organisation=row['organisation'], site=row['site'], clinician=row['clinician'])
            conn.execute("UPDATE visits SET starts_at=?, ends_at=?, status='prenotata' WHERE id=?",
                         (start.isoformat(), end.isoformat(), visit_id))
            conn.execute("INSERT INTO visit_events(visit_id,old_status,new_status,actor,occurred_at) VALUES (?,?,?,?,?)",
                         (visit_id, row["status"],
                          f"prenotata (riprogrammata: {row['starts_at']} / {row['ends_at']} → {start.isoformat()} / {end.isoformat()})",
                          actor, current.isoformat()))

    def list_visits(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM visits ORDER BY starts_at,id")]

    def history(self, visit_id):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM visit_events WHERE visit_id=? ORDER BY seq", (visit_id,))]

    def dataframe(self):
        import pandas as pd
        columns = ["id", "patient_code", "service", "resource", "starts_at", "ends_at", "status", "created_at", "executed_at"]
        columns += list(DIMENSIONS) + ['requested_at']
        return pd.DataFrame(self.list_visits(), columns=columns)

    def analytics(self):
        """Aggregate snapshot without patient identifiers; no invented predictions."""
        import pandas as pd
        df = self.dataframe()
        if df.empty:
            return pd.DataFrame(columns=["service", "status", "visits"])
        return df.groupby(["service", "status"], as_index=False).size().rename(columns={"size": "visits"})


def validate_visit_dataframe(df):
    """Optional Pandera quality check, requested explicitly by the UI."""
    import pandera.pandas as pa
    schema = pa.DataFrameSchema({
        "id": pa.Column(str, unique=True),
        "patient_code": pa.Column(str, pa.Check.str_length(min_value=1)),
        "service": pa.Column(str, pa.Check.str_length(min_value=1)),
        "resource": pa.Column(str, pa.Check.str_length(min_value=1)),
        "starts_at": pa.Column(str), "ends_at": pa.Column(str),
        "status": pa.Column(str, pa.Check.isin(STATES)),
        "created_at": pa.Column(str), "executed_at": pa.Column(str, nullable=True),
        **{name: pa.Column(str, pa.Check.isin(ENUMS[name]) if name in ENUMS else None) for name in DIMENSIONS},
        'requested_at': pa.Column(str, nullable=True),
    }, strict=True, checks=[
        pa.Check(lambda frame: frame.apply(lambda row: timestamp(row.ends_at) > timestamp(row.starts_at), axis=1).all()),
        pa.Check(lambda frame: ((frame.status == "eseguita") == frame.executed_at.notna()).all()),
    ])
    return schema.validate(df, lazy=True)

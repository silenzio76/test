"""R01/R03: immutable geography batches and explicitly reviewed crosswalks.

This database is separate from visits. No matching by name or inferred validity.
"""
from __future__ import annotations
import csv
from collections import Counter
from contextlib import contextmanager
from io import StringIO
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from lombardia_data import verify_snapshot

NAMESPACE = 'lombardia:6n7g-5p5e:ricovero'
PROFILE = {
    'external_code': 'codice_struttura_di_ricovero',
    'name': 'descrizione_struttura_di',
    'ats': 'ats_struttura', 'address': 'indirizzo',
    'postcode': 'cap', 'city': 'localita',
}
MAPPING_FIELDS = ('namespace', 'external_code', 'organisation', 'presidio', 'site',
                  'valid_from', 'valid_to', 'source', 'reviewer', 'status')


def load_geography(path):
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix.lower() == '.json':
        payload = json.loads(raw.decode('utf-8-sig'))
        if payload.get('dataset_id') != '6n7g-5p5e':
            raise ValueError('Questo incremento accetta solo il tracciato geografico 6n7g-5p5e.')
        verify_snapshot(payload)
        rows = payload['rows']
        metadata = {key: value for key, value in payload.items() if key not in ('rows', 'metadata')}
    elif path.suffix.lower() == '.csv':
        reader = csv.DictReader(StringIO(raw.decode('utf-8-sig'), newline=''))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Intestazioni CSV assenti o duplicate; usare separatore virgola.')
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise ValueError('CSV con numero di campi incoerente.')
        metadata = {'title': path.name, 'grain': 'struttura di ricovero',
                    'limits': 'Tracciato geografico dichiarato dall’utente; copertura e aggiornamento non certificati.'}
    else:
        raise ValueError('Selezionare uno snapshot JSON verificato oppure un CSV geografico.')
    if not rows:
        raise ValueError('La fonte non contiene righe.')
    metadata['file_sha256'] = hashlib.sha256(raw).hexdigest()
    metadata['filename'] = path.name
    return rows, metadata


def preview(rows, metadata, columns=None):
    columns = dict(PROFILE if columns is None else columns)
    if set(columns) != set(PROFILE) or len(set(columns.values())) != len(columns):
        raise ValueError('Mapping incompleto o colonne sorgente riutilizzate.')
    available = set().union(*(row.keys() for row in rows))
    if not set(columns.values()) <= available:
        raise ValueError('Colonne sorgente mancanti nel mapping.')
    records = []
    code_column = columns['external_code']
    code_counts = Counter(row[code_column].strip() for row in rows
                          if isinstance(row.get(code_column), str) and row[code_column].strip())
    for number, row in enumerate(rows, 1):
        values, reasons = {}, []
        for target, source in columns.items():
            value = row.get(source, '')
            if value is None:
                value = ''
            if not isinstance(value, str):
                reasons.append(f'{target}: attesa stringa, conversione non automatica')
                value = ''
            values[target] = value.strip()
        if not values['external_code'] or not values['name']:
            reasons.append('codice e denominazione obbligatori')
        code = values['external_code']
        if code and code_counts[code] > 1:
            reasons.append('codice duplicato nel lotto')
        records.append({'row_number': number, 'values': values, 'raw': row,
                        'status': 'rejected' if reasons else 'valid', 'reasons': reasons})
    document = {'namespace': NAMESPACE, 'metadata': dict(metadata), 'columns': columns,
                'records': records, 'profile_version': 1}
    return document


def counts(document):
    records = document['records']
    valid = sum(row['status'] == 'valid' for row in records)
    return {'source': len(records), 'valid': valid, 'rejected': len(records) - valid}


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class StagingStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, imported_at TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS crosswalks (
                    id TEXT PRIMARY KEY, document TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def import_batch(self, document):
        # Recompute validation: a caller cannot relabel a rejected record as valid.
        checked = preview([record['raw'] for record in document['records']],
                          document['metadata'], document['columns'])
        if checked != document:
            raise ValueError('Anteprima alterata: ripetere la validazione.')
        encoded = _encoded(checked)
        batch_id = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        with self.connect() as conn:
            inserted = conn.execute('INSERT OR IGNORE INTO batches VALUES (?, ?, ?)',
                                    (batch_id, datetime.now(timezone.utc).isoformat(), encoded)).rowcount
        return batch_id, bool(inserted)

    def batch(self, batch_id):
        with self.connect() as conn:
            row = conn.execute('SELECT document FROM batches WHERE id=?', (batch_id,)).fetchone()
        if row is None:
            raise ValueError('Lotto non trovato.')
        return json.loads(row[0])

    def import_crosswalk(self, path):
        with open(path, encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(MAPPING_FIELDS):
                raise ValueError('Usare intestazioni e ordine del template geography_crosswalk.csv.')
            rows = list(reader)
        if not rows:
            raise ValueError('Nessuna corrispondenza da importare.')
        validated = []
        for number, row in enumerate(rows, 1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Riga {number}: numero di campi incoerente.')
            row = {key: value.strip() for key, value in row.items()}
            if any(not row[key] for key in MAPPING_FIELDS if key != 'valid_to'):
                raise ValueError(f'Riga {number}: campi obbligatori mancanti.')
            if row['namespace'] != NAMESPACE or row['status'] != 'approved':
                raise ValueError(f'Riga {number}: namespace errato o revisione non approvata.')
            start = date.fromisoformat(row['valid_from'])
            end = date.fromisoformat(row['valid_to']) if row['valid_to'] else None
            if end is not None and end < start:
                raise ValueError(f'Riga {number}: intervallo di validità invertito.')
            row['valid_from'] = start.isoformat()
            row['valid_to'] = end.isoformat() if end else ''
            encoded = _encoded(row)
            validated.append((hashlib.sha256(encoded.encode('utf-8')).hexdigest(), encoded))
        # Entire file is validated before any write. Alternative matches coexist.
        with self.connect() as conn:
            before = conn.total_changes
            conn.executemany('INSERT OR IGNORE INTO crosswalks VALUES (?, ?)', validated)
            inserted = conn.total_changes - before
        return {'source': len(rows), 'inserted': inserted, 'existing': len(rows) - inserted}

    def match(self, batch_id, as_of):
        day = date.fromisoformat(as_of).isoformat()
        document = self.batch(batch_id)
        with self.connect() as conn:
            mappings = [json.loads(row[0]) for row in conn.execute('SELECT document FROM crosswalks')]
        output = []
        for record in document['records']:
            if record['status'] != 'valid':
                continue
            values = record['values']
            candidates = [row for row in mappings if row['namespace'] == document['namespace']
                          and row['external_code'] == values['external_code']
                          and row['valid_from'] <= day and (not row['valid_to'] or day <= row['valid_to'])]
            status = 'mapped' if len(candidates) == 1 else 'ambiguous' if candidates else 'unmapped'
            output.append(dict(values, mapping_status=status, candidate_count=len(candidates),
                               organisation=candidates[0]['organisation'] if status == 'mapped' else '',
                               presidio=candidates[0]['presidio'] if status == 'mapped' else '',
                               site=candidates[0]['site'] if status == 'mapped' else '',
                               as_of=day, candidates_json=_encoded(candidates)))
        return output

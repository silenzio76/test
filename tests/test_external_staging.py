import csv
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from external_staging import (NAMESPACE, PROFILE, MAPPING_FIELDS, StagingStore,
                              load_geography, preview, counts)


def source_row(code='030015-00', name='Struttura sintetica'):
    row = {value: '' for value in PROFILE.values()}
    row.update(codice_struttura_di_ricovero=code, descrizione_struttura_di=name, cap='00100')
    return row


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = StagingStore(self.path / 'staging.sqlite3')

    def crosswalk(self, rows):
        path = self.path / 'mapping.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=MAPPING_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def mapping(self, **changes):
        row = dict(namespace=NAMESPACE, external_code='030015-00', organisation='ENTE-01',
                   presidio='PRESIDIO-01', site='SEDE-01', valid_from='2018-01-01',
                   valid_to='2018-12-31', source='Documento sintetico', reviewer='TEST', status='approved')
        return dict(row, **changes)

    def test_reconciliation_rejects_all_duplicate_codes_and_preserves_strings(self):
        rows = [source_row(), source_row('000002'), source_row('DUP'), source_row('DUP'), source_row(''), source_row(123)]
        doc = preview(rows, {})
        self.assertEqual(counts(doc), {'source': 6, 'valid': 2, 'rejected': 4})
        self.assertEqual(doc['records'][1]['values']['external_code'], '000002')
        self.assertEqual(doc['records'][0]['values']['postcode'], '00100')
        self.assertEqual(doc['records'][5]['raw']['codice_struttura_di_ricovero'], 123)

    def test_batch_idempotency_versions_and_tamper_rejection(self):
        doc = preview([source_row()], {'file_sha256': 'synthetic'})
        batch_id, inserted = self.store.import_batch(doc)
        self.assertTrue(inserted)
        self.assertEqual(self.store.import_batch(doc), (batch_id, False))
        self.assertEqual(self.store.batch(batch_id), doc)
        altered = copy.deepcopy(doc)
        altered['records'][0]['values']['external_code'] = 'changed'
        with self.assertRaises(ValueError):
            self.store.import_batch(altered)
        new = preview([source_row(name='Rinominata')], {'file_sha256': 'changed'})
        self.assertNotEqual(self.store.import_batch(new)[0], batch_id)
        self.assertEqual(self.store.batch(batch_id), doc)

    def test_crosswalk_validity_ambiguity_and_idempotency(self):
        batch_id, _ = self.store.import_batch(preview([source_row(), source_row('OTHER')], {}))
        path = self.crosswalk([self.mapping()])
        self.assertEqual(self.store.import_crosswalk(path)['inserted'], 1)
        self.assertEqual(self.store.import_crosswalk(path)['existing'], 1)
        rows = self.store.match(batch_id, '2018-06-01')
        self.assertEqual([r['mapping_status'] for r in rows], ['mapped', 'unmapped'])
        self.assertEqual(self.store.match(batch_id, '2026-10-04')[0]['mapping_status'], 'unmapped')
        self.store.import_crosswalk(self.crosswalk([self.mapping(site='OTHER')]))
        ambiguous = self.store.match(batch_id, '2018-06-01')[0]
        self.assertEqual(ambiguous['mapping_status'], 'ambiguous')
        self.assertEqual(ambiguous['site'], '')
        self.assertEqual(len(json.loads(ambiguous['candidates_json'])), 2)

    def test_invalid_crosswalk_file_writes_nothing(self):
        path = self.crosswalk([self.mapping(), self.mapping(external_code='OTHER', status='proposed')])
        with self.assertRaises(ValueError):
            self.store.import_crosswalk(path)
        with self.store.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM crosswalks').fetchone()[0], 0)
        with self.assertRaises(ValueError):
            self.store.import_crosswalk(self.crosswalk([self.mapping(valid_to='2017-01-01')]))

    def test_csv_preserves_leading_zero_and_multiline_and_rejects_bad_headers(self):
        path = self.path / 'source.csv'
        row = source_row(name='Struttura\nseconda riga')
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=PROFILE.values())
            writer.writeheader()
            writer.writerow(row)
        rows, metadata = load_geography(path)
        self.assertEqual(rows, [row])
        self.assertEqual(metadata['file_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        path.write_text('a,a\n1,2\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_geography(path)

    def test_snapshot_verification(self):
        rows = [source_row()]
        payload = dict(dataset_id='6n7g-5p5e', rows=rows, source_rows=1,
                       downloaded_rows=1, query={},
                       rows_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest())
        path = self.path / 'source.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        self.assertEqual(load_geography(path)[0], rows)
        payload['rows'][0]['cap'] = 'changed'
        path.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_geography(path)

    def test_mapping_validation(self):
        with self.assertRaises(ValueError):
            preview([source_row()], {}, {'external_code': 'missing'})
        columns = dict(PROFILE, postcode=PROFILE['city'])
        with self.assertRaises(ValueError):
            preview([source_row()], {}, columns)


class StagingUITests(unittest.TestCase):
    def test_dialog_complete_flow_and_invalid_source_clears_results(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication, QMessageBox
        from external_staging_tab import GeographyImportTab
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder / 'source.csv'
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=PROFILE.values())
                writer.writeheader()
                writer.writerow(source_row())
            published = []
            dialog = GeographyImportTab(lambda frame, label: published.append(frame), staging_path=folder / 'staging.sqlite3')
            self.assertFalse(dialog.import_button.isEnabled())
            dialog.choose_source(path)
            dialog.validate()
            self.assertTrue(dialog.import_button.isEnabled())
            dialog.commit()
            first_id = dialog.batch_id
            dialog.commit()
            self.assertEqual(dialog.batch_id, first_id)
            dialog.match()
            self.assertEqual(dialog.frame.mapping_status.tolist(), ['unmapped'])
            dialog.publish()
            self.assertIn('source_file_sha256', published[0].columns)
            dialog.as_of.setText('bad-date')
            self.assertTrue(dialog.frame.empty)
            with patch.object(QMessageBox, 'warning'):
                dialog.match()
                dialog.choose_source(folder / 'missing.csv')
            self.assertFalse(dialog.import_button.isEnabled())
            self.assertFalse(dialog.match_button.isEnabled())
            self.assertTrue(dialog.frame.empty)
            dialog.close()
            app.processEvents()

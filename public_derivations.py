"""Versioned R02 recipes for observed annual SSR production, never CUP demand."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import pandas as pd
from lombardia_data import specialistica_frame, verify_snapshot

VERSION = 'annual-production/1.0'
COHORT = ['cod_ats_erogazione', 'pubb_priv']
DEFINITIONS = [
    ('volume', 'sum(volume)', ['volume'], 'prestazioni', 'Valori mancanti vietati'),
    ('source_rows', 'sum(source_rows)', ['source_rows'], 'righe sorgente', 'Valori mancanti vietati'),
    ('unknown_priority_volume', 'sum(volume dove priorità nulla/vuota/NON_INDICATA)', ['volume', 'cod_class_priorita'], 'prestazioni', 'Priorità assente conservata come non indicata'),
    ('unknown_priority_pct', '100 * unknown_priority_volume / volume', ['volume', 'cod_class_priorita'], '%', 'Nullo se volume = 0'),
    ('previous_available_year', 'lag(anno) nella stessa coorte ordinata per anno', ['anno'] + COHORT, 'anno', 'Nullo alla prima osservazione'),
    ('previous_available_volume', 'lag(volume) nella stessa coorte ordinata per anno', ['volume', 'anno'] + COHORT, 'prestazioni', 'Nullo alla prima osservazione; non implica anno consecutivo'),
    ('missing_years_count', 'anno - previous_available_year - 1', ['anno'] + COHORT, 'anni', 'Nullo alla prima osservazione; nessuna imputazione'),
    ('yoy_absolute', 'volume - previous_available_volume solo se anno precedente consecutivo', ['volume', 'anno'] + COHORT, 'prestazioni', 'Nullo alla prima osservazione o dopo anni mancanti'),
    ('yoy_pct', '100 * yoy_absolute / previous_available_volume', ['volume', 'anno'] + COHORT, '%', 'Nullo senza anno consecutivo o con base zero'),
    ('comparison_status', 'first_observation / missing_years / zero_previous_volume / comparable', ['volume', 'anno'] + COHORT, 'categoria', 'Stato esplicito, nessun valore ricostruito'),
    ('ats_label_variants', 'numero di descrizioni ATS distinte nello stesso anno/coorte', ['desc_ats_erogazione', 'anno'] + COHORT, 'descrizioni', 'Nulli/vuoti contati come descrizione non indicata'),
    ('desc_ats_erogazione', 'unione ordinata delle descrizioni distinte, separatore |', ['desc_ats_erogazione', 'anno'] + COHORT, 'testo', 'Descrizioni mancanti conservate come stringa vuota'),
    ('coverage_status', 'unverified', [], 'categoria', 'Riconciliazione numerica non certifica completezza dell’anno o coerenza delle codifiche'),
    ('derivation_version', VERSION, [], 'versione ricetta', 'Sempre presente'),
    ('input_rows_sha256', 'hash delle righe dello snapshot verificato', [], 'SHA-256', 'Sempre presente'),
]


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n'


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def derive_annual_production(payload):
    verify_snapshot(payload)
    if not payload['rows']:
        raise ValueError('Snapshot privo di righe: nessuna derivazione disponibile.')
    df = specialistica_frame(payload)
    required = set(COHORT + ['anno', 'desc_ats_erogazione', 'volume', 'source_rows'])
    if required - set(df.columns):
        raise ValueError('Schema annuale incompleto: ' + ', '.join(sorted(required - set(df.columns))))
    for column in COHORT:
        if not df[column].map(lambda value: isinstance(value, str) or pd.isna(value)).all():
            raise ValueError(f'{column}: codici e natura devono essere stringhe, senza conversione automatica.')
        df[column] = df[column].fillna('')
    for column in ('anno', 'volume', 'source_rows'):
        values = df[column]
        if values.isna().any() or not values.map(lambda value: math.isfinite(value) and value == int(value)).all():
            raise ValueError(f'{column}: richiesti interi finiti, senza valori mancanti.')
        if (values < 0).any() or (column != 'volume' and (values == 0).any()):
            raise ValueError(f'{column}: valori fuori dominio.')
        df[column] = values.astype('int64')
    if not df.anno.between(1900, 9999).all():
        raise ValueError('Anno fuori dal dominio 1900–9999.')
    df['unknown_priority_volume'] = df.volume.where(
        df.cod_class_priorita.astype(str).str.strip().isin(['', 'NON_INDICATA']), 0)
    df['desc_ats_erogazione'] = df.desc_ats_erogazione.fillna('').astype(str)
    keys = ['anno'] + COHORT
    result = df.groupby(keys, dropna=False, as_index=False).agg(
        volume=('volume', 'sum'), source_rows=('source_rows', 'sum'),
        unknown_priority_volume=('unknown_priority_volume', 'sum'),
        desc_ats_erogazione=('desc_ats_erogazione', lambda names: ' | '.join(sorted(set(names)))),
        ats_label_variants=('desc_ats_erogazione', 'nunique'))
    result = result.sort_values(COHORT + ['anno']).reset_index(drop=True)
    result['volume'] = result.volume.astype('Int64')
    result['anno'] = result.anno.astype('Int64')
    group = result.groupby(COHORT, dropna=False)
    result['previous_available_year'] = group.anno.shift().astype('Int64')
    result['previous_available_volume'] = group.volume.shift().astype('Int64')
    result['missing_years_count'] = (result.anno - result.previous_available_year - 1).astype('Int64')
    consecutive = (result.missing_years_count == 0).fillna(False)
    result['yoy_absolute'] = (result.volume - result.previous_available_volume).where(consecutive).astype('Int64')
    result['yoy_pct'] = (100 * result.yoy_absolute / result.previous_available_volume.where(result.previous_available_volume > 0)).astype('Float64')
    result['unknown_priority_pct'] = (100 * result.unknown_priority_volume / result.volume.where(result.volume > 0)).astype('Float64')
    result['comparison_status'] = 'comparable'
    result.loc[result.previous_available_year.isna(), 'comparison_status'] = 'first_observation'
    result.loc[(result.missing_years_count > 0).fillna(False), 'comparison_status'] = 'missing_years'
    result.loc[consecutive & (result.previous_available_volume == 0).fillna(False), 'comparison_status'] = 'zero_previous_volume'
    result['coverage_status'] = 'unverified'
    result['derivation_version'] = VERSION
    result['input_rows_sha256'] = payload['rows_sha256']
    # Reconcile each observed year, not only the overall total.
    source_totals = df.groupby('anno')[['volume', 'source_rows']].sum()
    derived_totals = result.groupby('anno')[['volume', 'source_rows']].sum()
    if not source_totals.reset_index().astype('Int64').equals(derived_totals.reset_index().astype('Int64')):
        raise ValueError('Totali annuali non riconciliati con lo snapshot.')
    reconciled = [{'anno': int(year), 'source_volume': int(row.volume),
                   'derived_volume': int(derived_totals.loc[year, 'volume']),
                   'source_rows': int(row.source_rows),
                   'derived_source_rows': int(derived_totals.loc[year, 'source_rows'])}
                  for year, row in source_totals.iterrows()]
    recipe = {
        'version': VERSION, 'dataset_id': payload['dataset_id'],
        'input_rows_sha256': payload['rows_sha256'],
        'source_metadata': {key: payload.get(key) for key in ['title', 'source_url', 'license', 'retrieved_at', 'source_updated_at', 'query', 'limits']},
        'source_grain': payload.get('grain', 'anno × ATS × natura × branca × priorità'),
        'output_grain': 'anno × codice ATS × natura erogatore', 'cohort': COHORT,
        'unit': 'prestazioni erogate SSR, non pazienti o richieste CUP',
        'observed_years': sorted(int(year) for year in source_totals.index),
        'input_aggregate_rows': len(df), 'output_rows': len(result),
        'source_rows': int(df.source_rows.sum()), 'reconciliation_by_year': reconciled,
        'columns': [dict(column=name, formula=formula, source_columns=columns, unit=unit,
                         null_rule=null, version=VERSION) for name, formula, columns, unit, null in DEFINITIONS],
        'limits': [
            'Dati pubblici annuali di produzione; nessuna domanda settimanale/no-show inferita.',
            'Anni mancanti non creati o imputati; il precedente disponibile resta solo contesto.',
            'Codice ATS e natura definiscono la coorte; cambi di denominazione non creano una coorte nuova.',
            'Etichette multiple sono segnalate, senza equivalenze anagrafiche implicite.',
            'Completezza del singolo anno e confrontabilità delle codifiche non certificate dai totali.',
            'Nessuna imputazione, formula arbitraria o modello addestrato.',
        ],
    }
    return result, recipe


def export_derivation_package(payload, output):
    """Validate all files in a sibling temporary folder, then publish one directory.

    Deterministic content address. An existing package is verified, never replaced.
    A failed validation/write preserves existing packages and the input snapshot.
    """
    frame, recipe = derive_annual_production(payload)
    files = {
        'source.json': _json(payload).encode('utf-8'),
        'annual.csv': frame.to_csv(index=False, lineterminator='\n').encode('utf-8'),
        'recipe.json': _json(recipe).encode('utf-8'),
    }
    manifest = {'version': VERSION, 'dataset_id': payload['dataset_id'],
                'rows': len(frame), 'columns': list(frame.columns),
                'files_sha256': {name: _digest(content) for name, content in files.items()}}
    manifest_bytes = _json(manifest).encode('utf-8')
    destination = Path(output) / ('annual-production-' + _digest(manifest_bytes)[:24])

    def validate(folder):
        if json.loads((folder / 'manifest.json').read_text(encoding='utf-8')) != manifest:
            raise ValueError('Manifest del pacchetto esistente non coerente.')
        for name, content in files.items():
            if _digest((folder / name).read_bytes()) != _digest(content):
                raise ValueError(f'Pacchetto alterato: {name}. Nessuna sovrascrittura.')
        restored = json.loads((folder / 'source.json').read_text(encoding='utf-8'))
        verify_snapshot(restored)
        if restored != payload:
            raise ValueError('La fonte non è stata preservata.')
        reader = csv.reader(io.StringIO((folder / 'annual.csv').read_text(encoding='utf-8'), newline=''))
        if next(reader) != list(frame.columns):
            raise ValueError('Intestazioni export non coerenti.')
        rows = list(reader)
        if len(rows) != len(frame) or any(len(row) != len(frame.columns) for row in rows):
            raise ValueError('Righe export non riconciliate.')

    parent = Path(output)
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        validate(destination)
        return destination
    temporary = Path(tempfile.mkdtemp(prefix='.annual-production-', dir=parent))
    try:
        for name, content in files.items():
            (temporary / name).write_bytes(content)
        (temporary / 'manifest.json').write_bytes(manifest_bytes)
        validate(temporary)
        if destination.exists():
            validate(destination)
        else:
            os.replace(temporary, destination)
    finally:
        if temporary.exists():
            # Generated temporary sibling only; never remove a selected output.
            assert temporary.resolve().parent == parent.resolve()
            assert temporary.name.startswith('.annual-production-')
            shutil.rmtree(temporary)
    return destination


if __name__ == '__main__':
    import argparse
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description='Derivazioni SSR annuali con dati originali e ricetta versionata.')
    parser.add_argument('--source', type=Path, default=root / 'data' / 'public' / 'specialistica.json')
    parser.add_argument('--output', type=Path, default=root / 'data' / 'derived')
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding='utf-8'))
    print(export_derivation_package(payload, args.output))

"""Build reproducible public production reports; never combine overlapping sources."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import pandas as pd
from lombardia_data import verify_snapshot, specialistica_frame, atomic_json
from healthcare_statistics import public_annual_report


def atomic_text(path, value, *, csv=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(value)
        restored = Path(name).read_text(encoding='utf-8')
        if restored != value:
            raise ValueError('Verifica scrittura fallita.')
        if csv:
            pd.read_csv(io.StringIO(restored))
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def build(source, output):
    source, output = Path(source), Path(output)
    catalog = []
    for path in sorted(source.glob('*.json')):
        payload = json.loads(path.read_text(encoding='utf-8'))
        verify_snapshot(payload)
        catalog.append({k: payload[k] for k in ['dataset_id', 'title', 'license', 'source_url', 'retrieved_at', 'source_updated_at', 'grain', 'limits', 'source_rows', 'downloaded_rows', 'rows_sha256']})
    payload = json.loads((source/'specialistica.json').read_text(encoding='utf-8'))
    verify_snapshot(payload)
    frame = specialistica_frame(payload)
    annual = public_annual_report(frame)
    year = int(frame.anno.max())
    latest = frame.loc[frame.anno == year].groupby(['anno', 'cod_branca', 'desc_branca', 'cod_class_priorita'], dropna=False, as_index=False).agg(volume=('volume', 'sum'), source_rows=('source_rows', 'sum'))
    totals = frame.groupby('anno', as_index=False).volume.sum()
    artifacts = {'produzione_ats_annuale.csv': annual, 'produzione_branca_priorita_ultimo_anno.csv': latest, 'produzione_regionale_annuale.csv': totals}
    hashes = {}
    for name, df in artifacts.items():
        content = df.to_csv(index=False, lineterminator='\n')
        atomic_text(output/name, content, csv=True)
        hashes[name] = hashlib.sha256(content.encode()).hexdigest()
    atomic_json(output/'sources.json', {'datasets': catalog, 'report_sha256': hashes})
    number = lambda v: f'{int(v):,}'.replace(',', '.')
    lines = ['# Estrazione e analisi dei dati pubblici lombardi', '',
             f"Snapshot recuperato: {payload['retrieved_at']}; ultimo aggiornamento fonte: {payload['source_updated_at']}.", '',
             'Analisi descrittiva della produzione SSR, senza stime dei tempi di attesa o della domanda non soddisfatta.', '',
             '| Dataset | Righe sorgente | Righe recuperate | Licenza |', '|---|---:|---:|---|']
    for item in catalog:
        lines.append(f"| [{item['title']}]({item['source_url']}) | {number(item['source_rows'])} | {number(item['downloaded_rows'])} | {item['license']} |")
    lines += ['', '## Produzione annuale del dataset Specialistica per Erogatore', '', '| Anno | Quantità prestazioni SSR |', '|---|---:|']
    for row in totals.itertuples(index=False):
        lines.append(f'| {int(row.anno)} | {number(row.volume)} |')
    missing = frame.loc[frame.anno == year].loc[lambda df: df.cod_class_priorita == 'NON_INDICATA', 'volume'].sum()
    total = totals.loc[totals.anno == year, 'volume'].iloc[0]
    lines += ['', f'Nel {year}, la priorità non indicata riguarda {number(missing)} prestazioni su {number(total)} ({missing/total:.1%}). Non è riclassificata automaticamente come P. La quota globale comprende attività per cui la priorità potrebbe non essere applicabile; non dimostra omissioni sui primi accessi monitorati.', '',
              '## Interpretazione', '',
              '- Le quantità sono prestazioni, non pazienti distinti né richieste CUP.',
              '- pubb_priv è la natura dell’erogatore; il dataset riguarda produzione SSR anche quando l’erogatore è privato.',
              '- I due dataset di volumi si sovrappongono: restano separati e non sono sommati.',
              '- Le variazioni annuali richiedono verifica di copertura, codifiche e mix. Non dimostrano da sole qualità, efficienza o un effetto causale.',
              '- La geografia è storica e riferita alle strutture di ricovero; richiede anagrafica aggiornata per le sedi ambulatoriali.',
              '- Gli snapshot conservano query, metadati e SHA-256; la somma di source_rows deve coincidere con il conteggio della fonte.',
              '- La riduzione delle righe per i volumi è un’aggregazione completa lato fonte, non un campionamento.', '',
              'Rigenerazione: `python lombardia_data.py` seguito da `python build_public_analysis.py`.']
    atomic_text(output/'LOMBARDIA_DATA_REPORT.md', '\n'.join(lines)+'\n')
    return output/'LOMBARDIA_DATA_REPORT.md'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    root = Path(__file__).parent
    parser.add_argument('--source', default=str(root/'data'/'public'))
    parser.add_argument('--output', default=str(root/'reports'))
    args = parser.parse_args()
    print(build(args.source, args.output))

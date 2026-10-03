"""Reproducible snapshots of official Lombardy public datasets, via Socrata EU."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://www.dati.lombardia.it"
DATASETS = {
    "specialistica": {
        "id": "qm4z-s92m",
        "select": "anno,cod_ats_erogazione,desc_ats_erogazione,pubb_priv,cod_branca,desc_branca,cod_class_priorita,sum(qta_tot::number) as volume,count(*) as source_rows",
        "group": "anno,cod_ats_erogazione,desc_ats_erogazione,pubb_priv,cod_branca,desc_branca,cod_class_priorita",
        "order": "anno,cod_ats_erogazione,pubb_priv,cod_branca,cod_class_priorita,desc_ats_erogazione,desc_branca",
        "grain": "anno × ATS × natura erogatore × branca × priorità",
        "limits": "Solo produzione SSR aggregata; niente ALPI, prenotazioni individuali, no-show o tempi di attesa. Esclusi PS, screening e neuropsichiatria infantile secondo metadati.",
    },
    "volumi_storici": {
        "id": "hdbq-kes5",
        "select": "anno,codice_ats_erogazione,descrizione_ats_erogazione,descrizione_tipologia_erogatore,codice_branca,descrizione_branca,sum(prestazioni_tot) as volume,count(*) as source_rows",
        "group": "anno,codice_ats_erogazione,descrizione_ats_erogazione,descrizione_tipologia_erogatore,codice_branca,descrizione_branca",
        "order": "anno,codice_ats_erogazione,descrizione_tipologia_erogatore,codice_branca,descrizione_branca,descrizione_ats_erogazione",
        "grain": "anno × ATS × tipologia erogatore × branca",
        "limits": "Produzione storica, non capacità prenotabile. Sovrapposta temporalmente al dataset specialistica: non sommare i due dataset.",
    },
    "geografia": {"id": "6n7g-5p5e", "order": ":id", "grain": "struttura di ricovero", "limits": "Anagrafica geografica storica; non censisce tutte le sedi ambulatoriali attuali. Nessun abbinamento automatico solo per nome."},
}


def fetch_json(url):
    # Retry only transient network/server failures; no mutations in these calls.
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
    from urllib.error import URLError

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=4),
           retry=retry_if_exception_type((URLError, TimeoutError)), reraise=True)
    def read():
        with urlopen(Request(url, headers={"User-Agent": "HealthReportStudio-public-data/1.0"}), timeout=45) as response:
            return json.load(response)
    return read()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        with open(name, encoding="utf-8") as stream:
            json.load(stream)
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def snapshot(key, output, fetch=fetch_json):
    config = DATASETS[key]
    dataset_id = config["id"]
    metadata = fetch(f"{BASE}/api/views/{dataset_id}.json")
    if metadata.get("id") != dataset_id or not metadata.get("licenseId"):
        raise ValueError("Metadati mancanti o dataset non identificato.")
    query = {"$order": config["order"]}
    for name in ("select", "group"):
        if name in config:
            query["$" + name] = config[name]
    count = fetch(f"{BASE}/resource/{dataset_id}.json?" + urlencode({"$select": "count(*) as rows"}))
    expected = int(count[0]["rows"])
    rows = []
    offset, page_size = 0, 5000
    while True:
        page_query = dict(query, **{"$limit": page_size, "$offset": offset})
        page = fetch(f"{BASE}/resource/{dataset_id}.json?" + urlencode(page_query))
        if not isinstance(page, list):
            raise ValueError("Risposta dati non tabellare.")
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    observed = sum(int(row["source_rows"]) for row in rows) if "group" in config else len(rows)
    if 'group' in config:
        dimensions = config['group'].split(',')
        keys = [tuple(row.get(name) for name in dimensions) for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError('Gruppi duplicati fra pagine: snapshot non affidabile.')
    if observed != expected:
        raise ValueError(f"Snapshot incompleto o fonte cambiata durante la lettura: {observed}/{expected}.")
    after = fetch(f"{BASE}/api/views/{dataset_id}.json")
    if after.get("rowsUpdatedAt") != metadata.get("rowsUpdatedAt"):
        raise ValueError("Fonte aggiornata durante il download: ripetere lo snapshot.")
    payload = {
        "dataset_id": dataset_id, "title": metadata.get("name"), "license": metadata["licenseId"],
        "source_url": f"{BASE}/d/{dataset_id}", "metadata_url": f"{BASE}/api/views/{dataset_id}.json",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_updated_at": datetime.fromtimestamp(metadata["rowsUpdatedAt"], timezone.utc).isoformat(),
        "query": query, "grain": config["grain"], "limits": config["limits"],
        "source_rows": expected, "downloaded_rows": len(rows), "rows": rows,
        "metadata": metadata,
    }
    payload["rows_sha256"] = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    path = Path(output) / f"{key}.json"
    atomic_json(path, payload)
    return path, payload


def specialistica_frame(payload):
    import pandas as pd
    if payload.get("dataset_id") != DATASETS["specialistica"]["id"]:
        raise ValueError("Dataset non compatibile con lo schema di specialistica.")
    df = pd.DataFrame(payload["rows"])
    for column in ("anno", "volume", "source_rows"):
        df[column] = pd.to_numeric(df[column], errors="raise")
    if (df.volume < 0).any() or (df.source_rows <= 0).any():
        raise ValueError("Quantità non valide.")
    # Missing priority is preserved as unknown, never recoded to P.
    df["cod_class_priorita"] = df.get("cod_class_priorita", pd.Series(index=df.index, dtype=str)).fillna("NON_INDICATA").replace('', 'NON_INDICATA')
    return df


def verify_snapshot(payload):
    rows = payload['rows']
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    if digest != payload['rows_sha256'] or len(rows) != payload['downloaded_rows']:
        raise ValueError('Snapshot alterato o incompleto.')
    observed = sum(int(r['source_rows']) for r in rows) if '$group' in payload['query'] else len(rows)
    if observed != payload['source_rows']:
        raise ValueError('Copertura sorgente non verificata.')
    if '$group' in payload['query']:
        dimensions = payload['query']['$group'].split(',')
        keys = [tuple(row.get(name) for name in dimensions) for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError('Gruppi duplicati nello snapshot.')
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(Path(__file__).parent / "data" / "public"))
    parser.add_argument("--dataset", choices=list(DATASETS) + ["all"], default="all")
    args = parser.parse_args()
    for key in DATASETS if args.dataset == "all" else [args.dataset]:
        path, payload = snapshot(key, args.output)
        print(f"{key}: {payload['downloaded_rows']} righe scaricate, {payload['source_rows']} righe sorgente; {path}", flush=True)

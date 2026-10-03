# Estrazione e analisi dei dati pubblici lombardi

Snapshot recuperato: 2026-10-03T13:25:45.546797+00:00; ultimo aggiornamento fonte: 2026-03-23T13:05:06+00:00.

Analisi descrittiva della produzione SSR, senza stime dei tempi di attesa o della domanda non soddisfatta.

| Dataset | Righe sorgente | Righe recuperate | Licenza |
|---|---:|---:|---|
| [Georeferenziazione strutture](https://www.dati.lombardia.it/d/6n7g-5p5e) | 212 | 212 | CC0_10 |
| [Specialistica per Erogatore](https://www.dati.lombardia.it/d/qm4z-s92m) | 804.902 | 22.673 | CC0_10 |
| [Volumi Prestazioni Specialistica Ambulatoriale in Regione Lombardia](https://www.dati.lombardia.it/d/hdbq-kes5) | 1.566.900 | 7.509 | CC0_10 |

## Produzione annuale del dataset Specialistica per Erogatore

| Anno | Quantità prestazioni SSR |
|---|---:|
| 2016 | 132.205.878 |
| 2017 | 133.358.752 |
| 2018 | 136.372.424 |
| 2019 | 138.051.599 |
| 2020 | 111.138.583 |
| 2021 | 146.296.098 |
| 2022 | 145.953.546 |
| 2023 | 150.656.190 |
| 2024 | 155.729.106 |
| 2025 | 153.712.659 |

Nel 2025, la priorità non indicata riguarda 122.122.061 prestazioni su 153.712.659 (79.4%). Non è riclassificata automaticamente come P. La quota globale comprende attività per cui la priorità potrebbe non essere applicabile; non dimostra omissioni sui primi accessi monitorati.

## Interpretazione

- Le quantità sono prestazioni, non pazienti distinti né richieste CUP.
- pubb_priv è la natura dell’erogatore; il dataset riguarda produzione SSR anche quando l’erogatore è privato.
- I due dataset di volumi si sovrappongono: restano separati e non sono sommati.
- Le variazioni annuali richiedono verifica di copertura, codifiche e mix. Non dimostrano da sole qualità, efficienza o un effetto causale.
- La geografia è storica e riferita alle strutture di ricovero; richiede anagrafica aggiornata per le sedi ambulatoriali.
- Gli snapshot conservano query, metadati e SHA-256; la somma di source_rows deve coincidere con il conteggio della fonte.
- La riduzione delle righe per i volumi è un’aggregazione completa lato fonte, non un campionamento.

Rigenerazione: `python lombardia_data.py` seguito da `python build_public_analysis.py`.

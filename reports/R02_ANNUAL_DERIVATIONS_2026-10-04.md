# R02 — derivazioni annuali della produzione SSR, 4 ottobre 2026

Classe Gialla. Incremento locale sul progetto lavoro; modifiche R01/R03 e R11/R12 precedenti preservate. Nessun commit o push effettuato in questa sessione. L'assenza dell'estratto aziendale non blocca questa ricetta pubblica; le funzioni che lo richiedono restano pianificate.

## Implementato e verificato

Ricetta `annual-production/1.0` in `public_derivations.py`. Fonte: snapshot locale verificato `qm4z-s92m`, *Specialistica per Erogatore*, con hash righe `bb36be8b14bcc687453d8d4b5de4e9d0a83c22e1d928479bb9e9c3b6ffed4221`. Il dataset contiene produzione SSR, non richieste CUP individuali. Originali e metadati rimangono nel pacchetto esportato.

22.673 aggregati → **161 righe annuali**, con **804.902 righe sorgente** riconciliate. Coorte definita da codice ATS e natura dell'erogatore; codici testuali, incluse eventuali cifre iniziali zero, preservati. Cambi di denominazione non spezzano la coorte; descrizioni multiple sono segnalate. Pubblico/privato non diventa SSN/ALPI.

Colonne derivate: precedente anno/volume disponibile, conteggio anni mancanti fra osservazioni, variazione assoluta/percentuale anno su anno, quota di priorità non indicata, stato del confronto, numero di denominazioni ATS, versione e hash input. Non creati anni o volumi assenti. Percentuale nulla senza anno precedente consecutivo o con base zero. Copertura annuale sempre dichiarata non certificata.

| Anno | Volume sorgente = volume derivato | Righe sorgente = conteggio derivato |
|---|---:|---:|
| 2016 | 132205878 | 73168 |
| 2017 | 133358752 | 77902 |
| 2018 | 136372424 | 78510 |
| 2019 | 138051599 | 79196 |
| 2020 | 111138583 | 78695 |
| 2021 | 146296098 | 77446 |
| 2022 | 145953546 | 78870 |
| 2023 | 150656190 | 77111 |
| 2024 | 155729106 | 79448 |
| 2025 | 153712659 | 104556 |

Stati osservati: 144 confronti consecutivi, 17 prime osservazioni; nessun confronto con anni mancanti o base zero in questo snapshot. La loro gestione è verificata su fixture sintetiche. Queste quantità descrivono il file acquisito, senza certificare la completezza dell'intero anno o la comparabilità delle codifiche.

Pacchetto reale locale: `data/derived/annual-production-debe2035467b5f5efc2204fe`. Contiene `source.json`, `annual.csv`, `recipe.json`, `manifest.json`; seconda esecuzione CLI restituisce e verifica lo stesso pacchetto. Tutti i file sono preparati e validati in una cartella temporanea nello stesso parent, poi pubblicati con rinomina atomica. Un pacchetto esistente alterato viene respinto, non sovrascritto. Dati operativi non modificati; pacchetti completi sotto `data` esclusi da Git.

## R11/R12 e validazione

- GUI: Statistica e ML → Derivazioni annuali SSR → Genera e verifica colonne. Risultati e Regole e unità separati, export dedicato disponibile dopo successo; cambio di fonte/errore invalida ricetta, export e pubblicazione precedenti.
- Esportazione dedicata conserva dati originali e metadati insieme; il generico Invio ai Report conserva la tabella e il flusso precedente, senza pretendere che ogni formato generico includa l'intero pacchetto.
- **46 test passati**: sei nuovi test su anni mancanti, zero denominatore, coorti, denominazioni, riconciliazione, input invalidi, hash, originali/zeri iniziali, export idempotente, corruzione, fallimento di rinomina, pulizia dei temporanei e stato UI.
- Smoke della finestra principale passato; smoke workspace esteso alla ricetta e al pacchetto annuale passato, incluse navigazione, import da tastiera, invio ai Report e callback dei sette formati generici.
- QA visivo offscreen della tabella regole, 1200×800; smoke verifica anche dimensioni effettive 1000×700. Solo dati sintetici nei test UI. Nessun collaudo manuale nativo/DPI multipli.
- Durante la verifica corretto un falso fallimento della riconciliazione dovuto al confronto fra indici pandas con tipi diversi, conservando il confronto esatto degli interi. La suite finale è passata dopo la correzione.
- Nessuna nuova dipendenza; pandas/PySide6 già core, gestione file standard library. Profili scientifici e librerie opzionali preservati. Matrice d'installazione multipiattaforma e profilo opzionale completo non rieseguiti.
- Nessun file candidato alla rimozione dimostrato obsoleto in questo incremento; la pulizia della sessione precedente resta tracciata. Diff controllato, nessun dato operativo aggiunto al contenuto versionabile.

## Limiti e prossimo passo

R02 completato per questa ricetta fissa, **parziale** rispetto al catalogo generale. Formule editabili, ricodifiche/join ulteriori, altre fonti e granularità restano pianificati. R03/R04 interni, domanda/no-show R06 e scenari con capacità reale non dichiarati completati. Un incremento possibile senza CUP è la reportistica descrittiva R10 sui dati pubblici verificati; non richiede addestrare modelli o inventare dati.

Quota: 79% settimanale/58% breve all'inizio, 77%/45% al controllo finale; consumo arrotondato 2/13 punti. Stima iniziale 2–4 punti settimanali: consumo rilevato entro il limite inferiore della stima, senza equivalenza con un conteggio esatto dei token. Progetto prevalente nella sessione: lavoro; confronto globale indisponibile. Reset settimanale effettivo 10 ottobre 2026 ore 13:07 Europe/Rome. Massimo settimanale in token non definito, allowance in token non calcolabile. Prossima sessione normale e circoscritta; University e riserva protette.

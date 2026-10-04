# HealthReport Studio — incremento del 4 ottobre 2026

Consegna su `main` del repository `silenzio76/test`, autorizzata dall'utente il 4 ottobre 2026. Classe Green per la pubblicazione del lavoro Giallo già completato. Nessun nuovo modello, estratto CUP aziendale o dato operativo incluso.

## Comportamento disponibile

- R01/R03, primo incremento: importazione geografica JSON/CSV con mapping, anteprima, scarti, lotti immutabili idempotenti in staging separato; corrispondenze dichiarate revisionate per codice/periodo, ambiguità e copertura esplicite. Nessuna associazione inventata né scrittura sulle visite.
- R11: cinque aree native (dati, import/anagrafiche, visite, statistica, report), navigazione semantica, intestazioni/stile condivisi, modulo visite scorrevole, fonte/metodo selezionabili e gestione dei risultati obsoleti dopo errore/cambio di analisi. Export generici raccolti in un selettore; invio ai Report apre l'area corretta.
- R12: eliminati 16 file obsoleti verificati (ribbon scollegata, risorse/icone/documentazione e tre bytecode Python 3.13); dialog import sostituito dalla pagina dedicata; metodo ML placeholder morto rimosso. Dati, fonti, migrazioni, template necessari e dipendenze core/opzionali preservati.
- R02, ricetta annuale: derivazioni versionate su produzione SSR pubblica, precedenti annuali e buchi temporali, percentuali con denominatori espliciti, riconciliazione per anno e anteprima delle regole/unità. Export dedicato atomico con snapshot originale, CSV, ricetta e manifest con hash; nessuna settimana CUP o etichetta no-show ricostruita.

R01/R02/R03 restano parziali rispetto al catalogo completo della roadmap; R11/R12 restano ricorrenti. Specifiche e limiti nei report [R01/R03](reports/R01_R03_INCREMENT_2026-10-04.md), [R11/R12](reports/R11_R12_WORKSPACE_2026-10-04.md) e [R02](reports/R02_ANNUAL_DERIVATIONS_2026-10-04.md).

## Esiti della checklist permanente

**Interfaccia R11:** schermate/comandi allineati alle funzioni disponibili; flussi visite, import, indicatori, ML esistente e invio ai Report verificati da test e smoke. Controllati layout offscreen a 1200×800 e 1000×700, scorrimento, testo, focus e import tramite tastiera; stati vuoti/errori invalidano risultati esportabili precedenti. Dati osservati distinti da previsioni. Collaudo manuale nativo, screen reader e DPI multipli non eseguiti.

**File e dipendenze R12:** riferimenti diretti, dinamici, opzionali, test e documentazione verificati prima della rimozione; avvio e flussi interessati provati dopo. Nessuna dipendenza aggiunta/rimossa e nessuna installazione opzionale richiesta. Ambiente verificato: Python 3.14, PySide6 6.11.2, pandas 3.0.5; installabilità dell'intera matrice Python e dei profili scientifici completa non verificata. Font esplicito nel solo QA offscreen. DB/cloud reali e generazione effettiva di tutti gli export opzionali non collaudati in questo incremento; instradamenti dei sette formati verificati.

**Validazione finale prima del commit:** `python -m unittest discover -s tests -q` — 46 test superati; `python tests/smoke_main_window.py` e `python tests/smoke_workspace_ui.py` — superati. Diff e contenuto del commit verificati; database, raw snapshot, pacchetti completi locali, immagini QA e registri quota locali esclusi. Le estrazioni reali pubbliche sono state validate localmente e documentate con conteggi/hash, senza aggiungere i raw al repository.

**Chiusura:** confronto con `origin/main` eseguito prima del commit; pubblicazione con normale push, senza riscrittura della storia. Esito e hash effettivi sono registrati nel checkpoint locale e nella risposta di chiusura. Nessuna release/tag separata richiesta.

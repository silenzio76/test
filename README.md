# HealthReport Studio — flussi di visite sanitarie

Sottoprogetto di `lavoro`, integrato dalla copia del repository https://github.com/silenzio76/test al commit `6090b2fd6424ac09999d74bbeb071d7a03d925a0` (main), il 3 ottobre 2026. L'origine Git resta collegata al repository dell'utente.

## Funzione aggiunta

La scheda **Visite sanitarie** permette di prenotare una prestazione, confermarla, registrare l'accettazione e poi l'esecuzione. Sono previste annullamento, mancata presentazione, riprogrammazione prima dell'accettazione, filtro per stato, storico delle operazioni ed esportazione CSV.

Ogni prenotazione contiene codice paziente, prestazione, risorsa/ambulatorio, data e ora, durata e stato, ente, sede, regime (SSN/ALPI/SOLVENZA), priorità, tipo di accesso e prestazione. La data della richiesta è facoltativa e deve essere verificata. Le date sono conservate in UTC e mostrate nell'ora locale del computer. La risorsa è una singola capacità prenotabile dentro una coppia ente/sede. Sono bloccate sovrapposizioni della stessa risorsa nella stessa sede, dello stesso paziente e dello stesso codice professionista anche fra sedi e regimi diversi. Due appuntamenti consecutivi sono consentiti; i tempi di trasferimento fra sedi richiedono una configurazione successiva. Prenotazioni annullate o con mancata presentazione liberano l'intervallo. I codici sono confrontati senza distinzione tra maiuscole e minuscole. La migrazione SQLite conserva i dati precedenti: i metadati assenti diventano non indicati, la richiesta rimane nulla.

Transizioni consentite:

```text
prenotata → confermata → accettata → eseguita
prenotata / confermata → annullata oppure non_presentato
accettata → annullata
```

Gli stati finali non possono essere riaperti. Per riprogrammare, selezionare la visita e impostare data e durata nel modulo: la visita torna a `prenotata`. Esecuzione e mancata presentazione non sono consentite prima dell'appuntamento. Ogni modifica è transazionale e conserva operatore e orario; uno stato cambiato da un'altra sessione fa fallire l'aggiornamento obsoleto.

## Collegamento all'analisi esistente

**Invia riepilogo ai Report** carica nel flusso Data Query/ETL/Report già esistente un conteggio per prestazione e stato, senza codici paziente. Il CSV completo delle prenotazioni è una funzione distinta. Le trasformazioni ETL dei riepiloghi non modificano il registro operativo.

**Verifica qualità (Pandera)** controlla unicità degli ID, campi, stati, ordine degli orari e coerenza dell'esecuzione. pandas viene usato per dataset e aggregazioni; i grafici e le analisi del report originale rimangono disponibili. La scheda **Statistica e ML** offre indicatori operativi stratificati, produzione regionale e validazione di previsioni della domanda. Nessun modello viene addestrato sui pazienti automaticamente.

## Spazio di lavoro — aggiornamento 4 ottobre 2026

La navigazione distingue cinque aree: **Dati e trasformazioni**, **Import e anagrafiche**, **Visite sanitarie**, **Statistica e ML**, **Report**. La barra superiore mostra il dataset corrente e la sua numerosità. L'importazione geografica è una pagina persistente: cambiare area mantiene il lotto e l'anteprima. Nelle visite il modulo scorre a sinistra, mentre elenco e azioni restano a destra; la richiesta non verificata ha il campo data disabilitato. La statistica separa registro, produzione pubblica e domanda settimanale, con pubblicazione e previsioni abilitate solo quando disponibili. Errori o cambi di analisi invalidano la tabella precedente.

**Invia ai Report** apre l'area Report e carica la tabella nel dataset analitico condiviso, sostituendo quello precedente e azzerando i passi ETL come già previsto dal flusso originale. I sette formati di esportazione sono raccolti in un selettore. Dati/Report e modulo visite hanno scorrimento per finestre piccole. Il modulo condiviso `workspace_ui.py` gestisce stile e intestazioni; `external_staging_tab.py` contiene l'importazione separata. Gli incrementi futuri vanno aggiunti all'area pertinente e registrati nella roadmap, senza mostrare comandi per funzioni ancora assenti.

Rimossi ribbon scollegata, manifesto e icone inutilizzati, relativa documentazione e tre bytecode Python 3.13 tracciati. Eliminato il vecchio placeholder ML; il modulo dialog dell'importazione è sostituito dalla pagina dedicata. Nessuna dipendenza rimossa: gli usi dinamici e facoltativi sono ancora necessari. Controlli e limiti: [verifica R11/R12](reports/R11_R12_WORKSPACE_2026-10-04.md).

## Avvio

Python 3.10 o successivo, con versioni delle dipendenze compatibili con l'interprete scelto.

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Su Linux/macOS usare `.venv/bin/python`. Eseguire dalla cartella del sottoprogetto, come per l'app originale. Il database viene creato al primo avvio in `data/visits.sqlite3`; per usare un altro percorso impostare `HEALTHREPORT_VISITS_DB`. Database e artefatti temporanei sono esclusi da Git; i tre bytecode Python 3.13 ereditati dall'originale sono stati rimossi nella pulizia del 4 ottobre.

Per il profilo scientifico dell'allegato:

```text
.venv\Scripts\python -m pip install -r requirements_analysis.txt
```

Tutti i pacchetti dell'allegato sono inclusi nel profilo facoltativo e quelli mancanti dal core appaiono nel gestore delle dipendenze opzionali. `pandera[pandas]` aggiunge il backend pandas. `imbalanced-learn` viene correttamente risolto come modulo `imblearn`. Le librerie ML e notebook non sono scaricate obbligatoriamente all'avvio. Non è stata richiesta né effettuata un'installazione completa del profilo scientifico.

## Verifica

```text
python -m unittest discover -s tests -v
```

I test del dominio usano database temporanei e dati sintetici. Il test Pandera e i test generativi richiedono il profilo scientifico; il test UI usa PySide6 in modalità offscreen. Il registro contiene soltanto il workflow amministrativo: referti e rendicontazione sono fuori dalla richiesta confermata.

## Importazione geografica in staging — R01/R03, primo incremento

La scheda **Import e anagrafiche** contiene il flusso per lo snapshot JSON verificato `data/public/geografia.json` oppure un CSV con virgola dello stesso tracciato. Scegliere la fonte, controllare le sei colonne sorgente, premere **Verifica e anteprima**, poi **Conferma import in staging**. L'anteprima riconcilia righe valide e scartate; i codici duplicati sono tutti scartati, senza scegliere arbitrariamente il primo. Codici e CAP restano stringhe. Snapshot alterati vengono respinti.

Il database separato `data/external_staging.sqlite3` (percorso alternativo: `HEALTHREPORT_STAGING_DB`) conserva lotti immutabili, righe originali, scarti/motivi, mapping, hash e provenienza. Reimportare lo stesso contenuto con gli stessi metadati e mapping restituisce il lotto esistente. Un file modificato crea una versione distinta: non aggiorna né cancella le visite. Per ritrovare un lotto, selezionare di nuovo la stessa fonte e confermare l'importazione idempotente.

Per associare codici esterni a enti/presidi/sedi interni, compilare [geography_crosswalk.csv](templates/geography_crosswalk.csv) e caricarlo con **Carica corrispondenze revisionate CSV**. Tutte le colonne sono obbligatorie eccetto `valid_to`; `namespace` deve essere `lombardia:6n7g-5p5e:ricovero`, `status` deve essere `approved`. Usare date ISO `AAAA-MM-GG`, fonte e revisore espliciti. La validità è inclusiva; fine vuota significa validità senza fine dichiarata dal revisore. Un file non valido non inserisce alcuna associazione. Questo incremento registra dichiarazioni revisionate; non verifica autenticità del revisore o esistenza degli identificativi interni.

**Verifica corrispondenze** applica codice esatto e periodo alla data scelta. Nessun candidato produce `unmapped`, uno `mapped`, più candidati `ambiguous`, con alternative visibili nel report. La copertura usa come denominatore le sole righe valide del lotto. **Invia tabella e provenienza ai Report** pubblica l'intera tabella verificata, con hash della fonte, lotto, aggiornamento, limiti e dettagli delle associazioni; la vista è limitata a 1.000 righe.

Verifica sullo snapshot locale storico: 212 righe valide, zero scartate, reimportazione senza duplicati. Nessuna corrispondenza interna inventata: 212 non associate. Fonte aggiornata nel 2018, inadatta a certificare sedi attuali. R01/R03 restano aperti per CUP, Excel/DB/API con staging, altri tracciati e anagrafiche, aggiornamenti incrementali per record, revisione/revoca delle corrispondenze e autenticazione. Non addestrare modelli di domanda/no-show su questa anagrafica.

## Limiti operativi del registro visite

Questa integrazione è una base desktop locale. Il campo operatore è dichiarativo; non fornisce autenticazione, autorizzazioni né un audit resistente a manomissioni del file SQLite. Prima dell'impiego condiviso con dati reali servono controllo degli accessi, backup e una decisione sull'architettura del servizio. Non sono ancora implementati collegamenti a CUP esterni, notifiche o importazione dei loro flussi: occorrono formati e interfacce effettivi.

Repository upstream: [silenzio76/test](https://github.com/silenzio76/test). Il rapporto storico in `lavoro/archive` è la base dei requisiti statistici, con aggiornamenti regionali distinti e versionati nel documento di progettazione. L’archivio documentale è esterno al repository: i collegamenti relativi verso `../../archive` funzionano nel workspace di lavoro; per il rapporto principale è disponibile anche il collegamento al PDF istituzionale.

## Statistica, dati regionali e machine learning

### R02 — derivazioni annuali SSR disponibili

Nella pagina **Statistica e ML**, selezionare **Derivazioni annuali SSR** e premere **Genera e verifica colonne**. Lo snapshot locale verificato `data/public/specialistica.json` produce una tabella anno × codice ATS × natura dell'erogatore. Sono conservati codici testuali e natura pubblica/privata, distinta dal regime SSN/ALPI. Le descrizioni ATS non sono chiavi: un cambio di nome non interrompe la stessa coorte; descrizioni multiple sono segnalate.

Le colonne comprendono anno/volume precedente disponibile, anni mancanti fra osservazioni, variazione assoluta e percentuale solo fra anni consecutivi, quota di produzione con priorità non indicata, stato del confronto, versione e hash della fonte. Una base zero lascia nulla la percentuale; anni mancanti non vengono creati o imputati. La riconciliazione per anno conserva sia volumi sia conteggi `source_rows`, senza certificare completezza del periodo o confrontabilità delle codifiche.

La scheda **Regole e unità** mostra formula, colonne sorgente, unità, regola sui nulli e versione. **Esporta dati e regole** crea una cartella verificata con `source.json` (snapshot originale completo), `annual.csv`, `recipe.json` e `manifest.json`. La preparazione avviene in una cartella temporanea sorella e diventa visibile con un'unica rinomina atomica. Ripetere l'export verifica il pacchetto esistente; un pacchetto alterato viene respinto senza sovrascrittura. **Invia tabella ai Report** usa il flusso analitico esistente; per mantenere insieme tutti i metadati e la fonte completa usare l'export dedicato.

Da terminale, senza scaricare nuove fonti:

```text
python public_derivations.py
```

Percorsi alternativi: `--source percorso_snapshot.json --output cartella`. Il pacchetto locale predefinito è sotto `data/derived`, escluso da Git. Verifica reale: 22.673 aggregati → 161 righe annuali, 804.902 righe sorgente riconciliate, anni 2016–2025. R02 è completato solo per questa ricetta fissa: editor di formule, altre granularità, join interni e altre fonti restano pianificati. Nessuna serie CUP, settimana sintetica o etichetta no-show ricavata dai volumi. [Esiti e limiti R02](reports/R02_ANNUAL_DERIVATIONS_2026-10-04.md).

Requisiti, formule, dizionario dei dati, fonti con pagine verificate e passi per la struttura multisede: [HEALTHCARE_ANALYTICS_DESIGN.md](HEALTHCARE_ANALYTICS_DESIGN.md). Risultati dell’estrazione pubblica: [LOMBARDIA_DATA_REPORT.md](reports/LOMBARDIA_DATA_REPORT.md).

Il catalogo della roadmap include regressioni, alberi decisionali, Random Forest, gradient boosting, reti neurali, K-Means e altri clustering, serie temporali, analisi delle anomalie, sopravvivenza e scenari di capacità, con criteri per report e confronto dei modelli. Attualmente è disponibile la pipeline Random Forest settimanale; gli altri metodi sono pianificati e saranno selezionati in base al problema e ai dati reali.

Ogni release comprende revisione e aggiornamento dell’interfaccia e verifica di dipendenze/file obsoleti, duplicati o incompatibili. Queste attività restano permanenti nella roadmap R11–R12 e nella [checklist di rilascio](RELEASE_CHECKLIST.md); una rimozione richiede evidenza d’inutilità e verifiche delle funzioni coinvolte.

```text
python lombardia_data.py
python build_public_analysis.py
python tests/smoke_main_window.py
```

Gli snapshot completi aggregati sono in `data/public`, esclusi da Git; query, licenza, timestamp e hash sono conservati. I report riproducibili sono in `reports`. L’indicatore `pubb_priv` non distingue SSN da ALPI: identifica la natura dell’erogatore nel dataset di produzione SSR.

**Indicatori visite** calcola numerosità della lista aperta, arretrati con appuntamento trascorso, esecuzioni, annullamenti, assenze con denominatore esplicito e intervallo Wilson, mediana e p90 richiesta–appuntamento corrente sui primi accessi con richiesta nota. Non certifica il rispetto normativo e non ricostruisce snapshot storici. Il p90 dell’età della lista aperta riguarda solo richieste note.

**Valuta previsione domanda CSV** richiede almeno 52 settimane consecutive complete, con colonne `week` (lunedì locale), `requests` (intero non negativo) e `complete` (booleano True). Il file deve rappresentare una sola coorte ente/sede/prestazione/regime e tutte le richieste, incluse quelle non prenotate. È disponibile il template vuoto `templates/weekly_demand.csv`; non contiene dati addestrabili. Il modello Random Forest usa solo ritardi e calendario, valuta le ultime 12 settimane contro l’ultima settimana osservata con MAE/WAPE e produce 4 settimane future ricorsive. Il pulsante **Previsioni future** mostra queste stime, pubblicabili nei Report. Una validazione su dati sintetici dimostra il funzionamento del codice, non l’efficacia su dati reali. Il modello non modifica le agende; non produce intervalli previsionali calibrati.

La funzione `capacity_report` richiede due tabelle con chiavi `organisation,site,regime,period`, rispettivamente `booked_minutes` e `available_minutes`: non presume una capacità disponibile dai volumi pubblici. Una capacità sconosciuta o nulla non produce una percentuale di saturazione.

Riferimento tecnico per lo schema: [documentazione Pandera](https://pandera.readthedocs.io/en/stable/dataframe_schemas.html).

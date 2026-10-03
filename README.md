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

**Verifica qualità (Pandera)** controlla unicità degli ID, campi, stati, ordine degli orari e coerenza dell'esecuzione. pandas viene usato per dataset e aggregazioni; i grafici e le analisi del report originale rimangono disponibili. La scheda **Statistica sanitaria e ML** sostituisce la scheda ML dimostrativa: offre indicatori operativi stratificati, produzione regionale e validazione di previsioni della domanda. Nessun modello viene addestrato sui pazienti automaticamente.

## Avvio

Python 3.10 o successivo, con versioni delle dipendenze compatibili con l'interprete scelto.

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Su Linux/macOS usare `.venv/bin/python`. Eseguire dalla cartella del sottoprogetto, come per l'app originale. Il database viene creato al primo avvio in `data/visits.sqlite3`; per usare un altro percorso impostare `HEALTHREPORT_VISITS_DB`. Il database e i nuovi artefatti temporanei sono esclusi da Git. I vecchi bytecode già presenti nel repository originale non vengono rimossi da questa integrazione.

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

## Limiti operativi

Questa integrazione è una base desktop locale. Il campo operatore è dichiarativo; non fornisce autenticazione, autorizzazioni né un audit resistente a manomissioni del file SQLite. Prima dell'impiego condiviso con dati reali servono controllo degli accessi, backup e una decisione sull'architettura del servizio. Non sono ancora implementati collegamenti a CUP esterni, notifiche o importazione dei loro flussi: occorrono formati e interfacce effettivi.

Repository upstream: [silenzio76/test](https://github.com/silenzio76/test). Il rapporto storico in `lavoro/archive` è la base dei requisiti statistici, con aggiornamenti regionali distinti e versionati nel documento di progettazione. L’archivio documentale è esterno al repository: i collegamenti relativi verso `../../archive` funzionano nel workspace di lavoro; per il rapporto principale è disponibile anche il collegamento al PDF istituzionale.

## Statistica, dati regionali e machine learning

Requisiti, formule, dizionario dei dati, fonti con pagine verificate e passi per la struttura multisede: [HEALTHCARE_ANALYTICS_DESIGN.md](HEALTHCARE_ANALYTICS_DESIGN.md). Risultati dell’estrazione pubblica: [LOMBARDIA_DATA_REPORT.md](reports/LOMBARDIA_DATA_REPORT.md).

Il catalogo della roadmap include regressioni, alberi decisionali, Random Forest, gradient boosting, reti neurali, K-Means e altri clustering, serie temporali, analisi delle anomalie, sopravvivenza e scenari di capacità, con criteri per report e confronto dei modelli. Attualmente è disponibile la pipeline Random Forest settimanale; gli altri metodi sono pianificati e saranno selezionati in base al problema e ai dati reali.

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

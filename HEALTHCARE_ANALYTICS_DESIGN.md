# Statistica e machine learning per la gestione sanitaria multisede

Versione 1.3, 3 ottobre 2026. Ambito: prenotazione, stato ed esecuzione amministrativa della visita, statistica e supporto alla programmazione. Referti e rendicontazione contabile non fanno parte dell’implementazione richiesta. Roadmap estesa con importazione, colonne derivate, classificazione multidimensionale, corrispondenze anagrafiche, catalogo dei metodi analitici, reportistica e manutenzione permanente a ogni release.

## Valutazione REV-077 e decisioni

**Accettato:** centralità della statistica; gestione con ente e sedi dipendenti; separazione SSN/ALPI/solvenza; uso dell’archivio come base dei requisiti; recupero di dati pubblici ufficiali. **Rivisto:** i volumi pubblici diventano confronti di produzione; non sono trasformati in richieste, slot disponibili o tempi individuali. **Respinto:** addestrare previsioni settimanali o di mancata presentazione sui soli totali regionali annuali; classificare un erogatore privato come ALPI; interpretare una priorità assente come P. **Provvisorio:** corrispondenze anagrafiche tra struttura interna, presidio, sede, codici regionali e branca; regole aggiornative dei documenti estratti, fino a verifica della versione ufficiale e delle note attuative applicabili.

Il risultato attuale è una base desktop verificata. L’architettura per una grande struttura è definita qui; backend condiviso, richieste senza prenotazione e integrazioni CUP restano sviluppi esplicitamente distinti.

## Requisiti ricavati dalla missione valutativa

I riferimenti seguenti usano i numeri stampati nelle pagine dell’edizione archiviata, verificati nei separatori di pagina del Markdown. I numeri delle pagine del visualizzatore possono differire. Le descrizioni del 2018 sono evidenza storica, non prescrizioni normative attuali.

| Requisito analitico | Evidenza storica verificata | Decisione di progetto | Stato |
|---|---|---|---|
| Distinguere consistenza della lista, attesa di accesso e attesa nel processo | PoliS-Lombardia, 2018, p. 14 | Tre famiglie di indicatori; la lista è uno stock, le attese sono durate | Stock prenotazioni e richiesta–slot implementati; processo da acquisire |
| Misurare offerta occupata e libera per regime | PoliS-Lombardia, 2018, p. 43 | Minuti prenotati e disponibilità esplicita della stessa agenda e periodo | Funzione capacità implementata; fonte capacità non ancora integrata |
| Separare primo accesso/controllo e indisponibilità delle risorse | PoliS-Lombardia, 2018, pp. 114–115 | Dimensioni distinte; assenze di personale/apparecchiature nel futuro calendario capacità | Dimensioni implementate; calendario da integrare |
| Misurare accesso fisico, attesa in sede e utilizzo degli ambulatori | PoliS-Lombardia, 2018, pp. 123–124 | Timestamp arrivo, inizio e fine clinici separati dall’aggiornamento amministrativo | Definito; non calcolato da executed_at |
| Analizzare attività istituzionale e libero-professionale | PoliS-Lombardia, 2018, pp. 134–135 | Regimi separati a parità di prestazione, sede, periodo e accesso | Stratificazione implementata; confronti richiedono dati interni |
| Evitare priorità mancanti e considerare complessità delle sedi | PoliS-Lombardia, 2018, p. 156 | Mancanti visibili; nessuna correzione automatica; sedi alternative abilitate solo se compatibili | Mancanti implementati; compatibilità da configurare |

Fonte principale: [Markdown archiviato](../../archive/MV_n13_TempiAttesa_Completo_Settembre2018.md). Le vecchie tabelle estratte e i benchmark di altre regioni non sono caricati come dati lombardi attuali: richiedono verifica distinta della struttura delle tabelle, dei periodi e delle definizioni.

## Aggiornamenti regionali: matrice di applicabilità

| Documento dell’archivio | Informazione verificata nel file | Conseguenza analitica | Applicazione |
|---|---|---|---|
| DGR XII/6583 del 27 luglio 2026 | Periodi pubblico maggio–dicembre, privato gennaio–dicembre; sostituzione degli allegati precedenti (Regione Lombardia, 2026a, pp. 5, 7) | Obiettivi di volume con inizio/fine e versione; confrontare periodi omogenei, non totali annuali grezzi | Requisito definito; nessun target numerico inventato da allegati assenti |
| DDG 8670/2026 | Nel richiamo iniziale alla DGR XII/5589 compare 30/12/2026, data da verificare rispetto al contesto del decreto | Anomalia di fonte; conservare originale e registrare verifica della data | Nessuna correzione silenziosa; nessuna regola automatica derivata dall’anomalia |
| DGR XII/6692 del 3 agosto 2026, file 2026_G1_212 | Atto di aggiornamento della programmazione SSR | Collegare gli allegati alla versione dell’atto, con decorrenza e stato di verifica | Registrato come contesto; non unificato indiscriminatamente al rapporto 2018 |
| RL_RLAOOG1_2026_739, Allegato 3 | Distinzione SSN/solvenza/LP e flussi 28/SAN/SMAF; validità di prenotazione U/B e separazione dalla data di esecuzione (Regione Lombardia, 2026b, p. 5) | Regime, tipo ente, data prescrizione, data richiesta e data prenotazione sono campi diversi | Regime implementato; integrazioni dei flussi e validità prescrizioni da verificare e sviluppare |
| Stesso Allegato 3 | Appropriatezza, controllo/priorità e accoglienza, con rinvio a note operative (Regione Lombardia, 2026b, p. 6) | Regole versionate; monitoraggio delle incoerenze prima di introdurre blocchi prescrittivi | Nessun blocco prescrittivo implementato senza verifica delle note e interfacce |
| RL_RLAOOG1_2026_737, Allegato 1; RL_RLAOOG1_2026_730, Allegato 2 | Quadro economico-finanziario e indicazioni gestionali agli enti | Eventuale analisi futura costo/capacità con fonti contabili, distinta dal workflow delle visite | Fuori dallo sviluppo corrente della rendicontazione; conservati come contesto |

L’Allegato 3 estratto e la pagina informativa pubblica presentano indicazioni sulla tempestività/validità della prenotazione da raccordare: non si presume che siano lo stesso termine. La [pagina regionale dei tempi d’attesa](https://www.regione.lombardia.it/sanita/prenotazioni-e-tempi-d-attesa/tempi-attesa-pretazioni-sanitarie), consultata il 3 ottobre 2026, riporta U 72 ore, B 10 giorni, D 30 giorni per visite e 60 per strumentali, P 120 giorni, con decorrenza dalla richiesta. L’app non applica questi limiti come certificazione di conformità. Occorrono prestazioni monitorate, primo accesso, eccezioni, disponibilità offerta/rifiutata, decorrenza e versione normativa: una semplice sottrazione di date non basta.

## Modello dei dati e flussi

Gerarchia prevista: ente → presidio → sede → agenda/risorsa → slot. Gli identificativi regionali e interni devono avere una tabella di corrispondenza con intervallo di validità. Il codice paziente usato per i conflitti deve essere unico nella rete gestita; omonimi o codici locali non possono essere abbinati solo per nome. ALPI va usato quando il regime è confermato; altre forme di libera professione richiedono un’estensione controllata della tassonomia e non vanno automaticamente assimilate all’ALPI.

| Entità | Campi minimi | Stato attuale |
|---|---|---|
| Prenotazione | ID, codice paziente, servizio, ente, sede, risorsa, professionista, regime, priorità, accesso, tipo prestazione, richiesta, creazione, slot, durata, stato | Implementata; metadati storici mancanti conservati come sconosciuti |
| Eventi | ID prenotazione, stato precedente/nuovo, operatore, timestamp; precedente/nuovo slot per riprogrammazione | Implementata; operatore dichiarativo, senza autenticazione |
| Richiesta | ID indipendente dalla prenotazione, prescrizione, priorità, servizio, canale, richiesta, primo slot offerto, accettazione/rifiuto motivato, chiusura | Da integrare; indispensabile per domanda non soddisfatta |
| Capacità | agenda/sede/regime, periodo e fuso, minuti disponibili, chiusure, personale, apparecchiature, slot riservati | Schema analitico disponibile; calendario operativo da integrare |
| Esecuzione clinica | arrivo, accettazione, inizio effettivo, fine effettiva | Da acquisire separatamente; executed_at è la registrazione amministrativa |
| Anagrafiche | codici servizio/branca/FARE, ente/sede/ATS, compatibilità clinica delle sedi e professionisti | Da configurare con il titolare dei flussi |
| Versioni | fonte, schema, estrazione, decorrenza, regola, hash, copertura | Snapshot pubblici implementati; registro regole operativo da integrare |

La prenotazione verifica sovrapposizioni per paziente, professionista condiviso e risorsa nella stessa coppia ente/sede, anche tra regimi differenti. Un’omonima risorsa in due sedi può operare contemporaneamente se professionista e paziente sono diversi. La durata è una previsione dello slot, non la durata effettiva. Tempi di trasferimento fra sedi, équipe con più professionisti, attrezzature condivise e dipendenze fra prestazioni richiedono vincoli aggiuntivi espliciti; non sono dedotti dalle coordinate pubbliche storiche.

## Dizionario degli indicatori

Grana corrente: ente × sede × prestazione × regime × priorità × accesso. Ogni tabella riporta numerosità e copertura. SSN, ALPI e solvenza rimangono separati. Non confrontare mediane grezze di mix differenti come se indicassero performance causale.

| Indicatore | Formula/coorte | Implementazione e limiti |
|---|---|---|
| Prenotazioni e produzione registrata | Conteggio ID; eseguite separate da prenotate, annullate e assenti | Snapshot corrente, non volumi clinici certificati |
| Lista aperta | Stati prenotata/confermata/accettata | Non comprende richieste mai prenotate; non equivale a tutta la domanda inevasa |
| Arretrati irrisolti | Lista aperta con slot ≤ data dello snapshot | Segnale di stato da verificare, non classificazione automatica come assenza |
| Richiesta–slot corrente | Differenza in giorni, primi accessi non annullati con richiesta nota; mediana/p90 | Descrive l’appuntamento corrente, non la prima disponibilità originaria o l’attesa clinica ex post |
| Età della lista aperta | Snapshot − richiesta, p90 sui casi con richiesta nota | Casi aperti censurati: non mescolare queste età con attese concluse |
| Mancata presentazione | Assenti / (eseguite + assenti), appuntamenti trascorsi e risolti | Annullamenti e casi irrisolti esclusi; denominatore e intervallo Wilson 95% esposti. Piccole celle e dipendenza fra eventi richiedono cautela interpretativa |
| Capacità/saturazione agenda | Minuti prenotati / minuti disponibili, medesima sede/regime/periodo | Funzione implementata; capacità ignota resta ignota, zero non produce una percentuale. Non misura utilizzo clinico effettivo |
| Produzione regionale | Quantità per anno, ATS, natura dell’erogatore; dettaglio branca/priorità ultimo anno | Implementata; non è conteggio di pazienti né lista di attesa |
| Trend | Variazione anno/anno solo su anni consecutivi e base positiva | Implementato; nessuna interpolazione automatica di anni mancanti |
| Rispetto soglie e prima offerta | Slot offerto/erogazione rispetto a richiesta + regola eleggibile versionata | Da implementare dopo acquisizione offerta, esclusioni e regole confermate |
| Attesa in sede e durata effettiva | Inizio − max(arrivo, orario previsto); fine − inizio, con casi di ritardo distinti | Da implementare con eventi reali, senza usare registrazione esecuzione come inizio |
| Mobilità/alternative | Richieste accolte in sede diversa, distanza e tempo di viaggio, compatibilità | Da implementare su anagrafica aggiornata e preferenze esplicite |
| Costi e obiettivi aggiuntivi | Produzione omogenea / obiettivo di periodo; costo incrementale e minuti aggiuntivi | Da integrare; volumi pubblici non sostituiscono costi o budget aziendali |

Il report corrente richiede lo snapshot coerente con as_of: non ricostruisce a posteriori stati annullati/assenti. Per serie storiche della lista servono replay degli eventi o snapshot periodici immutabili. Nella GUI as_of è l’istante corrente. La qualità viene prima degli indicatori: unicità ID, date con fuso, ordine richiesta/creazione, stati noti ed esecuzione coerente vengono controllati.

## Dati pubblici recuperati

| Dataset ufficiale | Copertura osservata | Uso ammesso |
|---|---|---|
| [Specialistica per Erogatore, qm4z-s92m](https://www.dati.lombardia.it/d/qm4z-s92m) | 2016–2025, 804.902 righe sorgente → 22.673 aggregati completi | Produzione SSR per ATS/natura erogatore/branca/priorità |
| [Volumi Prestazioni Specialistica Ambulatoriale, hdbq-kes5](https://www.dati.lombardia.it/d/hdbq-kes5) | 2012–2022, 1.566.900 righe sorgente → 7.509 aggregati completi | Confronto storico separato, con verifica delle definizioni |
| [Georeferenziazione strutture, 6n7g-5p5e](https://www.dati.lombardia.it/d/6n7g-5p5e) | 212 record, metadati aggiornati nel 2018 | Riferimento geografico storico di strutture di ricovero |

Le tre licenze nei metadati sono CC0_10. Ogni snapshot contiene titolo, query, licenza, metadati, timestamp della fonte e del recupero, conteggio e SHA-256. Le estrazioni aggregate verificano che la somma dei conteggi delle righe originarie coincida con il conteggio sorgente e che la fonte non sia cambiata durante il download. Le pagine API sono ordinate per tutte le dimensioni di aggregazione nel downloader corrente. I report salvati includono il catalogo e gli hash dei CSV.

I due dataset di volumi non si sommano negli anni sovrapposti. pubb_priv indica il tipo di erogatore, non il regime di pagamento. La [pagina dell’Osservatorio epidemiologico](https://osservatorioepidemiologico.regione.lombardia.it/wps/portal/site/osservatorio-epidemiologico/erogazione-delle-prestazioni/specialistica-ambulatoriale) descrive la produzione finanziata dal SSR. Non sono presenti nel dataset scelto richieste CUP individuali, prima offerta, no-show, capacità disponibile o serie settimanali ALPI. Gli anni recenti e le variazioni di volume richiedono controllo della copertura della fonte. La priorità globale non indicata può includere attività per cui la priorità non è applicabile: non equivale automaticamente a errore prescrittivo o mancanza dei primi accessi monitorati.

## Machine learning: funzione disponibile e sviluppi previsti

**Disponibile:** previsione delle richieste settimanali di una sola coorte ente/sede/servizio/regime. L’input esterno deve includere anche le richieste non prenotate; lo store attuale non lo genera automaticamente. Sono richieste almeno 52 settimane consecutive, conteggi non negativi interi e complete=True verificato alla fonte. Settimane mancanti non vengono inventate come zero. Per stimare stagionalità annuale e cambiamenti di regime servono preferibilmente più anni e periodi omogenei.

La pipeline usa Random Forest con parametri fissi, lag di 1/4/13 settimane, media delle precedenti 4 settimane e calendario ciclico. Trattiene le ultime 12 settimane; per ogni settimana di test usa solo osservazioni precedenti, con modello congelato addestrato prima del test. Confronta MAE e WAPE con il riferimento ultima settimana; WAPE è indefinito quando il totale reale è zero. La verifica cronologica segue il principio illustrato dalla [documentazione scikit-learn sulle caratteristiche ritardate](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html). Il test sul codice modifica l’ultimo target e verifica che non cambino le predizioni precedenti.

Il refit su tutto lo storico produce 4 settimane ricorsive. Questa modalità differisce dalla valutazione a un passo: per l’uso decisionale richiede un backtest multiorizzonte dedicato. Il modello non fornisce intervalli calibrati, non estrapola bene oltre i conteggi osservati e non è validato su dati sanitari reali. “Migliora il riferimento” è un risultato di quel holdout, non un’autorizzazione al rilascio. Nessun modello assegna priorità o modifica prenotazioni.

**Sviluppi definiti, non addestrati:**

- No-show: esito su prenotazioni trascorse e risolte, caratteristiche disponibili al momento della decisione, baseline e regressione logistica; split cronologico, calibrazione, Brier score, precision/recall e confronto fra sedi/regimi. L’esito e gli eventi successivi non possono diventare predittori.
- Durata/carico: inizio/fine reali, quantili della durata per servizio e complessità; valutazione del carico in minuti invece del solo numero di visite.
- Scenari di agenda: domanda prevista, capacità reale, assenze, trasferimenti e vincoli professionali. Decisione umana e confronto prospettico; nessun overbooking automatico fondato sulla probabilità individuale di assenza.
- Modelli più complessi: Optuna su validazione interna cronologica; SHAP per analisi dei predittori; PyTorch solo dopo confronto con modelli semplici e dati sufficienti. torch è già nel profilo requirements_analysis.txt. La disponibilità della libreria non implica che una rete neurale sia la scelta migliore.

## Passaggio alla grande struttura: backlog delimitato

1. Acquisire tracciati CUP/agende con dizionario e pseudonimi stabili: richieste, offerte, prenotazioni, eventi, capacità e anagrafiche. Concordare chi certifica completezza e correzioni; distinguere riprogrammazioni da nuove richieste.
2. Realizzare servizio transazionale condiviso e database server, autenticazione/ruoli per sede, identificativi/idempotenza degli import, audit degli accessi e modifiche, backup e ripristino verificati. SQLite desktop è il prototipo locale.
3. Attivare acquisizione del calendario e degli eventi clinici, snapshot storici, regole versionate e dizionario delle prestazioni monitorate. Validare manualmente un campione contro i sistemi sorgente prima di usare gli indicatori come obiettivi.
4. Validare il modello sulle serie reali e più origini temporali, confrontare baseline, sedi e regimi, misurare deriva. Finanziare miglioramenti solo se l’errore ha un impatto operativo misurabile.

Questi passi sono proposti per la successiva integrazione, non dichiarati implementati. I risultati sono verificabili nei moduli, nei test e nel report pubblico; gli aggiornamenti del repository sono tracciati nella cronologia Git.

## Roadmap aggiuntiva: dati esterni, variabili e anagrafiche

Richiesta del 3 ottobre 2026. Classe Green per questa modifica documentale; le funzionalità elencate sono pianificate e non vengono dichiarate implementate.

### REV-077 della proposta

Accettati il caricamento di dati esterni, la generazione di variabili dai dati importati e le corrispondenze tra struttura interna, presidio, sede, codici regionali, branca e disciplina. Accettata la classificazione multidimensionale dell’erogatore privato: si interpreta «multiplo» come un ente con più sedi, discipline, codici o regimi; questa interpretazione resta un’assunzione da confermare sul tracciato reale.

Rivista la proposta di addestramento sui soli totali annuali: il totale non identifica la distribuzione settimanale e, se descrive prestazioni erogate, non identifica la domanda. Non contiene neppure etichette di mancata presentazione né il relativo denominatore. Resta respinta la loro presentazione come dati osservati per addestrare o validare modelli settimanali/no-show. Sono invece ammessi scenari di disaggregazione esplicitamente ipotetici e, quando disponibili serie sufficienti e omogenee, modelli dei volumi annuali. L’addestramento settimanale e no-show rimane un obiettivo della roadmap, subordinato all’acquisizione dei dati necessari.

| ID / ordine | Funzionalità pianificata | Contenuto | Criterio di completamento |
|---|---|---|---|
| R01 — prima fase | Caricamento di dati esterni | CSV, Excel, database e API; anteprima, scelta del foglio/tabella, mapping delle colonne, tipi, date/fusi, unità, granularità e identificativi. Area di staging separata dal registro operativo; aggiornamento incrementale e gestione dei duplicati | Import ripetuto idempotente; righe valide, scartate e motivi riconciliati con la fonte; nessuna modifica al registro senza validazione e import esplicito |
| R02 — dopo R01 | Generazione di variabili/colonne | Colonne calcolate, ricodifiche, join anagrafici e aggregazioni; suggerimenti basati sulle colonne effettivamente importate. Esempi: settimana/mese della richiesta, attesa richiesta–slot, fascia oraria, regime normalizzato, sede e branca mappate, lag temporali e indicatori di copertura | Ogni derivazione conserva formula, colonne sorgente, unità, regola sui nulli e versione; anteprima e controllo dei risultati. Niente esecuzione di codice arbitrario importato, imputazioni silenziose o target futuri fra i predittori |
| R03 — insieme a R01 | Corrispondenze anagrafiche | Registro di ente/struttura interna, presidio, sede fisica, codici regionali, ATS, prestazione, branca e disciplina. Relazioni uno-a-molti/molti-a-molti dove necessarie; sistema di codifica, decorrenza, fine validità, fonte, stato e revisore | Codici conservati come stringhe, inclusi zeri iniziali; nessuna equivalenza implicita fra branca e disciplina o fra presidio e sede. Candidati ambigui/incompleti segnalati e revisionati; percentuale di record mappati e non mappati esposta |
| R04 — dopo R03 | Classificazione dell’erogatore privato multiplo | Entità giuridica distinta da presidi e sedi; natura pubblica/privata, autorizzazione, accreditamento, contratto SSN, regimi effettivi per prestazione/sede/periodo, branche e discipline. Categorie simultanee ammesse quando documentate | Lo stesso ente può avere sedi e attività differenti; privato non implica ALPI, né accreditamento implica contratto SSN. Nessun doppio conteggio delle prestazioni nei join molti-a-molti; aggregazioni di ente riconciliate con le sedi |
| R05 — dopo verifica delle fonti | Scenari settimanali da volumi regionali annuali | Distribuzione ipotetica dei volumi erogati con pesi settimanali configurati e documentati; scenari alternativi e riconciliazione con il totale del periodo. Eventuali pesi ricavati da una fonte temporale esterna identificata separatamente | Risultati marcati come simulati, senza chiamarli domanda osservata o previsioni validate. Nessun tasso no-show inferito dall’annuale; nessuna validazione del modello sulle stesse serie sintetiche usate per addestrarlo |
| R06 — dopo R01–R04 e dati adeguati | Addestramento settimanale e mancata presentazione | Domanda: richieste settimanali complete, anche non prenotate. No-show: prenotazioni individuali trascorse, esiti risolti, annullamenti distinti e predittori disponibili prima dell’appuntamento. Totali annuali pubblici utilizzabili come contesto, senza confonderli con etichette o osservazioni settimanali | Validazione temporale su dati reali, confronto con baseline, copertura e calibrazione per sede/regime; benchmark pubblici riferiti a periodi già disponibili al momento della previsione; nessun rilascio automatico sugli slot |

Per R03, il matching esatto usa prima identificativi verificati e periodo di validità. Somiglianza dei nomi, indirizzi e coordinate può proporre candidati, senza confermarli automaticamente. Un cambio di denominazione, fusione o trasferimento di sede mantiene lo storico. Un codice di branca non viene sostituito da quello di disciplina senza una relazione documentata, anche quando le descrizioni sono simili.

Per R02, le variabili vengono generate alla grana del dato disponibile: una riga annuale non acquisisce date di appuntamento individuali tramite una formula. L’export conserva insieme dati originali, derivazioni e metadati; la pipeline di training registra quali colonne sono disponibili all’istante della decisione. Le colonne mancanti comportano un requisito non soddisfatto, non una stima presentata come osservazione.

Aggiornamento autorizzato il 4 ottobre 2026: in assenza della possibilità di acquisire l'estratto CUP, proseguire con la parte R02 applicabile agli snapshot pubblici annuali già verificati. R01/R03 restano parziali e i join interni di R02/R04 richiedono corrispondenze revisionate. R05 è un modulo di scenari distinto. R06 richiede serie temporali ed esiti reali e non modifica il requisito già stabilito per la pipeline disponibile.

### R02 annuale applicato — 4 ottobre 2026

REV-077: accettata la prosecuzione senza estratto aziendale per le sole derivazioni della produzione pubblica; esclusa l'inferenza di richieste settimanali o assenze. Implementata la ricetta `annual-production/1.0` su `qm4z-s92m`: aggregazione anno × codice ATS × natura erogatore, lag annuali per coorte, anni mancanti espliciti, variazioni fra anni consecutivi e denominatore positivo per la percentuale, quota di priorità non indicata. Codici preservati come stringhe; denominazioni multiple segnalate senza assumere nuove identità. Non eseguiti join con enti/presidi/sedi interni.

La GUI offre anteprima, regole/unità e export dedicato. La ricetta conserva formule, colonne sorgente, unità, nulli e versione; l'export conserva snapshot originale, tabella annuale, ricetta e manifest con hash in una directory preparata/validata prima della rinomina atomica. Pacchetti esistenti verificati senza sovrascrittura; fallimenti non alterano pacchetti precedenti. Ogni anno riconcilia volumi e `source_rows`. `coverage_status=unverified` distingue la riconciliazione aritmetica dalla completezza annuale e dalla comparabilità delle codifiche.

Verifica reale: 22.673 righe aggregate → 161 righe annuali, 804.902 righe sorgente, anni 2016–2025; 144 confronti consecutivi e 17 prime osservazioni. Test dedicati coprono anche buchi annuali e base zero, assenti nei confronti di questo snapshot. R02 resta parziale rispetto alla roadmap generale: mancano editor configurabile, ricodifiche ulteriori, altre fonti/grane e join anagrafici. Nessuna nuova dipendenza. Il prossimo incremento può estendere report descrittivi R10 sugli indicatori pubblici già verificati oppure ricette R02 su un altro dataset omogeneo; non chiudere R03/R04/R06 senza dati adeguati.

### Incremento applicato — 4 ottobre 2026

R01/R03 **parzialmente implementati**, senza chiudere le voci complessive: staging dell'anagrafica geografica reale `6n7g-5p5e` già archiviata (212 strutture, aggiornamento fonte 8 marzo 2018). REV-077 accetta questo tracciato pubblico come primo incremento verificabile; resta distinta l'acquisizione CUP necessaria per gli indicatori delle richieste e per R06. Nessuna equivalenza automatica fra struttura di ricovero, ente, presidio e sede ambulatoriale attuale.

Implementati scelta snapshot JSON/CSV, mapping esplicito delle colonne, anteprima, validazione senza conversioni numeriche dei codici, scarti riconciliati, lotti immutabili e import ripetuto idempotente in SQLite separato. Il matching usa un CSV di corrispondenze dichiarate approvate, namespace/codice esatto e date di validità inclusive, fonte e revisore; più candidati attivi restano ambigui. Report con percentuale mappata, non mappati e ambigui, hash, periodo, provenienza e alternative. Nessuna scrittura nel registro operativo.

Verifica reale: 212 valide + 0 scartate = 212 righe fonte; secondo import dello stesso lotto senza inserimento; 212 non mappate in assenza di corrispondenze approvate. Limiti aperti: autenticazione del revisore, verifica dell'anagrafica interna, revoche/correzioni delle associazioni, altre entità e tracciati, Excel/DB/API in staging, aggiornamento incrementale per record. R02/R04 seguono una corrispondenza interna effettivamente revisionata; i metodi R06–R09 rimangono subordinati ai dati adeguati.

## Roadmap dei metodi di analisi e della reportistica

REV-077: accettati regressioni, alberi decisionali, Random Forest, gradient boosting, reti neurali e K-Means come candidati. «Tutto ciò che è applicabile» diventa un catalogo ampliabile per problema, con confronto e criteri di ammissibilità; non comporta applicare ogni algoritmo a ogni dataset o installare indiscriminatamente tutte le librerie. Applicabilità e ordine di priorità rimangono da verificare sui tracciati acquisiti con R01–R04.

### Catalogo previsto

| Famiglia | Metodi candidati | Applicazione prevista | Dati e vincoli da verificare |
|---|---|---|---|
| Statistica descrittiva e inferenziale | Distribuzioni, quantili, intervalli di confidenza, bootstrap, correlazioni, test parametrici/non parametrici, confronti fra gruppi | Report su volumi, attese, durata, capacità, sedi, discipline e regimi | Numerosità, distribuzione, dipendenza fra eventi e confronti multipli; associazione non equivale a causalità |
| Regressioni | Lineare, Ridge/Lasso/Elastic Net, robusta, quantile, logistica; GLM Poisson e binomiale negativa | Attese/durate, conteggi di richieste, rischio di assenza, stima di quantili del carico | Target e distribuzione compatibili; esposizione per confrontare conteggi; calibrazione per probabilità; diagnostica e intervalli per stime inferenziali |
| Alberi decisionali | Regressione e classificazione, potatura e limiti di complessità | Regole esplorative, segmenti operativi e riferimento interpretabile | Profondità e numerosità delle foglie controllate; nessuna conversione automatica in regola prescrittiva |
| Ensemble di alberi | Random Forest, Extra Trees, bagging | Previsioni tabulari di domanda, carico e no-show | Confronto con regressioni e baseline; costo, stabilità e prestazioni fuori campione |
| Gradient boosting | Gradient Boosting e HistGradientBoosting; valutazione eventuale di XGBoost, LightGBM e CatBoost | Relazioni non lineari nei dati tabulari, classificazione e regressione | Validazione e tuning separati dal test; dipendenze esterne aggiunte solo quando selezionate e verificate |
| Reti neurali | MLP tabulare; LSTM/GRU o altre architetture temporali quando motivate | Domanda e carico con storico sufficientemente esteso e granularità adeguata | Confronto con modelli semplici, regolarizzazione, costo di training e dati reali sufficienti. PyTorch disponibile; nessun vantaggio assunto a priori |
| Altri modelli supervisionati | SVM/SVR, k-nearest neighbors, Naive Bayes e modelli gaussiani dove pertinenti | Benchmark alternativi per classificazione/regressione | Scaling e dimensionalità; dimensione del dataset e costo; ipotesi del modello rispetto al problema |
| Clustering | K-Means/MiniBatchKMeans, gerarchico, DBSCAN/HDBSCAN e Gaussian Mixtures | Raggruppare profili di sedi, agende, prestazioni o carichi; individuare segmenti organizzativi | Distanza e scaling coerenti, stabilità e silhouette dove appropriate; cluster come esplorazione, non etichette cliniche. HDBSCAN e altre API verificati rispetto alla versione installata |
| Riduzione dimensionale | PCA; t-SNE/UMAP per esplorazione quando giustificati | Sintesi di indicatori correlati e visualizzazione dei profili | Trasformazioni apprese solo sul training quando usate da un predittore; mappe esplorative non sostituiscono la validazione dei cluster |
| Serie temporali | Baseline stagionali, medie mobili, decomposizione/STL, smoothing esponenziale, ARIMA/SARIMA/SARIMAX, regressori con lag | Domanda, produzione e capacità nel tempo | Frequenza e copertura reali, stagionalità, covariate disponibili alla previsione e backtest per orizzonte; nessuna ricostruzione fittizia di settimane dall’annuale |
| Sopravvivenza e modelli gerarchici | Kaplan–Meier/Cox o AFT; effetti misti e stime per livelli organizzativi | Tempo alla visita con richieste ancora aperte; variabilità fra sedi/professionisti | Date di richiesta/esito e censura; annullamento come evento distinto quando necessario; ipotesi e dipendenze specifiche da verificare |
| Anomalie e controllo del processo | Isolation Forest, Local Outlier Factor, regole robuste; carte di controllo e rilevazione di cambiamenti | Errori di flusso, variazioni inattese di volume/attesa o saturazione | Segnalazione revisionabile, stagionalità e cambi di codifica; anomalia non equivale a errore o frode accertata |
| Scenari e ottimizzazione | Simulazione a eventi discreti/Monte Carlo, analisi delle code, ottimizzazione vincolata | Impatto di slot, personale, sedi alternative e tempi di trasferimento | Capacità e durate reali, vincoli professionali e scenari dichiarati; queste tecniche non sono modelli di classificazione e non modificano le agende automaticamente |

I cataloghi ufficiali di [apprendimento supervisionato](https://scikit-learn.org/stable/supervised_learning.html), [apprendimento non supervisionato](https://scikit-learn.org/stable/unsupervised_learning.html) e [statsmodels](https://www.statsmodels.org/stable/index.html) costituiscono il riferimento tecnico per selezionare le API applicabili. La disponibilità di un metodo non ne dimostra l’adeguatezza ai dati della struttura. Tecniche o librerie non già presenti saranno introdotte come dipendenze opzionali nel relativo incremento, dopo verifica.

### Incrementi e criteri di completamento

| ID | Incremento pianificato | Dipendenze | Criterio di completamento |
|---|---|---|---|
| R07 | Catalogo supervisionato: regressioni, alberi, ensemble, gradient boosting e reti neurali | R01–R04, target disponibili e R06 per domanda/no-show | Selezione di target e predittori, pipeline preprocessing/modello, baseline comune, tuning interno e test finale separato; modelli confrontabili sullo stesso campione e orizzonte |
| R08 | Clustering, riduzione dimensionale e anomalie | R01–R04 e indicatori omogenei | Profili aggregati con scaling documentato, stabilità dei gruppi, motivazione dei parametri e revisione delle anomalie; nessuna categoria organizzativa imposta da un cluster senza conferma |
| R09 | Serie temporali, attese censurate, modelli gerarchici e scenari | R01–R06, cronologia e capacità/esiti appropriati | Backtest multiorizzonte e intervalli quando stimabili; censura ed eventi concorrenti trattati esplicitamente; scenari riproducibili e riconciliati con le risorse reali |
| R10 | Report statistici e schede dei modelli | Indicatori validati e R07–R09 secondo il report | Ogni risultato collega fonte, periodo, coorte, formula/metodo, numerosità, copertura, incertezza, versione e limite; esportazioni coerenti con le tabelle verificate |

Ordine proposto: statistica descrittiva e regressioni/baseline, alberi e ensemble, gradient boosting e clustering, poi metodi più costosi o con requisiti aggiuntivi. Le reti neurali richiedono una motivazione misurata rispetto alle alternative. Survival, gerarchia e scenari hanno priorità quando il problema richiede rispettivamente censura, livelli organizzativi o vincoli di capacità.

### Valutazione comune e redazione dei report

- Regressione e conteggi: MAE/RMSE e metriche coerenti con il target; WAPE solo con denominatore valido, errore per sede/regime e orizzonte. Quantili e intervalli vanno valutati per copertura, non solo per errore medio.
- Classificazione no-show: precision, recall, PR-AUC, ROC-AUC, matrice di confusione, Brier score e calibrazione; soglia legata al costo operativo e non scelta sul test finale. Eventuale riequilibrio delle classi avviene solo nei fold di training.
- Clustering: stabilità, composizione, numerosità e metriche interne appropriate; nessuna “accuratezza” senza etichette reali di riferimento. Per anomalie, revisione di un campione e misura dei falsi allarmi quando possibile.
- Preprocessing, imputazione, selezione variabili e tuning vengono stimati sul training; split temporali per problemi futuri e valutazione per sedi/gruppi quando pertinente. I record dello stesso episodio non devono contaminare training e test.
- Spiegabilità: coefficienti e diagnostica, regole degli alberi, permutation importance, SHAP/LIME quando pertinenti; ogni spiegazione descrive il modello e non prova un effetto causale.
- Report: tabelle e grafici descrittivi, confronti stratificati, risultati di validazione e scenari separati dalle osservazioni. Testo basato sui valori verificati, con celle mancanti/denominatori espliciti, assunzioni e limiti; nessun dato o risultato inventato per completare una narrazione.
- Export pianificati: CSV/Excel delle tabelle e HTML/PDF del report, con identico periodo e filtri, metadati e scheda del modello. Una scheda indica obiettivo, dati, unità, split, baseline, parametri, metriche, versione, spiegazioni e limiti d’impiego.

**Stato distinto dal catalogo:** attualmente sono implementati gli indicatori descritti sopra e la pipeline Random Forest settimanale. Le altre famiglie, il selettore comparativo e gli export report aggiuntivi sono elementi di roadmap, non funzionalità già disponibili. Le librerie esistenti sono riusate dove sufficienti; non si aggiungono nuovi pacchetti con questa revisione documentale.

## Attività permanenti a ogni release

REV-077: accettati aggiornamento dell’interfaccia e rimozione di dipendenze/file inutili o inutilizzabili come impegni ricorrenti di rilascio. Rivista la rimozione indiscriminata: l’assenza di un import diretto non dimostra inutilità, e un file storico può documentare una fonte o una migrazione. I controlli seguenti rimangono attivi dopo il loro primo completamento e si ripetono per ogni release.

| ID | Attività permanente | Controlli e criteri di completamento |
|---|---|---|
| R11 | Aggiornare e verificare l’interfaccia | Allineare schermate alle funzioni disponibili; verificare flussi visite/import/statistica/report/ML, leggibilità, navigazione, ridimensionamento, scorrimento, messaggi, stati vuoti e di errore. Correggere i problemi rilevati, mantenere terminologia coerente e distinguere dati osservati, scenari e risultati dei modelli. Registrare le modifiche e i controlli eseguiti |
| R12 | Eliminare dipendenze e file inutili o inutilizzabili | Inventariare uso diretto, dinamico, opzionale e nei test; verificare compatibilità e installabilità con gli interpreti supportati. Rimuovere elementi confermati obsoleti o duplicati, correggere o sostituire quelli necessari ma inutilizzabili; mantenere sincronizzati requirements, cataloghi e documentazione. Conservare provenienza, migrazioni e dati necessari. Verificare avvio, import/export e test dopo ogni pulizia |

La [checklist permanente di rilascio](RELEASE_CHECKLIST.md) è obbligatoria per ciascuna release. Ogni voce deve avere un esito e una verifica oppure una motivazione di non applicabilità; i blocchi di funzionalità prevista vanno risolti prima del rilascio. La verifica dell’interfaccia si ripete anche quando non cambia la grafica. Le dipendenze scientifiche richieste e usate da funzionalità opzionali o incrementi pianificati non si eliminano solo perché il core non le importa: se necessarie restano nel profilo opzionale con motivazione esplicita.

Questo aggiornamento introduce la politica e i controlli documentali; non dichiara già eseguiti un redesign o una bonifica generale del repository.

## Riferimenti

PoliS-Lombardia. (2018). *I tempi di attesa per le prestazioni ambulatoriali in Lombardia* (Missione valutativa n. 13/2017, codice RES17006, rapporto luglio 2018). Edizione conservata in [MV_n13_TempiAttesa_Completo_Settembre2018.md](../../archive/MV_n13_TempiAttesa_Completo_Settembre2018.md); [PDF del Consiglio regionale](https://www.consiglio.regione.lombardia.it/wps/wcm/connect/93155870-083e-4953-9e98-f39150733079/MV_n13_TempiAttesa_Completo_Settembre2018.pdf?MOD=AJPERES).

Regione Lombardia. (2026a, 27 luglio). *DGR XII/6583: Determinazioni in ordine alla rimodulazione del Piano operativo regionale 2026 per il contenimento dei tempi di attesa*. [Edizione archiviata](../../archive/DGR_XII_6583_2026.md), pp. 5 e 7 verificate nel file.

Regione Lombardia. (2026b). *Aggiornamento indicazioni specifiche per gli enti sanitari del Sistema sociosanitario regionale: Allegato 3*. [Edizione archiviata RL_RLAOOG1_2026_739](../../archive/RL_RLAOOG1_2026_739.md), pp. 5–6 verificate nel file; attribuzione all’atto e note attuative da verificare sulla pubblicazione ufficiale.

Regione Lombardia. (s.d.). *Tempi di attesa delle prestazioni sanitarie*. [Pagina istituzionale](https://www.regione.lombardia.it/sanita/prenotazioni-e-tempi-d-attesa/tempi-attesa-pretazioni-sanitarie), consultata il 3 ottobre 2026.

Regione Lombardia. (s.d.). *Specialistica ambulatoriale*. [Osservatorio epidemiologico regionale](https://osservatorioepidemiologico.regione.lombardia.it/wps/portal/site/osservatorio-epidemiologico/erogazione-delle-prestazioni/specialistica-ambulatoriale), consultato il 3 ottobre 2026. Dataset, licenze e timestamp specifici in reports/sources.json.

scikit-learn developers. (s.d.). *Lagged features for time series forecasting*. [Documentazione ufficiale](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html), consultata il 3 ottobre 2026.

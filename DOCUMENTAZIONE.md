# HealthReport Studio — Documentazione Tecnica

**Versione:** 1.0  
**Data:** Maggio 2026  
**Tecnologia:** Python 3.10+ · PySide6 · pandas · SQLAlchemy · matplotlib

**Aggiornamento interfaccia 4 ottobre 2026:** cinque aree distinte (Dati e trasformazioni, Import e anagrafiche, Visite sanitarie, Statistica e ML, Report), navigazione semantica mediante `MainWindow.navigate`, stile/intestazioni in `workspace_ui.py`, importazione persistente in `external_staging_tab.py`. Le sezioni generiche descrivono il nucleo originale; per flussi sanitari, staging, limiti e verifiche correnti usare [README.md](README.md) e [HEALTHCARE_ANALYTICS_DESIGN.md](HEALTHCARE_ANALYTICS_DESIGN.md). Ribbon e risorse scollegate sono state rimosse; non sono moduli da reintegrare. Nessuna nuova dipendenza.

---

## Indice

1. [Panoramica del progetto](#1-panoramica-del-progetto)
2. [Struttura dei file](#2-struttura-dei-file)
3. [Avvio e requisiti](#3-avvio-e-requisiti)
4. [dependency_manager.py](#4-dependency_managerpy)
5. [main.py — Architettura](#5-mainpy--architettura)
6. [Classi di supporto](#6-classi-di-supporto)
7. [MainWindow — Tab Data Query](#7-mainwindow--tab-data-query)
8. [MainWindow — Tab Report](#8-mainwindow--tab-report)
9. [MainWindow — Tab Analisi ML](#9-mainwindow--tab-analisi-ml)
10. [Librerie e dipendenze](#10-librerie-e-dipendenze)
11. [Flusso dati](#11-flusso-dati)
12. [Estendere l'applicazione](#12-estendere-lapplicazione)

---

## 1. Panoramica del progetto

HealthReport Studio è un'applicazione desktop Python per l'importazione,
la trasformazione e l'analisi di dati strutturati provenienti da sorgenti
eterogenee (file locali, database relazionali, database cloud, URL).

### Funzionalità principali

| Area | Descrizione |
|---|---|
| **Data Query** | Caricamento dati da 10+ formati, connessioni DB reali via SQLAlchemy, 20 provider cloud, SQL editor con syntax highlighting |
| **ETL** | 30+ trasformazioni: filtri avanzati, pulizia, tipo, testo, numerico, data/ora, colonne calcolate, reshape, outlier, campionamento, undo/redo |
| **Report** | Profilazione automatica, 15 grafici base, 17 analisi statistiche avanzate, 12 metodi di previsione; export PDF/Excel/HTML/PPTX/Word/CSV/PNG |
| **Dipendenze** | Gestione automatica: librerie core installate all'avvio, librerie opzionali installate on-demand con dialogo di consenso e progress bar |

---

## 2. Struttura dei file

```
progetto/
│
├── main.py                     # Applicazione principale (4785 righe)
├── dependency_manager.py       # Gestione dipendenze (1136 righe)
├── LIBRARIES.md                # Librerie core (installate automaticamente)
├── LIBRARIES_OPTIONAL.md       # Librerie opzionali (installate on-demand)
│
└── ~/.healthreport_studio/
    └── installed_optional.json # Registro persistente librerie opzionali
```

### Dipendenze tra file

```
main.py
  └── importa ──► dependency_manager.py
                       └── legge ──► LIBRARIES.md
                       └── legge ──► LIBRARIES_OPTIONAL.md
                       └── scrive ──► ~/.healthreport_studio/installed_optional.json
```

---

## 3. Avvio e requisiti

### Requisiti minimi

- Python 3.10 o superiore
- pip disponibile nell'ambiente
- Connessione internet per il primo avvio (installazione librerie core)

### Primo avvio

```bash
# Clona / copia i file nella cartella di progetto, poi:
python main.py
```

All'avvio, `dependency_manager.py` crea automaticamente un virtual
environment locale (`./venv/`) su Linux se non esiste, installa le
librerie core da `LIBRARIES.md`, quindi avvia la GUI.

### Avvio successivo (venv già creato)

```bash
# Linux / macOS
./venv/bin/python main.py

# Windows
venv\Scripts\python main.py
```

### Struttura venv automatico (Linux)

```
progetto/
└── venv/
    └── bin/
        ├── python3   ← interprete usato dall'app
        └── pip
```

---

## 4. dependency_manager.py

Modulo autonomo (usa solo stdlib Python) responsabile di tutta la
gestione delle dipendenze. Non importa PySide6 né pandas al livello
di modulo: li usa solo all'interno delle funzioni che ne hanno bisogno.

### 4.1 Costanti e strutture dati

#### `APP_DIR`
```python
APP_DIR = Path.home() / ".healthreport_studio"
```
Cartella utente dove viene conservato il registro delle librerie
opzionali installate.

#### `OPTIONAL_REGISTRY_PATH`
```python
OPTIONAL_REGISTRY_PATH = APP_DIR / "installed_optional.json"
```
File JSON con il registro persistente. Struttura:
```json
{
  "psycopg2-binary": {
    "installed":  true,
    "version":    "2.9.9",
    "timestamp":  "2026-05-17T10:30:00",
    "python":     "/home/user/progetto/venv/bin/python3"
  },
  "pymongo": {
    "installed":  false,
    "error":      "No matching distribution found",
    "timestamp":  "2026-05-17T10:35:00"
  }
}
```

#### `_IMPORT_NAME_MAP`
Dizionario che mappa il nome pip al nome del modulo Python da importare
(necessario perché spesso differiscono, es. `psycopg2-binary` → `psycopg2`,
`scikit-learn` → `sklearn`, `python-pptx` → `pptx`).

#### `_SYSTEM_DEPS`
Avvisi sulle dipendenze di sistema per librerie che richiedono
strumenti esterni (es. `pyodbc` richiede unixODBC su Linux,
`oracledb` richiede Oracle Instant Client).

#### `PROVIDER_PACKAGES`
Mappa `provider_name → [lista pacchetti pip]` per tutti i provider
DB/Cloud supportati. Usata da `require_provider()`.

```python
PROVIDER_PACKAGES = {
    "PostgreSQL":  ["psycopg2-binary"],
    "MySQL":       ["pymysql"],
    "Snowflake":   ["snowflake-connector-python", "snowflake-sqlalchemy"],
    "MongoDB":     ["pymongo"],
    "InfluxDB":    ["influxdb-client"],
    # ... 20+ provider
}
```

---

### 4.2 Funzioni di ambiente

#### `detect_os() → str`
Rileva il sistema operativo. Valori: `"linux"`, `"windows"`, `"macos"`, `"unknown"`.

#### `get_local_venv_python() → str | None`
Cerca un virtual environment locale nelle cartelle `venv/`, `.venv/`, `env/`
(sia per Linux/macOS con `bin/python3` che per Windows con `Scripts/python.exe`).
Verifica che pip sia funzionante prima di restituire il percorso.

#### `get_python_executable() → str`
Restituisce il percorso dell'interprete Python da usare, con questa priorità:
1. `sys.executable` se `VIRTUAL_ENV` è impostato nell'ambiente
2. Il venv locale trovato da `get_local_venv_python()`
3. `sys.executable` come fallback

#### `_in_venv(python_executable) → bool`
Verifica se un percorso Python appartiene a un virtual environment.

#### `base_pip_command(python_executable) → list[str]`
Restituisce il comando base pip: `[python, "-m", "pip"]`.

---

### 4.3 Lettura file di configurazione

#### `read_libraries_from_markdown(markdown_path) → list[str]`
Legge `LIBRARIES.md` (o un altro file Markdown) ed estrae la lista
dei nomi pip dalle righe con bullet `- ` o `* `. Ignora commenti (`#`)
e righe vuote.

```python
# Input LIBRARIES.md:
# ## Core desktop
# - PySide6
# - pandas

libs = read_libraries_from_markdown("LIBRARIES.md")
# → ["PySide6", "pandas", ...]
```

#### `read_optional_libraries_from_markdown(markdown_path) → dict[str, str]`
Legge `LIBRARIES_OPTIONAL.md` ed estrae `{pip_name: descrizione}`.
Supporta due formati di riga:
- `# nome_pacchetto   → descrizione` (commento con freccia)
- `- nome_pacchetto` (bullet senza descrizione)

---

### 4.4 Registro librerie opzionali

#### `_load_optional_registry() → dict`
Carica il registro JSON da disco. Restituisce `{}` se non esiste o
è corrotto.

#### `_save_optional_registry(registry)`
Salva il registro su disco (crea la directory se necessario).

#### `_mark_installed(pip_name, version)`
Aggiorna il registro marcando una libreria come installata con
versione e timestamp correnti.

#### `_mark_failed(pip_name, error)`
Aggiorna il registro marcando un tentativo fallito con il messaggio
di errore.

---

### 4.5 Verifica installazione

#### `_pip_name_to_import(pip_name) → str`
Converte il nome pip nel nome del modulo Python da importare usando
`_IMPORT_NAME_MAP`, con fallback euristico (`-` → `_`).

#### `is_installed(pip_name, python_executable) → bool`
Verifica se una libreria è importabile nell'interprete specificato
eseguendo `python -c "import <modulo>"` come sottoprocesso.
Gestisce import annidati come `google.cloud.bigquery` estraendo
il modulo radice (`google`).

#### `check_if_libraries_installed(libraries, python_executable) → list[str]`
Filtra una lista di nomi pip restituendo solo quelli non installati.

---

### 4.6 Installazione

#### `get_pip_install_command(libraries, os_name, python_executable, upgrade) → list[str]`
Costruisce il comando pip install corretto per l'OS e l'ambiente:
- Aggiunge `--upgrade` se richiesto
- Aggiunge `--prefer-binary` su Linux/Windows/macOS (evita compilazione sorgente)
- Aggiunge `--user` su Linux se non si è in un venv (evita errori di permessi)

#### `install_libraries(libraries, os_name, python_executable, upgrade, timeout) → tuple[int, str, str]`
Esegue l'installazione tramite subprocess e restituisce
`(returncode, stdout, stderr)`.

#### `install_single_optional(pip_name, python_executable, progress_callback) → tuple[bool, str]`
Installa un singolo pacchetto opzionale:
1. Mostra avviso dipendenze di sistema se necessario
2. Chiama `install_libraries()`
3. Verifica con `is_installed()` che sia effettivamente importabile
4. Legge la versione installata via `pip show`
5. Aggiorna il registro con `_mark_installed()` o `_mark_failed()`
6. Chiama `progress_callback(msg)` per aggiornamenti live

#### `_summarize_pip_error(pip_name, stderr, os_name) → str`
Trasforma l'output di errore grezzo di pip in messaggi leggibili,
rilevando i pattern più comuni:
- `externally-managed-environment` → suggerisce di usare il venv
- `Microsoft Visual C++` → suggerisce Visual C++ Build Tools (Windows)
- `gcc` / `compiler` → suggerisce `build-essential` (Linux)
- `No matching distribution` → versione Python incompatibile
- `Could not find a version` → pacchetto non trovato su PyPI

---

### 4.7 API on-demand (usata da main.py)

Queste sono le funzioni principali che `main.py` chiama ogni volta
che deve usare una libreria opzionale.

#### `require_optional(pip_name, reason, extra_packages, silent) → bool`

La funzione centrale del sistema on-demand.

**Parametri:**
- `pip_name` — nome pip del pacchetto principale (es. `"psycopg2-binary"`)
- `reason` — descrizione leggibile perché serve (es. `"connessioni PostgreSQL"`)
- `extra_packages` — lista di pacchetti aggiuntivi da installare insieme
- `silent` — se `True`, installa senza dialogo di consenso

**Comportamento:**
1. Controlla la cache in-sessione (`_session_installed`): se già installato, restituisce `True` immediatamente
2. Controlla se l'utente ha già rifiutato in questa sessione (`_session_declined`)
3. Se Qt è disponibile, mostra `_show_install_dialog()` per il consenso
4. Se l'utente acconsente, chiama `_do_install_optional()` che apre `_show_progress_dialog()`
5. Se Qt non è disponibile, usa il fallback console (`input()`)

**Esempio d'uso:**
```python
# In _db_connect_and_save():
if not require_optional("sqlalchemy", reason="connessioni database"):
    return   # utente ha rifiutato o installazione fallita
import sqlalchemy as sa
# ... codice che usa sqlalchemy
```

#### `require_optional_group(group_name, packages, reason, silent) → bool`
Installa un gruppo di pacchetti correlati in una sola operazione.
Restituisce `True` solo se **tutti** i pacchetti sono disponibili.

```python
# Installa entrambi i pacchetti Snowflake insieme:
if not require_optional_group("Snowflake",
        ["snowflake-connector-python", "snowflake-sqlalchemy"],
        reason="connessione Snowflake DWH"):
    return
```

#### `require_provider(provider_name, silent) → bool`
Shortcut che risolve automaticamente i pacchetti da `PROVIDER_PACKAGES`
e chiama `require_optional_group()`.

```python
# Invece di sapere quali pacchetti servono per PostgreSQL:
if not require_provider("PostgreSQL"):
    return
import psycopg2   # garantito disponibile
```

---

### 4.8 Dialoghi Qt

#### `_show_install_dialog(pip_name, reason, all_packages) → bool`
Finestra modale di consenso con:
- Icona 📦 e titolo
- Area di testo con dettagli: funzione richiesta, pacchetti, interprete Python,
  comando pip esatto, avvisi dipendenze di sistema, storico tentativi falliti
- Pulsanti "Installa ora" / "Non installare"

#### `_show_progress_dialog(packages, primary, reason) → bool`
Finestra di progresso durante l'installazione:
- `QProgressBar` in modalità indeterminata durante l'installazione
- Area log con aggiornamenti in tempo reale (`Signal/Slot` su `QThread`)
- Barra diventa verde (OK) o rossa (errore) al termine
- Pulsante "Chiudi" abilitato solo al termine

#### `open_optional_manager(parent) → None`
Pannello Qt completo di gestione librerie opzionali (accessibile dal menu
Strumenti dell'applicazione):

| Colonna tabella | Contenuto |
|---|---|
| Pacchetto pip | Nome installabile con pip |
| Descrizione | Testo da LIBRARIES_OPTIONAL.md |
| Stato | ✔ Installato / ✖ Mancante (colorato) |
| Versione | Versione installata (da registro) |
| Azione | Pulsante "Installa" / "Reinstalla" per riga |

Funzionalità aggiuntive:
- Campo di ricerca per filtrare la lista
- "Installa selezionati": installa solo le righe selezionate non installate
- "Installa tutti mancanti": installa in sequenza tutte le librerie assenti
- Log in tempo reale durante l'installazione (BulkWorker su QThread)
- "Aggiorna stato": rilegge il registro e ricalcola lo stato

---

### 4.9 Funzione di avvio

#### `ensure_dependencies_before_startup(markdown_path, auto_update)`
Chiamata da `main.py` prima di avviare la GUI.

**Flusso di esecuzione:**

```
STEP 0 (solo Linux, non in venv)
  └── Crea ./venv/ se non esiste
  └── Esegue ensurepip nel venv
  └── Imposta python_executable = ./venv/bin/python3

STEP 1
  └── verify_and_ensure_pip()
  └── Stampa istruzioni OS-specifiche se pip mancante

STEP 2
  └── check_if_libraries_installed(core_libs)
  └── Se tutte OK → stampa banner "PRONTO" e ritorna

STEP 3 (solo se mancanti e auto_update=True)
  └── Aggiorna pip
  └── Controlla "externally-managed-environment"
  └── install_libraries(mancanti)
  └── Verifica parziale: se alcune installate → banner WARNING
  └── Se nessuna installata → RuntimeError
```

---

## 5. main.py — Architettura

### 5.1 Struttura generale

```
main.py (4785 righe, 233 KB)
│
├── Blocco dipendenze (righe 1-42)
│   └── ensure_dependencies_before_startup()
│
├── Import librerie (righe 44-90)
│
├── Classi di supporto
│   ├── PandasTableModel      (adattatore DataFrame ↔ QTableView)
│   ├── DataImporter          (caricamento dati da 10+ sorgenti)
│   ├── ETLEngine             (30+ trasformazioni pure su DataFrame)
│   ├── SQLHighlighter        (syntax highlighting SQL per QTextEdit)
│   └── FilterDialog          (dialogo configurazione filtri ETL)
│
├── MainWindow                (finestra principale, 120+ metodi)
│   ├── Tab 1: Data Query
│   │   ├── A · Sorgenti Dati
│   │   ├── B · Connessioni DB
│   │   ├── C · Cloud Database
│   │   ├── D · Editor SQL
│   │   └── E · ETL / Trasformazioni
│   ├── Tab 2: Import e anagrafiche (GeographyImportTab)
│   ├── Tab 3: Visite sanitarie (VisitTab)
│   ├── Tab 4: Statistica e ML (HealthcareAnalysisTab)
│   └── Tab 5: Report
│   │   ├── I   · Panoramica Dataset
│   │   ├── II  · Grafici Base
│   │   ├── III · Statistiche Avanzate
│   │   └── IV  · Previsioni & Probabilità
│
└── main()   (entry point)
```

### 5.2 Stato condiviso di MainWindow

```python
self.raw_df:     pd.DataFrame  # Dataset caricato originale (immutabile durante ETL)
self.working_df: pd.DataFrame  # Dataset corrente dopo trasformazioni ETL
self.query_sources:       list # [{kind, value}, ...] sorgenti aggiunte
self.db_connections:      list # Connessioni DB on-premise
self._active_connections: dict # {alias: {engine, type, url_masked, ...}}
self.etl_steps:           list # Log passi ETL (ultimi 40 mostrati)
self._report_figures:     dict # {titolo: matplotlib.Figure} per export
self.sql_result_df:  pd.DataFrame  # Risultato ultima query SQL
```

### 5.3 Flusso principale dei dati

```
Sorgenti dati (A)
  ↓ _set_raw_df()
raw_df  ──────────────────────────────────► working_df
                                               ↑
ETL (E) ──── _etl_apply(fn, description) ──────┘
              (con _etl_push() per undo)

working_df ──► SQL Editor (D) → query su SQLite in-memory
working_df ──► Report (II, III, IV) → grafici matplotlib
working_df ──► Esportazione (PDF/Excel/HTML/PPTX/Word/CSV/PNG)
```

---

## 6. Classi di supporto

### 6.1 PandasTableModel

Adattatore Qt che permette di visualizzare un `pd.DataFrame` in un
`QTableView` implementando `QAbstractTableModel`.

| Metodo | Descrizione |
|---|---|
| `rowCount()` | Numero di righe del DataFrame |
| `columnCount()` | Numero di colonne del DataFrame |
| `data(index, role)` | Valore cella in formato stringa; `""` per NaN |
| `headerData(section, orientation, role)` | Intestazioni colonne e indice riga |
| `update_dataframe(df)` | Aggiorna il modello con un nuovo DataFrame (emette reset) |
| `dataframe` (property) | Restituisce una copia del DataFrame corrente |

### 6.2 DataImporter

Classe con metodi statici puri che caricano dati da sorgenti eterogenee
restituendo sempre un `pd.DataFrame`.

| Metodo | Sorgente | Note |
|---|---|---|
| `load_file(path)` | File locale | CSV, TSV, XLSX, XLS, JSON, XML, Parquet, Feather, ORC, SQLite, DuckDB |
| `load_folder(path)` | Cartella | Carica e concatena tutti i file supportati nella cartella |
| `load_url(url)` | URL HTTP/S | Auto-detect formato da estensione e Content-Type |
| `load_sqlite(path, query)` | SQLite | Query personalizzata |
| `_load_xml(path)` | XML | Prima tenta `pd.read_xml()`, poi parsing manuale con ElementTree |
| `_load_sqlite_first_table(path)` | SQLite | Carica automaticamente la prima tabella (LIMIT 5000) |
| `normalize_columns(df)` | — | Normalizza nomi colonne: minuscolo, spazi→underscore |

**Formati supportati:** `.csv`, `.tsv`, `.xlsx`, `.xls`, `.json`, `.xml`,
`.parquet`, `.feather`, `.orc`, `.db`, `.sqlite`

### 6.3 ETLEngine

Classe con 30+ metodi statici puri (ogni metodo riceve un DataFrame,
restituisce un nuovo DataFrame senza modificare l'originale).
Solleva `ValueError` con messaggi in italiano per input non validi.

#### Filtri

| Metodo | Descrizione |
|---|---|
| `filter_rows(df, column, operator, value)` | 17 operatori: `==`, `!=`, `>`, `>=`, `<`, `<=`, `contiene`, `non contiene`, `inizia con`, `finisce con`, `regex`, `è vuoto`, `non è vuoto`, `in lista`, `non in lista`, `tra (numerico)`, `outlier IQR` |

#### Pulizia

| Metodo | Parametri chiave | Descrizione |
|---|---|---|
| `sort_rows(df, columns, ascending)` | `columns: list`, `ascending: list` | Ordina su N colonne con direzione indipendente |
| `drop_duplicates(df, subset, keep)` | `keep: "first"/"last"/False` | Rimuove duplicati |
| `drop_nulls(df, subset, thresh)` | `thresh: int` | Elimina righe con nulli |
| `fill_nulls(df, column, strategy, fill_value)` | 9 strategie | Strategie: `valore`, `media`, `mediana`, `moda`, `forward fill`, `backward fill`, `interpolazione lineare`, `zero`, `stringa vuota` |
| `drop_column(df, column)` | — | Elimina una colonna |
| `drop_columns(df, columns)` | `columns: list` | Elimina più colonne |
| `keep_columns(df, columns)` | `columns: list` | Mantiene solo le colonne indicate |
| `rename_column(df, old, new)` | — | Rinomina con verifica unicità |
| `rename_columns_map(df, mapping)` | `mapping: dict` | Rinomina più colonne con dizionario |
| `reorder_columns(df, new_order)` | — | Riordina (colonne non indicate → in fondo) |

#### Conversione di tipo

| Metodo | Tipi supportati |
|---|---|
| `cast_column(df, column, dtype, date_format)` | `string`, `int`, `float`, `datetime`, `boolean`, `category`, `timedelta` |

#### Trasformazioni testo

`text_transform(df, column, operation, extra)` — 15 operazioni:

| Operazione | Extra richiesto |
|---|---|
| `maiuscolo`, `minuscolo`, `title case` | — |
| `strip`, `lstrip`, `rstrip` | — |
| `sostituisci` | `"vecchio→nuovo"` |
| `prefisso`, `suffisso` | testo da aggiungere |
| `estrai regex` | pattern regex Python |
| `lunghezza` | — (crea colonna `_len`) |
| `split` | `"separatore\|posizione"` |
| `rimuovi spazi multipli` | — |
| `rimuovi caratteri speciali` | — |
| `codifica url` | — |

#### Trasformazioni numeriche

`numeric_transform(df, column, operation, value)` — 18 operazioni:

| Operazione | Parametro `value` |
|---|---|
| `arrotonda` | n. decimali |
| `assoluto`, `logaritmo`, `log10`, `radice quadrata` | — |
| `normalizza 0-1`, `standardizza (z-score)` | — |
| `clip` | `"min,max"` |
| `potenza` | esponente |
| `percentuale sul totale` | — |
| `rank` | — (crea `_rank`) |
| `bin` | n. bin (crea `_bin`) |
| `cumsum`, `cumprod` | — (crea nuova colonna) |
| `diff`, `shift` | periodi |
| `rolling mean`, `rolling std` | finestra |

#### Data/Ora

| Metodo | Descrizione |
|---|---|
| `datetime_extract(df, column, parts)` | Estrae: `anno`, `mese`, `giorno`, `ora`, `minuto`, `secondo`, `giorno_settimana`, `numero_settimana`, `trimestre`, `is_weekend`, `nome_mese`, `nome_giorno`, `unix_timestamp` |
| `datetime_diff(df, col1, col2, unit, new_col)` | Differenza in `days`, `hours`, `minutes`, `seconds`, `weeks`, `months`, `years` |

#### Colonne calcolate

| Metodo | Descrizione |
|---|---|
| `add_formula_column(df, new_col, formula)` | Espressione valutata con `df.eval()` (es. `"prezzo * quantita * 1.22"`) |
| `add_conditional_column(df, new_col, ...)` | Colonna IF/ELSE basata su filtro |
| `add_map_column(df, source_col, new_col, mapping_str)` | Mappa valori con dizionario `"A→1,B→2"` |

#### Reshape

| Metodo | Descrizione |
|---|---|
| `merge(df, right, on, how)` | Join tra due DataFrame (inner/left/right/outer/cross) |
| `concat_rows(dfs)` | Concatenazione verticale di più DataFrame |
| `pivot(df, index, columns, values, agg_func)` | Tabella pivot |
| `unpivot(df, id_vars, var_name, value_name)` | Da wide a long format (melt) |

#### Aggregazione e campionamento

| Metodo | Descrizione |
|---|---|
| `aggregate(df, group_by, agg_column, agg_func)` | GROUP BY singola colonna |
| `aggregate_multi(df, group_by, agg_dict)` | GROUP BY multi-colonna multi-funzione |
| `sample_rows(df, n, frac, seed)` | Campionamento per n righe o frazione |

#### Outlier

| Metodo | Descrizione |
|---|---|
| `remove_outliers_iqr(df, columns, factor)` | Rimuove righe con outlier IQR (default k=1.5) su N colonne |
| `cap_outliers_iqr(df, columns, factor)` | Winsorizing: clippa ai fence IQR invece di eliminare |

#### Utilità

| Metodo | Descrizione |
|---|---|
| `normalize_column_names(df)` | Minuscolo + underscore (delega a `DataImporter.normalize_columns`) |
| `add_row_index(df, col_name, start)` | Aggiunge colonna indice progressivo |
| `export(df, path)` | Export a CSV, TSV, XLSX, JSON, Parquet, Feather, HTML, Pickle |

### 6.4 SQLHighlighter

`QSyntaxHighlighter` per l'editor SQL. Evidenzia con colori distinti:
- **Blu grassetto** — parole chiave SQL (SELECT, FROM, WHERE, JOIN, ecc., 35+ keywords)
- **Giallo** — nomi di funzione (pattern: `nome(`)
- **Arancione** — stringhe (`'...'` e `"..."`)
- **Verde corsivo** — commenti (`-- commento`)
- **Verde chiaro** — valori numerici

### 6.5 FilterDialog

`QDialog` per configurare un filtro ETL. Mostra:
- Combo colonna (popolato con le colonne del DataFrame corrente)
- Combo operatore (17 operatori da `ETLEngine.FILTER_OPERATORS`)
- Campo valore (disabilitato per operatori come `è vuoto`)
- Label di hint che spiega il formato del valore per operatori complessi
  (es. `in lista` → "Valori separati da virgola: A,B,C")

---

## 7. MainWindow — Tab Data Query

### 7.1 Tab A · Sorgenti Dati

Gestisce la lista di sorgenti dati da caricare.

| Metodo | Descrizione |
|---|---|
| `_build_sources_tab()` | Costruisce l'UI del tab |
| `_src_add_file()` | Aggiunge file singoli o multipli (dialog multi-selezione) |
| `_src_add_folder()` | Aggiunge una cartella intera |
| `_src_add_url()` | Aggiunge un URL HTTP/S con input dialog |
| `_src_add_sqlite()` | Aggiunge un file SQLite con file dialog |
| `_src_remove()` | Rimuove la sorgente selezionata |
| `_src_clear_all()` | Svuota la lista e l'anteprima |
| `_src_refresh()` | Aggiorna la QListWidget e l'etichetta info |
| `_load_source(source)` | Dispatcher: chiama il metodo DataImporter corretto in base a `source["kind"]` |
| `_src_preview()` | Carica le prime 200 righe nell'anteprima |
| `_src_load_to_etl()` | Carica l'intera sorgente e naviga al tab ETL |
| `_set_raw_df(df, label)` | **Punto centrale**: imposta `raw_df` e `working_df`, svuota lo stack ETL, aggiorna tutte le UI |

### 7.2 Tab B · Connessioni DB

Gestisce le connessioni ai database on-premise tramite SQLAlchemy.
Richiama automaticamente `require_optional()` e `require_provider()`
prima di ogni operazione reale.

**Driver on-premise supportati:**
SQLite, PostgreSQL, MySQL/MariaDB, MSSQL/SQL Server, Oracle,
IBM DB2, DuckDB, Access (ODBC), Firebird.

**Sotto-tab:**

**Nuova connessione**

| Campo | Descrizione |
|---|---|
| Tipo DBMS | Selezione da menu a tendina (aggiorna automaticamente hint, campi e URL preview) |
| Alias/Nome | Identificatore univoco per la connessione nel registro `_active_connections` |
| Host, Porta, Database | Parametri di connessione (disabilitati per DB basati su file) |
| File | Percorso file per SQLite, DuckDB, Access (con file browser) |
| Utente, Password | Credenziali (password nascondibile con toggle) |
| Extra URL | Parametri aggiuntivi nella query string (es. `charset=utf8`) |
| SSL/TLS, Pool, Timeout | Opzioni avanzate di connessione |

| Pulsante | Azione |
|---|---|
| "Testa connessione" | `_db_test_real()`: installa driver se mancante, apre connessione reale, esegue `SELECT 1` |
| "Connetti e salva" | `_db_connect_and_save()`: come sopra ma salva l'engine in `_active_connections` |
| "Apri SQLite..." | `_db_quick_sqlite()`: shortcut rapido per SQLite |
| "Da URL completa..." | `_db_from_url()`: connette da URL SQLAlchemy incollata direttamente |

**Connessioni salvate**

Mostra la lista di tutte le connessioni in `_active_connections` con
possibilità di: eseguire query rapida inline, importare una tabella
nel dataset corrente, testare la connessione, rimuoverla.

**Browser schema**

Esplora la struttura del database tramite `sqlalchemy.inspect()`:
- Albero gerarchico: Schema → Tabelle → Colonne
- Click su tabella: mostra colonne con tipo, nullable, default;
  PRIMARY KEY, FOREIGN KEY, indici
- Pulsanti: anteprima (prime 200 righe), carica tabella in ETL

**Metodi chiave:**

| Metodo | Descrizione |
|---|---|
| `_db_build_url()` | Costruisce la URL SQLAlchemy dai campi del form |
| `_db_update_url_preview()` | Aggiorna il label URL in tempo reale (oscura la password) |
| `_db_refresh_connection_lists(alias)` | Sincronizza `db_saved_list`, `schema_conn_combo`, `sql_conn_combo` e `cloud_conn_use_combo` |
| `_db_run_on(alias, sql)` | Esegue una query su una connessione attiva; gestisce sia SQLAlchemy (SQL standard) che SDK (MongoDB, InfluxDB, Elasticsearch) |

### 7.3 Tab C · Cloud Database

Gestisce le connessioni a 20 provider cloud. Ogni provider è configurato
nel dizionario `_CLOUD_PROVIDERS` con: gruppo, pacchetti pip, URL template,
porta default, campi richiesti e hint.

**Provider supportati per gruppo:**

| Gruppo | Provider |
|---|---|
| **AWS** | Amazon RDS (PostgreSQL/MySQL), Redshift, Athena |
| **GCP** | Google BigQuery, Cloud SQL (PostgreSQL), Cloud Spanner |
| **Azure** | Azure SQL Database, Synapse Analytics, PostgreSQL Flexible |
| **Snowflake** | Snowflake DWH |
| **Databricks** | Databricks SQL |
| **MongoDB** | MongoDB Atlas |
| **BaaS** | Supabase, Neon, CockroachDB, PlanetScale |
| **OLAP** | ClickHouse |
| **Time-Series** | InfluxDB 2.x |
| **Search** | Elasticsearch |

**Sotto-tab:**

**Connetti** — form dinamico che abilita solo i campi rilevanti per
il provider selezionato. Filtro per gruppo. Preview URL live.
Pulsanti: Test, Connetti e salva, Mostra pip install.

**Guida & Driver** — tabella testuale con pip install e note per tutti i provider.

**Template codice** — codice Python pronto da copiare per ogni provider,
con snippet specifici per SDK (MongoDB, InfluxDB, BigQuery, Elasticsearch, DynamoDB).

**Metodi chiave:**

| Metodo | Descrizione |
|---|---|
| `_cloud_filter_providers(group)` | Filtra il combo provider per gruppo |
| `_cloud_on_provider_changed()` | Abilita/disabilita campi e aggiorna hint |
| `_cloud_build_url()` | Compila l'URL template con i valori del form |
| `_cloud_connect()` | Installa driver, connette, salva in `_active_connections` |
| `_cloud_connect_sdk(alias, name, cfg)` | Connessione via SDK per provider non-SQL (MongoDB, InfluxDB, Elasticsearch) con `require_optional_group()` |
| `_cloud_update_template(name)` | Genera il codice Python template per il provider selezionato |

### 7.4 Tab D · Editor SQL

Editor SQL con syntax highlighting e esecuzione su dataset locale
o connessioni reali in `_active_connections`.

| Metodo | Descrizione |
|---|---|
| `_build_sql_tab()` | Costruisce UI: toolbar, editor, splitter, tabella risultati |
| `_sql_run()` | Esegue la query; locale = SQLite in-memory con tabella "dati"; remoto = usa engine da `_active_connections` |
| `_sql_to_etl()` | Invia il risultato dell'ultima query al tab ETL |
| `_sql_save()` / `_sql_open()` | Salva/carica file `.sql` |
| `_sql_toggle_theme()` / `_sql_apply_theme()` | Alterna tema scuro/chiaro dell'editor |

Nota: per le connessioni locali il dataset `working_df` viene
caricato in una tabella chiamata `dati` in SQLite in-memory.

### 7.5 Tab E · ETL / Trasformazioni

L'ETL è organizzato in 11 sotto-tab operativi, uno stack undo (max 20 livelli)
e un log persistente per sessione.

**Sotto-tab operativi:**

| Sotto-tab | Operazioni disponibili |
|---|---|
| **Colonne** | Converti tipo (7 tipi), riempi nulli (9 strategie), rinomina, elimina |
| **Filtri** | Aggiungi filtro (17 operatori), rimuovi outlier IQR per colonna |
| **Ordina** | Ordina su 1-2 colonne con direzione indipendente, mescola |
| **Aggrega** | GROUP BY + funzione aggregata, Pivot, Unpivot (melt) |
| **Testo** | 15 operazioni su colonne stringa |
| **Numerico** | 18 operazioni su colonne numeriche |
| **Data/Ora** | Estrai componenti datetime, calcola differenze temporali |
| **Formula** | Colonna calcolata (eval), colonna IF/ELSE, mappatura valori |
| **Reshape** | Mantieni colonne, elimina multiple, riordina |
| **Outlier** | Rimuovi outlier IQR, Cap/Winsorize su N colonne |
| **Campiona** | Per n righe o frazione, prime N, ultime N |

**Meccanismo undo:**

```python
# Prima di ogni trasformazione:
self._etl_push()   # salva copia di working_df nello stack

# In caso di errore:
self._etl_undo_stack.pop()   # rollback automatico

# Pulsante "↺ Annulla":
self._etl_undo()   # ripristina ultimo stato salvato
```

**Metodo centrale `_etl_apply(fn, description)`:**
```python
def _etl_apply(self, fn, description: str) -> None:
    self._etl_push()           # salva stato prima
    try:
        self.working_df = fn() # applica trasformazione
        self._etl_log(description)
        self._etl_refresh()    # aggiorna UI
    except Exception as exc:
        self._etl_undo_stack.pop()  # rollback su errore
        QMessageBox.critical(...)
```

**Export supportati:** CSV, TSV, Excel, JSON, Parquet, HTML, Pickle.

---

## 8. MainWindow — Tab Report

### 8.1 Header esportazione

Controlli globali per tutti gli export:
- Titolo e autore del documento
- Formato carta (A4, A3, Letter, Legal) e orientamento
- DPI per grafici rasterizzati (72–600)
- Pulsanti export: PDF, Excel, HTML, PPTX, PNG/SVG, CSV, ODT

I grafici generati nei sotto-tab vengono registrati in
`self._report_figures: dict[str, Figure]` e usati da tutti gli export.

### 8.2 Sotto-tab I · Panoramica Dataset

**`_rpt_run_overview()`** — profilazione automatica del dataset corrente:

1. **Tipi di colonna** — rileva numeriche, categoriche, datetime, booleane
2. **Valori nulli** — percentuale per colonna con flag ⚠ se > 30%
3. **Statistiche descrittive** — min, max, media, mediana, std, skewness, kurtosis, percentili (p05/p25/p75/p95)
4. **Cardinalità categoriche** — conteggio valori unici + top-3 frequenti
5. **Correlazioni significative** — coppie con |r| ≥ 0.7
6. **Outlier IQR** — conteggio per colonna
7. **Suggerimenti** — tipi di analisi applicabili in base ai dati

**`_rpt_build_overview_charts()`** — genera automaticamente:
- Barra orizzontale percentuale valori mancanti
- Torta distribuzione tipi di colonna
- Box-plot variabili numeriche (max 12)
- Heatmap correlazione (max 14 colonne)
- Barre frequenze prima colonna categorica

### 8.3 Sotto-tab II · Grafici Base

15 tipi di grafico configurabili con: asse X/Y, raggruppamento (hue),
n° bin, funzione di aggregazione, palette colori, scala logaritmica,
griglia, annotazioni, KDE, cumulativo.

| Grafico | Descrizione |
|---|---|
| Istogramma | Con opzione KDE sovrapposta e modalità cumulativa |
| Box-plot | Con o senza raggruppamento per categoria |
| Barre (conteggio) | Frequenze assolute, annotazioni opzionali |
| Barre (aggregato) | GROUP BY colonna X, aggregazione Y |
| Torta / Donut | Top-12 categorie, foro centrale |
| Scatter plot | Con raggruppamento per colore |
| Line chart | Con area riempita opzionale |
| Area chart | Riempimento sotto la curva |
| Violin plot | Distribuzione con mediana |
| Strip / Swarm | Punti con jitter orizzontale |
| Bar chart orizzontale | Top-25 categorie |
| Bubble chart | Dimensione bolle proporzionale a Y |
| Heatmap pivot | Tabella pivot colorata |
| Pareto chart | Con curva cumulata e linea 80% |
| Waterfall chart | Delta positivi/negativi colorati |

### 8.4 Sotto-tab III · Statistiche Avanzate

17 analisi con interfaccia configurabile (colonne X/Y, raggruppamento,
n° componenti PCA, distribuzione da fittare, soglia α):

| Analisi | Libreria | Descrizione |
|---|---|---|
| Matrice correlazione | matplotlib | Heatmap Pearson con valori annotati |
| Scatter matrix | matplotlib | Pair-plot per max 6 variabili |
| PCA | scikit-learn | Score plot + Scree plot varianza spiegata |
| Fitting distribuzione | scipy | KS test dopo fit su 8 distribuzioni |
| Q-Q plot | scipy | Normalità grafica con r² linea riferimento |
| Test Shapiro-Wilk | scipy | Test formale normalità con p-value |
| Test Mann-Whitney | scipy | Confronto 2 gruppi non-parametrico |
| Test ANOVA | scipy | F-test su 3+ gruppi |
| Test Chi-quadro | scipy | Indipendenza variabili categoriche con heatmap contingenza |
| Decomposizione stagionale | statsmodels | Trend + stagionalità + residuo |
| ACF / PACF | statsmodels | Correlogrammi per analisi serie temporali |
| CDF empirica | scipy | ECDF vs CDF teorica |
| Outlier Mahalanobis | numpy | Distanza multivariata con soglia 97.5° percentile |
| Curva di Lorenz / Gini | numpy | Concentrazione + coefficiente Gini |
| Radar / Spider chart | matplotlib | Profilo multi-variabile su assi polari |
| Funnel chart | matplotlib | Proporzioni decrescenti (pipeline/conversioni) |
| Pareto esteso (ABC) | matplotlib | Classificazione A (80%), B (95%), C (100%) |

### 8.5 Sotto-tab IV · Previsioni & Probabilità

12 metodi di previsione con interfaccia configurabile (colonne X/Y,
orizzonte temporale, grado polinomiale, livello IC, n° simulazioni, finestra MA):

| Metodo | Descrizione |
|---|---|
| Regressione lineare (IC) | y=ax+b con banda di confidenza proiettata |
| Regressione polinomiale | Curva grado n con proiezione |
| Media mobile SMA/EMA | Con proiezione piatta dell'EMA |
| Smoothing esponenziale | Holt-Winters (statsmodels) |
| Previsione naive | Baseline: ultimo valore / seasonal naive |
| ARIMA | Auto-order via AIC (statsmodels) |
| Decomposizione + trend | Estrae trend lineare e proietta |
| Monte Carlo | N percorsi gaussiani, fan chart p05/p25/p50/p75/p95 |
| Bootstrap PI | Bande di predizione non-parametriche |
| VaR & CVaR | Value at Risk e Conditional VaR su rendimenti |
| Intervalli di predizione | Banda individuale (più larga degli IC) |
| Crescita exp./logistica | Fit y=a·e^(bx) e curva S logistica |

### 8.6 Export

| Formato | Implementazione |
|---|---|
| **PDF** | `matplotlib.backends.backend_pdf.PdfPages` — copertina + una pagina per grafico |
| **Excel** | `pandas.ExcelWriter` — foglio Dataset + foglio Statistiche + foglio Profilazione |
| **HTML** | Grafici embedded come PNG base64 + dataset come tabella HTML |
| **PPTX** | `python-pptx` (installato on-demand) — slide copertina + una slide per grafico |
| **ODT/Word** | `python-docx` (installato on-demand) — heading + grafici come immagini |
| **PNG/SVG** | `Figure.savefig()` — un file per grafico in cartella scelta |
| **CSV** | `df.describe()` — statistiche descrittive in CSV |

---

## 9. MainWindow — Tab Analisi ML

Il vecchio placeholder è stato eliminato. La pagina Statistica e ML usa `healthcare_analysis_tab.py`: selettore registro visite, produzione SSR annuale o domanda settimanale CSV. Sono disponibili gli indicatori sanitari e Random Forest con validazione cronologica e baseline, solo su serie che soddisfano il contratto dati. Risultati invalidati dopo errori o cambio di selezione; previsioni e pubblicazione abilitate quando disponibili. Le altre famiglie di modelli restano nel catalogo pianificato di `HEALTHCARE_ANALYTICS_DESIGN.md`.

---

## 10. Librerie e dipendenze

### 10.1 Librerie core (LIBRARIES.md — installate automaticamente)

| Libreria | Versione minima | Uso |
|---|---|---|
| `PySide6` | 6.4 | Framework GUI Qt |
| `pandas` | 1.5 | Manipolazione DataFrame |
| `openpyxl` | 3.0 | Lettura/scrittura XLSX |
| `pyarrow` | 10.0 | Parquet e Feather |
| `matplotlib` | 3.6 | Grafici e visualizzazioni |
| `numpy` | 1.23 | Calcolo numerico vettoriale |
| `scipy` | 1.9 | Test statistici, fitting, KDE |
| `scikit-learn` | 1.1 | PCA, StandardScaler |
| `statsmodels` | 0.13 | ARIMA, decomposizione stagionale, ACF/PACF |
| `sqlalchemy` | 2.0 | ORM e connessioni DB |

### 10.2 Librerie opzionali (LIBRARIES_OPTIONAL.md — on-demand)

Installate automaticamente quando l'utente tenta di usarle per la prima volta,
tramite il sistema di consenso descritto in §4.7.

**Driver on-premise:**

| Libreria | Provider |
|---|---|
| `psycopg2-binary` | PostgreSQL, Supabase, Neon, Azure PG, Cloud SQL |
| `pymysql` | MySQL, MariaDB, PlanetScale |
| `pyodbc` | MSSQL, SQL Server, Azure SQL, Synapse, Access |
| `oracledb` | Oracle Database |
| `duckdb` + `duckdb-engine` | DuckDB locale |
| `fdb` | Firebird |
| `ibm_db` + `ibm_db_sa` | IBM DB2 |

**Driver cloud:**

| Libreria | Provider |
|---|---|
| `redshift-connector` + `sqlalchemy-redshift` | Amazon Redshift |
| `PyAthena` | Amazon Athena |
| `google-cloud-bigquery` + `sqlalchemy-bigquery` | Google BigQuery |
| `cloud-sql-python-connector` | Google Cloud SQL |
| `google-cloud-spanner` + `sqlalchemy-spanner` | Google Cloud Spanner |
| `azure-cosmos` | Azure Cosmos DB |
| `snowflake-connector-python` + `snowflake-sqlalchemy` | Snowflake |
| `databricks-sql-connector` + `sqlalchemy-databricks` | Databricks SQL |
| `pymongo` | MongoDB Atlas |
| `influxdb-client` | InfluxDB 2.x |
| `elasticsearch` + `eland` | Elasticsearch |
| `clickhouse-driver` + `sqlalchemy-clickhouse` | ClickHouse |
| `sqlalchemy-cockroachdb` | CockroachDB |
| `boto3` | AWS DynamoDB, S3 |

**Export:**

| Libreria | Funzione |
|---|---|
| `python-pptx` | Export PowerPoint (.pptx) |
| `python-docx` | Export Word/ODT (.docx) |

---

## 11. Flusso dati

### 11.1 Caricamento

```
Utente seleziona sorgente (file / cartella / URL / SQLite / DB)
                │
                ▼
         DataImporter.load_*()
                │
                ▼
         pd.DataFrame grezzo
                │
                ▼
        _set_raw_df(df, label)
         ├── raw_df = df          (copia immutabile)
         ├── working_df = df      (copia modificabile)
         ├── etl_steps.clear()
         └── _etl_refresh()      (aggiorna UI ETL)
```

### 11.2 Trasformazione ETL

```
Utente configura trasformazione nel sotto-tab ETL
                │
                ▼
         _etl_apply(fn, description)
         ├── _etl_push()           → stack_undo.append(working_df.copy())
         ├── working_df = fn()     → DataFrame trasformato
         ├── _etl_log(description) → etl_steps.append(...)
         └── _etl_refresh()        → aggiorna tabella, combo, log
```

### 11.3 Analisi e report

```
working_df ──► SQL Editor ──► pd.read_sql_query() ──► sql_result_df
                                                              │
                                                              ▼
                                                    invia a ETL se richiesto

working_df ──► Report ──► matplotlib Figure ──► _report_figures[titolo]
                                                              │
                                                              ▼
                                                    export PDF/PPTX/HTML/...
```

---

## 12. Estendere l'applicazione

### Aggiungere un nuovo formato di file

1. Aggiungere l'estensione a `SUPPORTED_EXTENSIONS` in `DataImporter`
2. Aggiungere un ramo `elif suffix == ".xyz":` in `DataImporter.load_file()`
3. Aggiornare il filtro del file dialog in `_src_add_file()`
4. Aggiungere `".xyz"` al filtro export in `ETLEngine.export()` se necessario

### Aggiungere una trasformazione ETL

1. Aggiungere un metodo statico a `ETLEngine` (deve restituire un DataFrame puro)
2. Aggiungere il controllo UI nel sotto-tab appropriato in `_build_etl_ops_*()`
3. Aggiungere il metodo `_etl_nome_azione()` che chiama `_etl_apply(lambda: ..., "desc")`

### Aggiungere un provider cloud

1. Aggiungere una voce al dizionario `_CLOUD_PROVIDERS` in `MainWindow`
2. Aggiungere la lista pacchetti a `PROVIDER_PACKAGES` in `dependency_manager.py`
3. Se il provider usa SDK (non SQLAlchemy), aggiungere un ramo in `_cloud_connect_sdk()`
4. Aggiungere il template Python in `_cloud_update_template()`

### Aggiungere un tipo di grafico

1. Aggiungere la voce al `QComboBox` in `_build_rpt_charts_tab()`
2. Aggiungere il ramo `elif t == "Nome grafico":` in `_rpt_ch_generate()`
3. Collegare `_rpt_ch_update_controls()` per abilitare/disabilitare i controlli

### Aggiungere una libreria opzionale

1. Aggiungere una riga commentata in `LIBRARIES_OPTIONAL.md`:
   `# nome-pacchetto   → Descrizione uso`
2. Aggiungere la mappatura in `_IMPORT_NAME_MAP` se nome pip ≠ nome modulo
3. Aggiungere alla mappa `PROVIDER_PACKAGES` se associata a un provider
4. Usare `require_optional("nome-pacchetto", reason="...")` nel codice
   che la usa, prima di importarla

---

*Documentazione generata automaticamente — HealthReport Studio v1.0*

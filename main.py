"""
HealthReport Studio
Applicazione desktop per importazione, trasformazione e analisi dati.

Struttura tab principale:
  1. Data Query  → sorgenti file/DB, SQL editor, ETL
  2. Report      → (futuro) report base e avanzati
  3. Analisi ML  → (futuro) regressione e machine learning

File richiesti nella stessa cartella:
    main.py
    dependency_manager.py
    LIBRARIES.md

Avvio:
    python main.py
"""

from __future__ import annotations

# ── Gestione dipendenze ────────────────────────────────────────────────────────
# DEVE restare prima di qualsiasi import esterno (pandas, matplotlib, PySide6…).
# dependency_manager.py usa solo librerie standard di Python.
from dependency_manager import (
    ensure_dependencies_before_startup,
    get_python_executable,
    require_optional,
    require_optional_group,
    require_provider,
    open_optional_manager,
    is_installed,
)
import sys

try:
    ensure_dependencies_before_startup(markdown_path="LIBRARIES.md", auto_update=True)
except RuntimeError as e:
    print(f"\n❌ Errore fatale: {e}")
    sys.exit(1)

# Forza l'esecuzione con il venv, se non già attivo
import os
if "venv" not in sys.executable:
    venv_python = get_python_executable()
    if "venv" in venv_python:
        print(f"\n❌ Devi avviare l'applicazione con il virtual environment:")
        print(f"   {venv_python} main.py")
        sys.exit(1)

# ── Import standard ────────────────────────────────────────────────────────────
import io
import math
import sqlite3
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, cast
import importlib
import xml.etree.ElementTree as ET

# ── Import di terze parti ──────────────────────────────────────────────────────
import numpy as np
import pandas as pd
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib
matplotlib.use("Agg")          # renderer non-interattivo, thread-safe con Qt
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QRegularExpression, QThread, Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QSplitter,
    QStatusBar,
    QTableView,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ══════════════════════════════════════════════════════════════════════════════
# MODELLO TABELLARE QT
# ══════════════════════════════════════════════════════════════════════════════

class PandasTableModel(QAbstractTableModel):
    """Adattatore tra pandas DataFrame e QTableView."""

    def __init__(self, dataframe: Optional[pd.DataFrame] = None) -> None:
        super().__init__()
        self._df = pd.DataFrame() if dataframe is None else dataframe.copy()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self._df.iat[index.row(), index.column()]
        return "" if pd.isna(value) else str(value)

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)

    def update_dataframe(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df.copy()
        self.endResetModel()

    @property
    def dataframe(self) -> pd.DataFrame:
        return self._df.copy()


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTATORE DATI
# ══════════════════════════════════════════════════════════════════════════════

SUPPORTED_EXTENSIONS = {
    ".csv", ".tsv",
    ".xlsx", ".xls",
    ".json",
    ".xml",
    ".parquet",
    ".feather",
    ".orc",
    ".db", ".sqlite",
}


class DataImporter:
    """Carica dati da sorgenti eterogenee restituendo sempre un DataFrame."""

    @staticmethod
    def load_file(path: Path, **kwargs) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path, **kwargs)
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t", **kwargs)
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path, **kwargs)
        if suffix == ".json":
            return pd.read_json(path, **kwargs)
        if suffix == ".xml":
            return DataImporter._load_xml(path)
        if suffix == ".parquet":
            return pd.read_parquet(path, **kwargs)
        if suffix == ".feather":
            return pd.read_feather(path, **kwargs)
        if suffix == ".orc":
            return pd.read_orc(path, **kwargs)
        if suffix in {".db", ".sqlite"}:
            return DataImporter._load_sqlite_first_table(path)
        raise ValueError(
            f"Formato non supportato: '{suffix}'. "
            f"Usa: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    @staticmethod
    def _load_xml(path: Path) -> pd.DataFrame:
        try:
            return pd.read_xml(path)
        except Exception:
            tree = ET.parse(path)
            root = tree.getroot()
            rows = []
            for child in root:
                row = {sub.tag: sub.text for sub in child}
                if not row:
                    row = child.attrib
                rows.append(row)
            return pd.DataFrame(rows)

    @staticmethod
    def _load_sqlite_first_table(path: Path) -> pd.DataFrame:
        conn = sqlite3.connect(path)
        try:
            tables = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table'", conn
            )
            if tables.empty:
                return pd.DataFrame()
            first = tables.iloc[0]["name"]
            return pd.read_sql_query(f"SELECT * FROM [{first}] LIMIT 5000", conn)
        finally:
            conn.close()

    @staticmethod
    def load_folder(path: Path) -> pd.DataFrame:
        if not path.is_dir():
            raise ValueError("Il percorso non è una cartella.")
        frames = []
        for child in sorted(path.iterdir()):
            if child.suffix.lower() in SUPPORTED_EXTENSIONS - {".db", ".sqlite"}:
                try:
                    frames.append(DataImporter.load_file(child))
                except Exception:
                    continue
        if not frames:
            raise ValueError("Nessun file supportato trovato nella cartella.")
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def load_url(url: str) -> pd.DataFrame:
        response = urllib.request.urlopen(url)
        raw = response.read()
        suffix = Path(url.split("?")[0]).suffix.lower()
        ct = response.headers.get("Content-Type", "").lower()
        bio = BytesIO(raw)
        if suffix == ".csv" or "text/csv" in ct:
            return pd.read_csv(bio)
        if suffix == ".tsv":
            return pd.read_csv(bio, sep="\t")
        if suffix in {".xlsx", ".xls"} or "spreadsheet" in ct:
            return pd.read_excel(bio)
        if suffix == ".json" or "application/json" in ct:
            return pd.read_json(bio)
        if suffix == ".parquet":
            return pd.read_parquet(bio)
        if suffix == ".xml":
            return pd.read_xml(bio)
        try:
            return pd.read_json(bio)
        except Exception:
            bio.seek(0)
        try:
            return pd.read_csv(bio)
        except Exception as exc:
            raise ValueError(f"Impossibile leggere il contenuto dell'URL: {exc}")

    @staticmethod
    def load_sqlite(path: Path, query: str) -> pd.DataFrame:
        if not path.exists():
            raise FileNotFoundError(f"File SQLite non trovato: {path}")
        conn = sqlite3.connect(path)
        try:
            return pd.read_sql_query(query, conn)
        finally:
            conn.close()

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [
            str(c).strip().lower()
            .replace(" ", "_").replace("-", "_")
            .replace("/", "_").replace(".", "_")
            for c in df.columns
        ]
        return df


# ══════════════════════════════════════════════════════════════════════════════
# MOTORE ETL
# ══════════════════════════════════════════════════════════════════════════════

class ETLEngine:
    """
    Motore ETL con 30+ trasformazioni su DataFrame pandas.

    Ogni metodo è puro (restituisce un nuovo DataFrame, non modifica l'originale)
    e solleva ValueError / TypeError con messaggi descrittivi in italiano.
    """

    # ── FILTRI ────────────────────────────────────────────────────────────────

    FILTER_OPERATORS = [
        "==", "!=", ">", ">=", "<", "<=",
        "contiene", "non contiene",
        "inizia con", "finisce con",
        "regex",
        "è vuoto", "non è vuoto",
        "in lista",          # valore = "a,b,c"
        "non in lista",
        "tra (numerico)",    # valore = "10,50"
        "outlier IQR",       # nessun valore richiesto
    ]

    @staticmethod
    def filter_rows(df: pd.DataFrame, column: str, operator: str, value: str = "") -> pd.DataFrame:
        if column not in df.columns:
            raise ValueError(f"Colonna «{column}» non trovata.")
        col = df[column]

        def _num(v: str) -> Optional[float]:
            try: return float(v)
            except ValueError: return None

        num = _num(value)

        if operator == "==":
            mask = (pd.to_numeric(col, errors="coerce") == num) if num is not None \
                   else (col.astype(str) == value)
        elif operator == "!=":
            mask = (pd.to_numeric(col, errors="coerce") != num) if num is not None \
                   else (col.astype(str) != value)
        elif operator == ">" and num is not None:
            mask = pd.to_numeric(col, errors="coerce") > num
        elif operator == ">=" and num is not None:
            mask = pd.to_numeric(col, errors="coerce") >= num
        elif operator == "<" and num is not None:
            mask = pd.to_numeric(col, errors="coerce") < num
        elif operator == "<=" and num is not None:
            mask = pd.to_numeric(col, errors="coerce") <= num
        elif operator == "contiene":
            mask = col.astype(str).str.contains(value, na=False, case=False, regex=False)
        elif operator == "non contiene":
            mask = ~col.astype(str).str.contains(value, na=False, case=False, regex=False)
        elif operator == "inizia con":
            mask = col.astype(str).str.startswith(value, na=False)
        elif operator == "finisce con":
            mask = col.astype(str).str.endswith(value, na=False)
        elif operator == "regex":
            mask = col.astype(str).str.contains(value, na=False, case=False, regex=True)
        elif operator == "è vuoto":
            mask = col.isna() | (col.astype(str).str.strip() == "")
        elif operator == "non è vuoto":
            mask = col.notna() & (col.astype(str).str.strip() != "")
        elif operator == "in lista":
            items = [v.strip() for v in value.split(",")]
            mask = col.astype(str).isin(items)
        elif operator == "non in lista":
            items = [v.strip() for v in value.split(",")]
            mask = ~col.astype(str).isin(items)
        elif operator == "tra (numerico)":
            parts = [v.strip() for v in value.split(",")]
            if len(parts) != 2:
                raise ValueError("«tra (numerico)» richiede due valori separati da virgola: min,max")
            lo, hi = float(parts[0]), float(parts[1])
            num_col = pd.to_numeric(col, errors="coerce")
            mask = (num_col >= lo) & (num_col <= hi)
        elif operator == "outlier IQR":
            num_col = pd.to_numeric(col, errors="coerce")
            q1, q3 = num_col.quantile(0.25), num_col.quantile(0.75)
            iqr = q3 - q1
            mask = (num_col < q1 - 1.5 * iqr) | (num_col > q3 + 1.5 * iqr)
        else:
            raise ValueError(f"Operatore non riconosciuto: {operator!r}")

        return df[mask].reset_index(drop=True)

    # ── PULIZIA ───────────────────────────────────────────────────────────────

    @staticmethod
    def sort_rows(df: pd.DataFrame, columns: List[str], ascending: List[bool]) -> pd.DataFrame:
        """Ordina su una o più colonne con direzione indipendente per ognuna."""
        if not columns:
            raise ValueError("Specificare almeno una colonna di ordinamento.")
        return df.sort_values(columns, ascending=ascending, ignore_index=True)

    @staticmethod
    def drop_duplicates(df: pd.DataFrame, subset: Optional[List[str]] = None,
                        keep: Literal["first", "last", False] = "first") -> pd.DataFrame:
        """Rimuove duplicati. keep: 'first' | 'last' | False (rimuove tutti)."""
        return df.drop_duplicates(subset=subset or None, keep=keep,
                                  ignore_index=True)

    @staticmethod
    def drop_nulls(df: pd.DataFrame, subset: Optional[List[str]] = None,
                   thresh: Optional[int] = None) -> pd.DataFrame:
        """Elimina righe con nulli. thresh = n. minimo di valori NON nulli richiesti."""
        return df.dropna(subset=subset or None, thresh=thresh).reset_index(drop=True)

    @staticmethod
    def fill_nulls(df: pd.DataFrame, column: str, strategy: str,
                   fill_value: str = "") -> pd.DataFrame:
        """
        Strategie: 'valore', 'media', 'mediana', 'moda', 'forward fill', 'backward fill',
                   'interpolazione lineare', 'zero', 'stringa vuota'.
        """
        df = df.copy()
        col = df[column]
        s = strategy.lower().strip()
        if s == "valore":
            df[column] = col.fillna(fill_value)
        elif s == "media":
            df[column] = col.fillna(pd.to_numeric(col, errors="coerce").mean())
        elif s == "mediana":
            df[column] = col.fillna(pd.to_numeric(col, errors="coerce").median())
        elif s == "moda":
            mode = col.mode()
            df[column] = col.fillna(mode.iloc[0] if not mode.empty else fill_value)
        elif s == "forward fill":
            df[column] = col.ffill()
        elif s == "backward fill":
            df[column] = col.bfill()
        elif s == "interpolazione lineare":
            df[column] = pd.to_numeric(col, errors="coerce").interpolate(method="linear")
        elif s == "zero":
            df[column] = col.fillna(0)
        elif s == "stringa vuota":
            df[column] = col.fillna("")
        else:
            raise ValueError(f"Strategia non riconosciuta: {strategy!r}")
        return df

    @staticmethod
    def drop_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
        return df.drop(columns=[column])

    @staticmethod
    def drop_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """Elimina più colonne in una sola operazione."""
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(f"Colonne non trovate: {missing}")
        return df.drop(columns=columns)

    @staticmethod
    def keep_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """Mantiene solo le colonne specificate (scarta tutte le altre)."""
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(f"Colonne non trovate: {missing}")
        return df[columns].copy()

    @staticmethod
    def rename_column(df: pd.DataFrame, old: str, new: str) -> pd.DataFrame:
        if old not in df.columns:
            raise ValueError(f"Colonna «{old}» non trovata.")
        if new in df.columns:
            raise ValueError(f"Esiste già una colonna chiamata «{new}».")
        return df.rename(columns={old: new})

    @staticmethod
    def rename_columns_map(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
        """Rinomina più colonne contemporaneamente con un dizionario {vecchio: nuovo}."""
        return df.rename(columns=mapping)

    @staticmethod
    def reorder_columns(df: pd.DataFrame, new_order: List[str]) -> pd.DataFrame:
        """Riordina le colonne. Le colonne non in new_order vengono aggiunte in fondo."""
        existing = [c for c in new_order if c in df.columns]
        rest     = [c for c in df.columns if c not in existing]
        return df[existing + rest]

    # ── TIPO / CONVERSIONE ────────────────────────────────────────────────────

    @staticmethod
    def cast_column(df: pd.DataFrame, column: str, dtype: str,
                    date_format: str = "") -> pd.DataFrame:
        """
        Tipi supportati: string, int, float, datetime, boolean, category, timedelta.
        Per datetime accetta un format opzionale (es. '%d/%m/%Y').
        """
        df = df.copy()
        col = df[column]
        d = dtype.lower()
        if d == "string":
            df[column] = col.astype("string")
        elif d == "int":
            df[column] = pd.to_numeric(col, errors="coerce").astype("Int64")
        elif d == "float":
            df[column] = pd.to_numeric(col, errors="coerce")
        elif d == "datetime":
            kw: Dict[str, Any] = {"errors": "coerce", "dayfirst": True}
            if date_format:
                kw["format"] = date_format
            df[column] = pd.to_datetime(col, **kw)
        elif d == "boolean":
            mapping = {"true": True, "false": False, "1": True, "0": False,
                       "yes": True, "no": False, "si": True, "sì": True}
            df[column] = col.astype(str).str.lower().map(mapping).astype("boolean")
        elif d == "category":
            df[column] = col.astype("category")
        elif d == "timedelta":
            df[column] = pd.to_timedelta(col, errors="coerce")
        else:
            raise ValueError(f"Tipo non supportato: {dtype!r}")
        return df

    # ── TRASFORMAZIONI TESTO ──────────────────────────────────────────────────

    @staticmethod
    def text_transform(df: pd.DataFrame, column: str, operation: str,
                       extra: str = "") -> pd.DataFrame:
        """
        Operazioni: maiuscolo, minuscolo, title case, strip, lstrip, rstrip,
                    sostituisci (extra='vecchio→nuovo'), prefisso, suffisso,
                    estrai regex (extra='pattern'), padding sinistro/destro,
                    lunghezza (crea col_len), split (extra='sep|pos').
        """
        df = df.copy()
        s = df[column].astype(str)
        op = operation.lower().strip()
        if op == "maiuscolo":          df[column] = s.str.upper()
        elif op == "minuscolo":        df[column] = s.str.lower()
        elif op == "title case":       df[column] = s.str.title()
        elif op == "strip":            df[column] = s.str.strip()
        elif op == "lstrip":           df[column] = s.str.lstrip()
        elif op == "rstrip":           df[column] = s.str.rstrip()
        elif op == "sostituisci":
            if "→" not in extra:
                raise ValueError("extra deve essere 'vecchio→nuovo'")
            old, new = extra.split("→", 1)
            df[column] = s.str.replace(old, new, regex=False)
        elif op == "prefisso":
            df[column] = extra + s
        elif op == "suffisso":
            df[column] = s + extra
        elif op == "estrai regex":
            df[column] = s.str.extract(f"({extra})", expand=False)
        elif op == "lunghezza":
            df[f"{column}_len"] = s.str.len()
        elif op == "split":
            sep, _, pos_s = extra.partition("|")
            pos = int(pos_s) if pos_s.strip().lstrip("-").isdigit() else 0
            df[column] = s.str.split(sep).str[pos]
        elif op == "rimuovi spazi multipli":
            import re as _re
            df[column] = s.str.replace(r"\s+", " ", regex=True).str.strip()
        elif op == "rimuovi caratteri speciali":
            df[column] = s.str.replace(r"[^\w\s]", "", regex=True)
        elif op == "codifica url":
            import urllib.parse
            df[column] = s.apply(urllib.parse.quote_plus)
        else:
            raise ValueError(f"Operazione testo non riconosciuta: {operation!r}")
        return df

    # ── TRASFORMAZIONI NUMERICHE ──────────────────────────────────────────────

    @staticmethod
    def numeric_transform(df: pd.DataFrame, column: str, operation: str,
                          value: str = "") -> pd.DataFrame:
        """
        Operazioni: arrotonda, assoluto, logaritmo, radice quadrata,
                    normalizza 0-1, standardizza (z-score),
                    clip (value='min,max'), potenza, percentuale sul totale,
                    rank, bin (value='n_bins'), cumsum, cumprod, diff.
        """
        df = df.copy()
        col = pd.to_numeric(df[column], errors="coerce")
        op = operation.lower().strip()

        if op == "arrotonda":
            decimali = int(value) if value.strip().lstrip("-").isdigit() else 2
            df[column] = col.round(decimali)
        elif op == "assoluto":
            df[column] = col.abs()
        elif op == "logaritmo":
            df[column] = np.log(col.clip(lower=1e-12))
        elif op == "log10":
            df[column] = np.log10(col.clip(lower=1e-12))
        elif op == "radice quadrata":
            df[column] = np.sqrt(col.clip(lower=0))
        elif op == "normalizza 0-1":
            mn, mx = col.min(), col.max()
            df[column] = (col - mn) / (mx - mn + 1e-12)
        elif op == "standardizza (z-score)":
            df[column] = (col - col.mean()) / (col.std() + 1e-12)
        elif op == "clip":
            parts = [v.strip() for v in value.split(",")]
            if len(parts) != 2:
                raise ValueError("clip richiede 'min,max'")
            df[column] = col.clip(lower=float(parts[0]), upper=float(parts[1]))
        elif op == "potenza":
            exp = float(value) if value.strip() else 2.0
            df[column] = col ** exp
        elif op == "percentuale sul totale":
            df[column] = col / col.sum() * 100
        elif op == "rank":
            df[f"{column}_rank"] = col.rank(method="average")
        elif op == "bin":
            n = int(value) if value.strip().isdigit() else 5
            df[f"{column}_bin"] = pd.cut(col, bins=n, labels=False)
        elif op == "cumsum":
            df[f"{column}_cumsum"] = col.cumsum()
        elif op == "cumprod":
            df[f"{column}_cumprod"] = col.cumprod()
        elif op == "diff":
            periodi = int(value) if value.strip().lstrip("-").isdigit() else 1
            df[f"{column}_diff"] = col.diff(periodi)
        elif op == "shift":
            periodi = int(value) if value.strip().lstrip("-").isdigit() else 1
            df[f"{column}_shift"] = col.shift(periodi)
        elif op == "rolling mean":
            w = int(value) if value.strip().isdigit() else 3
            df[f"{column}_rm{w}"] = col.rolling(w).mean()
        elif op == "rolling std":
            w = int(value) if value.strip().isdigit() else 3
            df[f"{column}_rs{w}"] = col.rolling(w).std()
        else:
            raise ValueError(f"Operazione numerica non riconosciuta: {operation!r}")
        return df

    # ── DATA/ORA ──────────────────────────────────────────────────────────────

    @staticmethod
    def datetime_extract(df: pd.DataFrame, column: str,
                         parts: List[str]) -> pd.DataFrame:
        """
        Estrae componenti datetime in nuove colonne.
        parts: lista di 'anno','mese','giorno','ora','minuto','secondo',
               'giorno_settimana','numero_settimana','trimestre','is_weekend'.
        """
        df = df.copy()
        dt = pd.to_datetime(df[column], errors="coerce", dayfirst=True)
        mapping = {
            "anno":            dt.dt.year,
            "mese":            dt.dt.month,
            "giorno":          dt.dt.day,
            "ora":             dt.dt.hour,
            "minuto":          dt.dt.minute,
            "secondo":         dt.dt.second,
            "giorno_settimana":dt.dt.dayofweek,
            "numero_settimana":dt.dt.isocalendar().week.astype("Int64"),
            "trimestre":       dt.dt.quarter,
            "is_weekend":      (dt.dt.dayofweek >= 5).astype("boolean"),
            "nome_mese":       dt.dt.month_name(),
            "nome_giorno":     dt.dt.day_name(),
            "unix_timestamp":  dt.astype("int64") // 10**9,
        }
        for part in parts:
            key = part.lower().strip()
            if key in mapping:
                df[f"{column}_{key}"] = mapping[key]
        return df

    @staticmethod
    def datetime_diff(df: pd.DataFrame, col1: str, col2: str,
                      unit: str = "days", new_col: str = "") -> pd.DataFrame:
        """Calcola la differenza temporale tra due colonne datetime."""
        df = df.copy()
        dt1 = pd.to_datetime(df[col1], errors="coerce", dayfirst=True)
        dt2 = pd.to_datetime(df[col2], errors="coerce", dayfirst=True)
        diff = dt1 - dt2
        units = {
            "days":    diff.dt.days,
            "hours":   diff / pd.Timedelta(hours=1),
            "minutes": diff / pd.Timedelta(minutes=1),
            "seconds": diff / pd.Timedelta(seconds=1),
            "weeks":   diff.dt.days / 7,
            "months":  diff.dt.days / 30.44,
            "years":   diff.dt.days / 365.25,
        }
        if unit not in units:
            raise ValueError(f"Unità non riconosciuta: {unit!r}")
        name = new_col or f"{col1}_minus_{col2}_{unit}"
        df[name] = units[unit]
        return df

    # ── COLONNE CALCOLATE ─────────────────────────────────────────────────────

    @staticmethod
    def add_formula_column(df: pd.DataFrame, new_col: str,
                           formula: str) -> pd.DataFrame:
        """
        Crea una colonna calcolata tramite df.eval().
        Esempio formula: 'prezzo * quantita * 1.22'
        Le colonne del dataframe sono accessibili per nome.
        """
        if not new_col.strip():
            raise ValueError("Il nome della nuova colonna non può essere vuoto.")
        try:
            result = df.eval(formula)
        except Exception as exc:
            raise ValueError(f"Errore nella formula: {exc}") from exc
        df = df.copy()
        df[new_col] = result
        return df

    @staticmethod
    def add_conditional_column(df: pd.DataFrame, new_col: str,
                               condition_col: str, operator: str,
                               condition_val: str,
                               true_val: str, false_val: str) -> pd.DataFrame:
        """Aggiunge una colonna con valore condizionale (if/else)."""
        mask_df = ETLEngine.filter_rows(df, condition_col, operator, condition_val)
        mask = df.index.isin(mask_df.index)
        df = df.copy()
        df[new_col] = false_val
        df.loc[mask, new_col] = true_val
        return df

    @staticmethod
    def add_map_column(df: pd.DataFrame, source_col: str,
                       new_col: str, mapping_str: str) -> pd.DataFrame:
        """
        Mappa valori di source_col in new_col tramite una stringa dizionario.
        Formato mapping_str: 'A→1,B→2,C→3'
        """
        mapping: Dict[str, str] = {}
        for pair in mapping_str.split(","):
            pair = pair.strip()
            if "→" in pair:
                k, v = pair.split("→", 1)
                mapping[k.strip()] = v.strip()
        if not mapping:
            raise ValueError("Nessun mapping valido trovato. Formato: 'A→1,B→2'")
        df = df.copy()
        df[new_col] = df[source_col].astype(str).map(mapping)
        return df

    # ── JOIN / MERGE ──────────────────────────────────────────────────────────

    @staticmethod
    def merge(df: pd.DataFrame, right: pd.DataFrame,
              on: List[str], how: Literal["left", "right", "outer", "inner", "cross"] = "inner") -> pd.DataFrame:
        """Unisce due DataFrame. how: 'inner','left','right','outer','cross'."""
        return pd.merge(df, right, on=on or None, how=how)

    @staticmethod
    def concat_rows(dfs: List[pd.DataFrame],
                    ignore_index: bool = True) -> pd.DataFrame:
        """Concatena verticalmente più DataFrame (rbind)."""
        return pd.concat(dfs, ignore_index=ignore_index)

    @staticmethod
    def pivot(df: pd.DataFrame, index: str, columns: str,
              values: str, agg_func: Any = "mean") -> pd.DataFrame:
        """Crea una tabella pivot."""
        return df.pivot_table(index=index, columns=columns,
                              values=values, aggfunc=agg_func)

    @staticmethod
    def unpivot(df: pd.DataFrame, id_vars: List[str],
                var_name: str = "variabile",
                value_name: str = "valore") -> pd.DataFrame:
        """Trasforma colonne in righe (melt / wide → long)."""
        return pd.melt(df, id_vars=id_vars,
                       var_name=var_name, value_name=value_name)

    # ── AGGREGAZIONE ──────────────────────────────────────────────────────────

    @staticmethod
    def aggregate(df: pd.DataFrame, group_by: List[str],
                  agg_column: str, agg_func: str) -> pd.DataFrame:
        """Aggregazione singola colonna."""
        funcs = {"sum","mean","count","min","max","median","std","var",
                 "first","last","nunique","size"}
        if agg_func not in funcs:
            raise ValueError(f"Funzione non supportata: {agg_func!r}. Usa: {funcs}")
        return (df.groupby(group_by, dropna=False)[agg_column]
                  .agg(agg_func).reset_index())

    @staticmethod
    def aggregate_multi(df: pd.DataFrame, group_by: List[str],
                        agg_dict: Dict[str, List[str]]) -> pd.DataFrame:
        """
        Aggregazione multi-colonna multi-funzione.
        agg_dict = {'colonna': ['sum', 'mean'], 'altra': ['count']}
        """
        result = df.groupby(group_by, dropna=False).agg(agg_dict)
        result.columns = ["_".join(c) for c in result.columns]
        return result.reset_index()

    @staticmethod
    def sample_rows(df: pd.DataFrame, n: Optional[int] = None,
                    frac: Optional[float] = None,
                    seed: int = 42) -> pd.DataFrame:
        """Campiona n righe o una frazione del DataFrame."""
        if frac is not None:
            return df.sample(frac=frac, random_state=seed).reset_index(drop=True)
        return df.sample(n=n or 100, random_state=seed).reset_index(drop=True)

    # ── OUTLIER ───────────────────────────────────────────────────────────────

    @staticmethod
    def remove_outliers_iqr(df: pd.DataFrame, columns: List[str],
                            factor: float = 1.5) -> pd.DataFrame:
        """Rimuove righe con outlier IQR su una o più colonne numeriche."""
        mask = pd.Series([True] * len(df), index=df.index)
        for col in columns:
            num = pd.to_numeric(df[col], errors="coerce")
            q1, q3 = num.quantile(0.25), num.quantile(0.75)
            iqr = q3 - q1
            mask &= (num >= q1 - factor * iqr) & (num <= q3 + factor * iqr)
        return df[mask].reset_index(drop=True)

    @staticmethod
    def cap_outliers_iqr(df: pd.DataFrame, columns: List[str],
                         factor: float = 1.5) -> pd.DataFrame:
        """Fa il 'winsorizing': limita (clip) i valori estremi ai fence IQR."""
        df = df.copy()
        for col in columns:
            num = pd.to_numeric(df[col], errors="coerce")
            q1, q3 = num.quantile(0.25), num.quantile(0.75)
            iqr = q3 - q1
            df[col] = num.clip(lower=q1 - factor * iqr,
                               upper=q3 + factor * iqr)
        return df

    # ── UTILITÀ ───────────────────────────────────────────────────────────────

    @staticmethod
    def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
        return DataImporter.normalize_columns(df)

    @staticmethod
    def add_row_index(df: pd.DataFrame, col_name: str = "row_id",
                      start: int = 1) -> pd.DataFrame:
        """Aggiunge una colonna indice numerico progressivo."""
        df = df.copy()
        df.insert(0, col_name, range(start, start + len(df)))
        return df

    @staticmethod
    def export(df: pd.DataFrame, path: Path) -> None:
        """Esporta il DataFrame nel formato dedotto dall'estensione del file."""
        suffix = path.suffix.lower()
        if suffix == ".csv":
            df.to_csv(path, index=False, encoding="utf-8-sig")
        elif suffix == ".tsv":
            df.to_csv(path, index=False, sep="\t", encoding="utf-8-sig")
        elif suffix in {".xlsx", ".xls"}:
            df.to_excel(path, index=False)
        elif suffix == ".json":
            df.to_json(path, orient="records", force_ascii=False, indent=2)
        elif suffix == ".parquet":
            df.to_parquet(path, index=False)
        elif suffix == ".feather":
            df.to_feather(path)
        elif suffix == ".html":
            df.to_html(path, index=False)
        elif suffix in {".pkl", ".pickle"}:
            df.to_pickle(path)
        else:
            df.to_csv(path, index=False)


# ══════════════════════════════════════════════════════════════════════════════
# SQL SYNTAX HIGHLIGHTER
# ══════════════════════════════════════════════════════════════════════════════

class SQLHighlighter(QSyntaxHighlighter):

    KEYWORDS = [
        "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES", "UPDATE",
        "SET", "DELETE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER",
        "ON", "AS", "AND", "OR", "NOT", "NULL", "IS", "IN", "LIKE", "BETWEEN",
        "GROUP", "BY", "ORDER", "HAVING", "DISTINCT", "UNION", "ALL", "EXCEPT",
        "INTERSECT", "CREATE", "TABLE", "PRIMARY", "KEY", "FOREIGN", "ALTER",
        "DROP", "VIEW", "INDEX", "CASE", "WHEN", "THEN", "ELSE", "END",
        "LIMIT", "OFFSET", "TOP", "WITH", "RECURSIVE", "EXISTS",
        "TRUNCATE", "COMMIT", "ROLLBACK", "BEGIN", "TRANSACTION",
    ]

    def __init__(self, document) -> None:
        super().__init__(document)

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#569CD6"))
        kw_fmt.setFontWeight(QFont.Weight.Bold)

        fn_fmt = QTextCharFormat()
        fn_fmt.setForeground(QColor("#DCDCAA"))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#CE9178"))

        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#6A9955"))
        cmt_fmt.setFontItalic(True)

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#B5CEA8"))

        self._rules = [
            *(
                (
                    QRegularExpression(
                        r"\b" + kw + r"\b",
                        QRegularExpression.PatternOption.CaseInsensitiveOption,
                    ),
                    kw_fmt,
                )
                for kw in self.KEYWORDS
            ),
            (QRegularExpression(r"'[^']*'"), str_fmt),
            (QRegularExpression(r'"[^"]*"'), str_fmt),
            (QRegularExpression(r"--[^\n]*"), cmt_fmt),
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), num_fmt),
            (QRegularExpression(r"\b[A-Za-z_]\w*\s*(?=\()"), fn_fmt),
        ]

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ══════════════════════════════════════════════════════════════════════════════
# DIALOGO FILTRO
# ══════════════════════════════════════════════════════════════════════════════

class FilterDialog(QDialog):
    """Configura un filtro su una colonna del DataFrame."""

    OPERATORS = ETLEngine.FILTER_OPERATORS

    def __init__(self, columns: List[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aggiungi filtro")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.col_combo = QComboBox()
        self.col_combo.addItems(columns)

        self.op_combo = QComboBox()
        self.op_combo.addItems(self.OPERATORS)
        self.op_combo.currentTextChanged.connect(self._on_operator_changed)

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("valore…")

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color:#777; font-size:11px;")
        self.hint_label.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addRow("Colonna:", self.col_combo)
        layout.addRow("Operatore:", self.op_combo)
        layout.addRow("Valore:", self.value_edit)
        layout.addRow("", self.hint_label)
        layout.addRow(buttons)
        self._on_operator_changed(self.op_combo.currentText())

    _HINTS = {
        "in lista":       "Valori separati da virgola: A,B,C",
        "non in lista":   "Valori separati da virgola: A,B,C",
        "tra (numerico)": "Due valori separati da virgola: min,max",
        "regex":          "Espressione regolare Python (case-insensitive)",
        "outlier IQR":    "Nessun valore richiesto",
        "sostituisci":    "Formato: vecchio→nuovo",
    }

    def _on_operator_changed(self, op: str) -> None:
        no_value = {"è vuoto", "non è vuoto", "outlier IQR"}
        self.value_edit.setEnabled(op not in no_value)
        self.hint_label.setText(self._HINTS.get(op, ""))

    def result_values(self):
        return (
            self.col_combo.currentText(),
            self.op_combo.currentText(),
            self.value_edit.text(),
        )


# ══════════════════════════════════════════════════════════════════════════════
# FINESTRA PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HealthReport Studio")
        self.resize(1400, 900)

        # ── Stato condiviso ───────────────────────────────────────────────────
        self.raw_df: pd.DataFrame = pd.DataFrame()      # dati originali
        self.working_df: pd.DataFrame = pd.DataFrame()  # dati dopo ETL
        self.query_sources: List[Dict[str, Any]] = []
        self.db_connections: List[Dict[str, Any]] = []
        self.etl_steps: List[str] = []
        self.sql_theme_dark: bool = True
        self.sql_result_df: pd.DataFrame = pd.DataFrame()
        self._report_figures: Dict[str, Figure] = {}

        # ── Layout radice ─────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.tabs.addTab(self._build_data_query_tab(), "📂  Data Query")
        self.tabs.addTab(self._build_report_tab(),        "📊  Report")
        self.tabs.addTab(self._build_ml_placeholder(),    "🤖  Analisi ML")

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._set_status("Pronto.")
        self._build_menu_bar()

    def _build_menu_bar(self) -> None:
        """Barra menu principale con Strumenti → Gestione dipendenze opzionali."""
        from PySide6.QtGui import QAction
        menubar = self.menuBar()

        # Menu Strumenti
        tools_menu = menubar.addMenu("Strumenti")

        act_dep = QAction("📦  Gestione dipendenze opzionali...", self)
        act_dep.setToolTip("Installa, aggiorna o verifica le librerie opzionali (driver DB, export, ML)")
        act_dep.triggered.connect(lambda: open_optional_manager(self))
        tools_menu.addAction(act_dep)

        tools_menu.addSeparator()

        act_reload = QAction("🔄  Ricarica dipendenze core", self)
        act_reload.setToolTip("Verifica e reinstalla le librerie core da LIBRARIES.md")
        act_reload.triggered.connect(self._reload_core_deps)
        tools_menu.addAction(act_reload)

        act_status = QAction("ℹ  Stato dipendenze", self)
        act_status.triggered.connect(self._show_dep_status)
        tools_menu.addAction(act_status)

        # Menu Dati
        data_menu = menubar.addMenu("Dati")
        act_etl_reset = QAction("↩  Ripristina dataset originale", self)
        act_etl_reset.triggered.connect(self._etl_reset)
        data_menu.addAction(act_etl_reset)

        act_export = QAction("📤  Esporta dati correnti...", self)
        act_export.triggered.connect(self._etl_export)
        data_menu.addAction(act_export)

    def _reload_core_deps(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        try:
            from dependency_manager import ensure_dependencies_before_startup
            ensure_dependencies_before_startup("LIBRARIES.md", auto_update=True)
            QMessageBox.information(self, "Dipendenze core",
                "Verifica completata. Tutte le librerie core sono installate.")
        except Exception as exc:
            QMessageBox.critical(self, "Errore dipendenze", str(exc))

    def _show_dep_status(self) -> None:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
        from PySide6.QtGui import QFont
        from dependency_manager import (
            read_libraries_from_markdown,
            read_optional_libraries_from_markdown,
            is_installed, get_python_executable,
            _load_optional_registry,
        )
        dlg = QDialog(self); dlg.setWindowTitle("Stato dipendenze"); dlg.resize(600, 480)
        layout = QVBoxLayout(dlg)
        txt = QTextEdit(); txt.setReadOnly(True); txt.setFont(QFont("Courier New", 10))
        btn = QPushButton("Chiudi"); btn.clicked.connect(dlg.accept)
        layout.addWidget(txt); layout.addWidget(btn)

        py = get_python_executable()
        lines = [
            "STATO DIPENDENZE — HealthReport Studio",
            "=" * 60,
            f"Interprete Python : {py}",
            "",
            "── CORE LIBRARIES ──",
        ]
        try:
            core = read_libraries_from_markdown("LIBRARIES.md")
            for lib in core:
                ok = is_installed(lib, py)
                lines.append(f"  {'✔' if ok else '✖'}  {lib}")
        except Exception as exc:
            lines.append(f"  Errore lettura LIBRARIES.md: {exc}")

        lines += ["", "── LIBRERIE OPZIONALI ──"]
        reg = _load_optional_registry()
        try:
            opt = read_optional_libraries_from_markdown("LIBRARIES_OPTIONAL.md")
            for pip_name, desc in opt.items():
                ok = is_installed(pip_name, py)
                ver = reg.get(pip_name, {}).get("version", "") if ok else ""
                status = f"✔ {ver}" if ok else "✖ non installata"
                lines.append(f"  [{status:<18}] {pip_name:<35} {desc[:35]}")
        except Exception as exc:
            lines.append(f"  Errore lettura LIBRARIES_OPTIONAL.md: {exc}")

        txt.setPlainText("\n".join(lines))
        dlg.exec()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 – DATA QUERY
    # ══════════════════════════════════════════════════════════════════════════

    def _build_data_query_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.query_subtabs = QTabWidget()
        self.query_subtabs.addTab(self._build_sources_tab(),     "A · Sorgenti Dati")
        self.query_subtabs.addTab(self._build_db_tab(),          "B · Connessioni DB")
        self.query_subtabs.addTab(self._build_cloud_db_tab(),    "C · Cloud Database")
        self.query_subtabs.addTab(self._build_sql_tab(),         "D · Editor SQL")
        self.query_subtabs.addTab(self._build_etl_tab(),         "E · ETL / Trasformazioni")

        layout.addWidget(self.query_subtabs)
        return widget

    # ── A · Sorgenti Dati ─────────────────────────────────────────────────────

    def _build_sources_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        bar = QHBoxLayout()
        for label, slot in [
            ("+ File",     self._src_add_file),
            ("+ Cartella", self._src_add_folder),
            ("+ URL",      self._src_add_url),
            ("+ SQLite",   self._src_add_sqlite),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            bar.addWidget(btn)

        bar.addStretch()
        btn_prev  = QPushButton("👁  Anteprima")
        btn_load  = QPushButton("✔  Carica in ETL")
        btn_rm    = QPushButton("✖  Rimuovi")
        btn_clear = QPushButton("⊗  Svuota tutto")
        btn_prev.clicked.connect(self._src_preview)
        btn_load.clicked.connect(self._src_load_to_etl)
        btn_rm.clicked.connect(self._src_remove)
        btn_clear.clicked.connect(self._src_clear_all)
        for b in [btn_prev, btn_load, btn_rm, btn_clear]:
            bar.addWidget(b)

        self.sources_list  = QListWidget()
        self.sources_list.setMaximumHeight(120)
        self.sources_info  = QLabel("Sorgenti: 0  |  Nessun dato caricato")

        self.preview_model = PandasTableModel()
        self.preview_table = _make_table_view(self.preview_model)

        layout.addLayout(bar)
        layout.addWidget(QLabel("Sorgenti dati:"))
        layout.addWidget(self.sources_list)
        layout.addWidget(self.sources_info)
        layout.addWidget(QLabel("Anteprima (prime 200 righe):"))
        layout.addWidget(self.preview_table, stretch=1)
        return widget

    # ·· slot sorgenti ··

    def _src_add_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Seleziona file", "",
            "Tutti i formati supportati "
            "(*.csv *.tsv *.xlsx *.xls *.json *.xml *.parquet *.feather *.orc *.db *.sqlite);;"
            "CSV/TSV (*.csv *.tsv);;Excel (*.xlsx *.xls);;JSON (*.json);;"
            "XML (*.xml);;Parquet (*.parquet);;Feather (*.feather);;"
            "ORC (*.orc);;SQLite (*.db *.sqlite)",
        )
        for f in files:
            self.query_sources.append({"kind": "file", "value": f})
        self._src_refresh()

    def _src_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleziona cartella")
        if folder:
            self.query_sources.append({"kind": "folder", "value": folder})
        self._src_refresh()

    def _src_add_url(self) -> None:
        url, ok = QInputDialog.getText(
            self, "URL", "URL del file (CSV / JSON / Excel / Parquet / XML):"
        )
        if ok and url.strip():
            self.query_sources.append({"kind": "url", "value": url.strip()})
        self._src_refresh()

    def _src_add_sqlite(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona SQLite", "", "SQLite (*.db *.sqlite)"
        )
        if path:
            self.query_sources.append({"kind": "sqlite", "value": path})
        self._src_refresh()

    def _src_remove(self) -> None:
        row = self.sources_list.currentRow()
        if row >= 0:
            self.query_sources.pop(row)
        self._src_refresh()

    def _src_clear_all(self) -> None:
        self.query_sources.clear()
        self.preview_model.update_dataframe(pd.DataFrame())
        self._src_refresh()

    def _src_refresh(self) -> None:
        self.sources_list.clear()
        for s in self.query_sources:
            self.sources_list.addItem(f"[{s['kind'].upper()}]  {s['value']}")
        self.sources_info.setText(
            f"Sorgenti: {len(self.query_sources)}  |  "
            f"Righe nel dataset corrente: {len(self.raw_df)}"
        )

    def _load_source(self, source: Dict[str, Any]) -> pd.DataFrame:
        kind, value = source["kind"], source["value"]
        if kind == "file":
            return DataImporter.load_file(Path(value))
        if kind == "folder":
            return DataImporter.load_folder(Path(value))
        if kind == "url":
            return DataImporter.load_url(value)
        if kind == "sqlite":
            return DataImporter._load_sqlite_first_table(Path(value))
        raise ValueError(f"Tipo sorgente sconosciuto: {kind}")

    def _src_preview(self) -> None:
        row = self.sources_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Anteprima", "Seleziona prima una sorgente.")
            return
        try:
            df = self._load_source(self.query_sources[row])
            self.preview_model.update_dataframe(df.head(200))
            self.preview_table.resizeColumnsToContents()
            self._set_status(
                f"Anteprima: {len(df)} righe × {len(df.columns)} colonne"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Errore", str(exc))

    def _src_load_to_etl(self) -> None:
        row = self.sources_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Carica", "Seleziona prima una sorgente.")
            return
        try:
            df = self._load_source(self.query_sources[row])
            self._set_raw_df(df, label=self.query_sources[row]["value"])
            self.query_subtabs.setCurrentIndex(4)   # vai a ETL
        except Exception as exc:
            QMessageBox.critical(self, "Errore di caricamento", str(exc))

    def _set_raw_df(self, df: pd.DataFrame, label: str = "") -> None:
        self.raw_df    = df.copy()
        self.working_df = df.copy()
        self.etl_steps.clear()
        self._src_refresh()
        self._etl_refresh()
        name = Path(label).name if label else "—"
        self._set_status(
            f"Dataset caricato — {len(df)} righe × {len(df.columns)} colonne"
            + (f"  da: {name}" if name else "")
        )
        QMessageBox.information(
            self, "Caricamento completato",
            f"Dataset caricato con successo.\n\n"
            f"  Righe   : {len(df):,}\n"
            f"  Colonne : {len(df.columns)}\n"
            f"  Fonte   : {name}",
        )


    # ======================================================================
    # B · CONNESSIONI DB LOCALI / ON-PREMISE (SQLAlchemy)
    # ======================================================================

    _active_connections: dict = {}

    _DB_DEFAULTS: dict = {
        "SQLite": {
            "port": "", "driver": "sqlite",
            "pkg": "sqlalchemy",
            "url": "sqlite:///{file}",
            "hint": "File locale. Non serve host/porta/utente.",
            "fields": ["file"],
        },
        "PostgreSQL": {
            "port": "5432", "driver": "postgresql+psycopg2",
            "pkg": "psycopg2-binary",
            "url": "postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
            "hint": "Driver: psycopg2  ->  pip install psycopg2-binary sqlalchemy",
            "fields": ["host","port","database","user","password"],
        },
        "MySQL / MariaDB": {
            "port": "3306", "driver": "mysql+pymysql",
            "pkg": "pymysql",
            "url": "mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
            "hint": "Driver: PyMySQL  ->  pip install pymysql sqlalchemy",
            "fields": ["host","port","database","user","password"],
        },
        "MSSQL / SQL Server": {
            "port": "1433", "driver": "mssql+pyodbc",
            "pkg": "pyodbc",
            "url": "mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server",
            "hint": "Richiede ODBC Driver 17+  ->  pip install pyodbc sqlalchemy",
            "fields": ["host","port","database","user","password"],
        },
        "Oracle": {
            "port": "1521", "driver": "oracle+oracledb",
            "pkg": "oracledb",
            "url": "oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={database}",
            "hint": "Driver: python-oracledb  ->  pip install oracledb sqlalchemy",
            "fields": ["host","port","database","user","password"],
        },
        "IBM DB2": {
            "port": "50000", "driver": "ibm_db_sa",
            "pkg": "ibm_db ibm_db_sa",
            "url": "db2+ibm_db://{user}:{password}@{host}:{port}/{database}",
            "hint": "pip install ibm_db ibm_db_sa sqlalchemy",
            "fields": ["host","port","database","user","password"],
        },
        "DuckDB (file)": {
            "port": "", "driver": "duckdb",
            "pkg": "duckdb duckdb-engine",
            "url": "duckdb:///{file}",
            "hint": "pip install duckdb duckdb-engine  -- File locale .duckdb",
            "fields": ["file"],
        },
        "Access (ODBC)": {
            "port": "", "driver": "access+pyodbc",
            "pkg": "pyodbc",
            "url": "access+pyodbc:///{file}",
            "hint": "Richiede ACE OLEDB 64-bit (Windows). pip install pyodbc sqlalchemy",
            "fields": ["file"],
        },
        "Firebird": {
            "port": "3050", "driver": "firebird+fdb",
            "pkg": "fdb sqlalchemy",
            "url": "firebird+fdb://{user}:{password}@{host}:{port}/{database}",
            "hint": "pip install fdb sqlalchemy",
            "fields": ["host","port","database","user","password"],
        },
    }

    def _build_db_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        inner = QTabWidget()
        inner.addTab(self._build_db_new_conn_panel(), "Nuova connessione")
        inner.addTab(self._build_db_saved_panel(),    "Connessioni salvate")
        inner.addTab(self._build_db_schema_browser(), "Browser schema")
        layout.addWidget(inner)
        return widget

    def _build_db_new_conn_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        form_group = QGroupBox("Parametri connessione")
        fl = QFormLayout(form_group)
        self.db_type = QComboBox()
        self.db_type.addItems(list(self._DB_DEFAULTS.keys()))
        self.db_type.currentTextChanged.connect(self._db_on_type_changed)
        self.db_hint_lbl = QLabel()
        self.db_hint_lbl.setWordWrap(True)
        self.db_hint_lbl.setStyleSheet("color:#777;font-style:italic;font-size:11px;")
        self.db_name_edit = QLineEdit(); self.db_name_edit.setPlaceholderText("Nome connessione (alias)")
        self.db_host_edit = QLineEdit(); self.db_host_edit.setPlaceholderText("localhost")
        self.db_port_edit = QLineEdit(); self.db_port_edit.setPlaceholderText("porta")
        self.db_db_edit   = QLineEdit(); self.db_db_edit.setPlaceholderText("nome database")
        self.db_user_edit = QLineEdit(); self.db_user_edit.setPlaceholderText("utente")
        self.db_file_edit = QLineEdit(); self.db_file_edit.setPlaceholderText("percorso file...")
        btn_browse_file = QPushButton("..."); btn_browse_file.setMaximumWidth(30)
        btn_browse_file.clicked.connect(self._db_browse_file)
        file_row = QHBoxLayout(); file_row.addWidget(self.db_file_edit); file_row.addWidget(btn_browse_file)
        self.db_file_widget = QWidget(); self.db_file_widget.setLayout(file_row)
        self.db_pass_edit = QLineEdit()
        self.db_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_pass_edit.setPlaceholderText("password")
        btn_show_pw = QPushButton("mostra"); btn_show_pw.setMaximumWidth(55); btn_show_pw.setCheckable(True)
        btn_show_pw.clicked.connect(
            lambda chk: self.db_pass_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if chk else QLineEdit.EchoMode.Password))
        pw_row = QHBoxLayout(); pw_row.addWidget(self.db_pass_edit); pw_row.addWidget(btn_show_pw)
        self.db_pw_widget = QWidget(); self.db_pw_widget.setLayout(pw_row)
        self.db_extra_edit = QLineEdit()
        self.db_extra_edit.setPlaceholderText("parametri extra URL (es. charset=utf8&timeout=30)")
        self.db_ssl_check = QCheckBox("SSL/TLS")
        self.db_pool_spin = QSpinBox(); self.db_pool_spin.setRange(1,20); self.db_pool_spin.setValue(5)
        self.db_pool_spin.setPrefix("Pool: ")
        self.db_timeout_spin = QSpinBox(); self.db_timeout_spin.setRange(1,120); self.db_timeout_spin.setValue(30)
        self.db_timeout_spin.setPrefix("Timeout: "); self.db_timeout_spin.setSuffix("s")
        fl.addRow("Tipo DBMS:",       self.db_type)
        fl.addRow("",                 self.db_hint_lbl)
        fl.addRow("Alias/Nome:",      self.db_name_edit)
        fl.addRow("Host:",            self.db_host_edit)
        fl.addRow("Porta:",           self.db_port_edit)
        fl.addRow("Database:",        self.db_db_edit)
        fl.addRow("File:",            self.db_file_widget)
        fl.addRow("Utente:",          self.db_user_edit)
        fl.addRow("Password:",        self.db_pw_widget)
        fl.addRow("Extra URL:",       self.db_extra_edit)
        opts_row = QHBoxLayout()
        opts_row.addWidget(self.db_ssl_check); opts_row.addWidget(self.db_pool_spin)
        opts_row.addWidget(self.db_timeout_spin); opts_row.addStretch()
        fl.addRow("Opzioni:", _wrap(opts_row))
        btn_test    = QPushButton("Testa connessione")
        btn_connect = QPushButton("Connetti e salva")
        btn_sqlite  = QPushButton("Apri SQLite...")
        btn_url     = QPushButton("Da URL completa...")
        btn_test.clicked.connect(self._db_test_real)
        btn_connect.clicked.connect(self._db_connect_and_save)
        btn_sqlite.clicked.connect(self._db_quick_sqlite)
        btn_url.clicked.connect(self._db_from_url)
        act_row = QHBoxLayout()
        act_row.addWidget(btn_test); act_row.addWidget(btn_connect)
        act_row.addStretch(); act_row.addWidget(btn_sqlite); act_row.addWidget(btn_url)
        self.db_url_preview = QLabel("URL: --")
        self.db_url_preview.setStyleSheet("font-family:monospace;font-size:10px;color:#555;background:#f5f5f5;padding:4px;")
        self.db_url_preview.setWordWrap(True)
        for w in [self.db_host_edit, self.db_port_edit, self.db_db_edit,
                  self.db_user_edit, self.db_file_edit, self.db_extra_edit]:
            w.textChanged.connect(self._db_update_url_preview)
        self.db_type.currentTextChanged.connect(self._db_update_url_preview)
        layout.addWidget(form_group)
        layout.addLayout(act_row)
        layout.addWidget(QLabel("URL preview:"))
        layout.addWidget(self.db_url_preview)
        layout.addStretch()
        self._db_on_type_changed(self.db_type.currentText())
        return widget

    def _build_db_saved_panel(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(8,8,8,8)
        bar = QHBoxLayout()
        btn_use    = QPushButton("Usa in SQL Editor"); btn_use.clicked.connect(self._db_use_selected)
        btn_import = QPushButton("Importa tabella");   btn_import.clicked.connect(self._db_import_table)
        btn_remove = QPushButton("Rimuovi");           btn_remove.clicked.connect(self._db_remove_conn)
        btn_test2  = QPushButton("Test");              btn_test2.clicked.connect(self._db_test_selected)
        bar.addWidget(btn_use); bar.addWidget(btn_import); bar.addStretch()
        bar.addWidget(btn_test2); bar.addWidget(btn_remove)
        self.db_saved_list = QListWidget()
        self.db_saved_list.itemDoubleClicked.connect(self._db_use_selected)
        qr_group = QGroupBox("Query rapida sulla connessione selezionata")
        qr_layout = QVBoxLayout(qr_group)
        self.db_quick_sql = QTextEdit()
        self.db_quick_sql.setMaximumHeight(75)
        self.db_quick_sql.setFont(QFont("Courier New", 10))
        self.db_quick_sql.setPlaceholderText("SELECT * FROM tabella LIMIT 100")
        btn_run_quick = QPushButton("Esegui"); btn_run_quick.clicked.connect(self._db_run_quick_query)
        qr_layout.addWidget(self.db_quick_sql); qr_layout.addWidget(btn_run_quick)
        self.db_quick_result_lbl   = QLabel("--")
        self.db_quick_result_model = PandasTableModel()
        self.db_quick_result_table = _make_table_view(self.db_quick_result_model)
        self.db_quick_result_table.setMaximumHeight(180)
        layout.addLayout(bar)
        layout.addWidget(QLabel("Connessioni attive:")); layout.addWidget(self.db_saved_list)
        layout.addWidget(qr_group)
        layout.addWidget(self.db_quick_result_lbl); layout.addWidget(self.db_quick_result_table)
        return widget

    def _build_db_schema_browser(self) -> QWidget:
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(8,8,8,8)
        bar = QHBoxLayout()
        self.schema_conn_combo = QComboBox(); self.schema_conn_combo.setMinimumWidth(200)
        btn_browse       = QPushButton("Esplora schema")
        btn_preview_tbl  = QPushButton("Anteprima tabella")
        btn_load_tbl     = QPushButton("Carica tabella")
        btn_browse.clicked.connect(self._db_browse_schema)
        btn_preview_tbl.clicked.connect(self._db_preview_table)
        btn_load_tbl.clicked.connect(self._db_load_selected_table)
        bar.addWidget(QLabel("Connessione:")); bar.addWidget(self.schema_conn_combo)
        bar.addWidget(btn_browse); bar.addStretch()
        bar.addWidget(btn_preview_tbl); bar.addWidget(btn_load_tbl)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.schema_tree = QTreeWidget()
        self.schema_tree.setHeaderLabels(["Oggetto", "Tipo"])
        self.schema_tree.setMinimumWidth(260)
        self.schema_detail = QTextEdit()
        self.schema_detail.setReadOnly(True); self.schema_detail.setFont(QFont("Courier New", 10))
        self.schema_detail.setPlaceholderText("Seleziona una tabella per i dettagli...")
        splitter.addWidget(self.schema_tree); splitter.addWidget(self.schema_detail)
        splitter.setSizes([280, 400])
        layout.addLayout(bar); layout.addWidget(splitter, stretch=1)
        return widget

    # -- DB logic (SQLAlchemy) -----------------------------------------------

    def _db_build_url(self) -> str:
        t    = self.db_type.currentText()
        cfg  = self._DB_DEFAULTS.get(t, {})
        host = self.db_host_edit.text().strip() or "localhost"
        port = self.db_port_edit.text().strip()
        db   = self.db_db_edit.text().strip()
        user = self.db_user_edit.text().strip()
        pwd  = self.db_pass_edit.text()
        file_= self.db_file_edit.text().strip()
        extra= self.db_extra_edit.text().strip()
        import urllib.parse
        pwd_enc = urllib.parse.quote_plus(pwd) if pwd else ""
        url = cfg.get("url","").format(
            host=host, port=port, database=db,
            user=user, password=pwd_enc, file=file_,
        )
        if extra:
            sep = "&" if "?" in url else "?"
            url = url + sep + extra
        return url

    def _db_update_url_preview(self, *_) -> None:
        try:
            import re
            url = self._db_build_url()
            url_d = re.sub(r":[^:@]+@", ":***@", url)
            self.db_url_preview.setText("URL: " + url_d)
        except Exception:
            self.db_url_preview.setText("URL: --")

    def _db_on_type_changed(self, db_type: str) -> None:
        cfg = self._DB_DEFAULTS.get(db_type, {})
        fields = cfg.get("fields", [])
        self.db_hint_lbl.setText(cfg.get("hint",""))
        self.db_port_edit.setPlaceholderText(cfg.get("port",""))
        self.db_port_edit.setEnabled("port" in fields)
        self.db_host_edit.setEnabled("host" in fields)
        self.db_db_edit.setEnabled("database" in fields)
        self.db_user_edit.setEnabled("user" in fields)
        self.db_pw_widget.setEnabled("password" in fields)
        self.db_file_widget.setEnabled("file" in fields)
        self._db_update_url_preview()

    def _db_browse_file(self) -> None:
        t = self.db_type.currentText()
        if "DuckDB" in t:
            path, _ = QFileDialog.getOpenFileName(self, "Apri DuckDB", "", "DuckDB (*.duckdb *.db)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Apri file DB", "",
                "Database (*.db *.sqlite *.accdb *.mdb *.duckdb)")
        if path:
            self.db_file_edit.setText(path)

    def _db_test_real(self) -> None:
        # Assicura SQLAlchemy installato
        if not require_optional("sqlalchemy", reason="connessioni database SQLAlchemy"):
            return
        # Assicura il driver specifico
        t = self.db_type.currentText()
        provider_map = {
            "PostgreSQL": "PostgreSQL", "MySQL / MariaDB": "MySQL",
            "MSSQL / SQL Server": "MSSQL", "Oracle": "Oracle",
            "DuckDB (file)": "DuckDB", "IBM DB2": "IBM DB2",
            "Access (ODBC)": "MSSQL", "Firebird": "Firebird",
        }
        provider = provider_map.get(t)
        if provider and not require_provider(provider):
            return
        try:
            import sqlalchemy as sa, re
            url = self._db_build_url()
            kw: Dict[str, Any] = {}
            if t not in {"SQLite","DuckDB (file)","Access (ODBC)"}:
                kw["connect_args"] = {"connect_timeout": self.db_timeout_spin.value()}
            engine = sa.create_engine(url, pool_size=1, max_overflow=0, **kw)
            with engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            engine.dispose()
            url_d = re.sub(r":[^:@]+@", ":***@", url)
            QMessageBox.information(self, "Test superato",
                "Connessione riuscita!\n\nURL: " + url_d)
        except Exception as exc:
            QMessageBox.critical(self, "Connessione fallita",
                "Errore: " + str(exc) + "\n\nVerifica host, credenziali e driver installato.")

    def _db_connect_and_save(self) -> None:
        alias = self.db_name_edit.text().strip()
        if not alias:
            QMessageBox.warning(self, "Alias mancante", "Inserisci un nome per la connessione."); return
        if alias in self._active_connections:
            r = QMessageBox.question(self, "Sostituire?",
                "Connessione '" + alias + "' gia' esistente. Sostituire?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes: return
        # Installa SQLAlchemy e il driver se mancanti
        if not require_optional("sqlalchemy", reason="connessioni database"):
            return
        t = self.db_type.currentText()
        provider_map = {
            "PostgreSQL": "PostgreSQL", "MySQL / MariaDB": "MySQL",
            "MSSQL / SQL Server": "MSSQL", "Oracle": "Oracle",
            "DuckDB (file)": "DuckDB", "IBM DB2": "IBM DB2",
            "Access (ODBC)": "MSSQL", "Firebird": "Firebird",
        }
        provider = provider_map.get(t)
        if provider and not require_provider(provider):
            return
        try:
            import sqlalchemy as sa, re
            url  = self._db_build_url()
            t    = self.db_type.currentText()
            pool = self.db_pool_spin.value()
            tmo  = self.db_timeout_spin.value()
            kw: Dict[str, Any] = {}
            if t not in {"SQLite","DuckDB (file)","Access (ODBC)"}:
                kw["connect_args"] = {"connect_timeout": tmo}
            engine = sa.create_engine(url, pool_size=pool, max_overflow=5,
                                       pool_pre_ping=True, **kw)
            with engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            url_masked = re.sub(r":[^:@]+@", ":***@", url)
            self._active_connections[alias] = {
                "engine": engine, "type": t,
                "url": url, "url_masked": url_masked,
                "pool": pool, "timeout": tmo,
            }
            self._db_refresh_connection_lists(alias)
            QMessageBox.information(self, "Connesso",
                "Connessione '" + alias + "' stabilita.\n" + url_masked)
        except ImportError:
            QMessageBox.warning(self, "SQLAlchemy mancante",
                "pip install sqlalchemy + driver specifico")
        except Exception as exc:
            QMessageBox.critical(self, "Errore connessione", str(exc))

    def _db_from_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Connetti da URL",
            "Incolla la URL SQLAlchemy completa:")
        if not ok or not url.strip(): return
        alias, ok2 = QInputDialog.getText(self, "Alias", "Nome per questa connessione:")
        if not ok2 or not alias.strip(): return
        try:
            import sqlalchemy as sa, re
            engine = sa.create_engine(url.strip())
            with engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            url_masked = re.sub(r":[^:@]+@", ":***@", url.strip())
            self._active_connections[alias.strip()] = {
                "engine": engine, "type": "Custom URL",
                "url": url.strip(), "url_masked": url_masked,
                "pool": 5, "timeout": 30,
            }
            self._db_refresh_connection_lists(alias.strip())
            QMessageBox.information(self, "Connesso", alias + " -> " + url_masked)
        except Exception as exc:
            QMessageBox.critical(self, "Errore", str(exc))

    def _db_refresh_connection_lists(self, new_alias: str = "") -> None:
        self.db_saved_list.clear()
        for alias, info in self._active_connections.items():
            self.db_saved_list.addItem("[" + info["type"] + "]  " + alias + "  --  " + info["url_masked"])
        self.schema_conn_combo.clear()
        self.schema_conn_combo.addItems(list(self._active_connections.keys()))
        self.sql_conn_combo.clear()
        self.sql_conn_combo.addItem("Locale (dataset caricato)")
        for alias in self._active_connections:
            self.sql_conn_combo.addItem(alias)
        if hasattr(self, "cloud_conn_use_combo"):
            self.cloud_conn_use_combo.clear()
            self.cloud_conn_use_combo.addItems(list(self._active_connections.keys()))

    def _db_use_selected(self, _item=None) -> None:
        row = self.db_saved_list.currentRow()
        if row < 0: return
        alias = list(self._active_connections.keys())[row]
        idx = self.sql_conn_combo.findText(alias)
        if idx >= 0: self.sql_conn_combo.setCurrentIndex(idx)
        self.query_subtabs.setCurrentIndex(3)

    def _db_test_selected(self) -> None:
        row = self.db_saved_list.currentRow()
        if row < 0: return
        alias = list(self._active_connections.keys())[row]
        try:
            import sqlalchemy as sa
            with self._active_connections[alias]["engine"].connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            QMessageBox.information(self, "OK", "Connessione '" + alias + "' attiva.")
        except Exception as exc:
            QMessageBox.critical(self, "Errore", str(exc))

    def _db_remove_conn(self) -> None:
        row = self.db_saved_list.currentRow()
        if row < 0: return
        alias = list(self._active_connections.keys())[row]
        if QMessageBox.question(self, "Rimuovi", "Chiudere connessione '" + alias + "'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes: return
        try: self._active_connections[alias]["engine"].dispose()
        except Exception: pass
        del self._active_connections[alias]
        self._db_refresh_connection_lists()

    def _db_run_quick_query(self) -> None:
        row = self.db_saved_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selezione", "Seleziona prima una connessione."); return
        alias = list(self._active_connections.keys())[row]
        sql   = self.db_quick_sql.toPlainText().strip()
        if not sql: return
        self._db_run_on(alias, sql)

    def _db_run_on(self, alias: str, sql: str) -> None:
        info = self._active_connections.get(alias)
        if not info:
            QMessageBox.warning(self, "Connessione", "Connessione '" + alias + "' non trovata."); return
        sdk = info.get("sdk")
        try:
            if sdk == "pymongo":
                coll = info["engine"][info["db_name"]][info["collection"]]
                df = pd.DataFrame(list(coll.find({}, {"_id": 0})))
            elif sdk == "influxdb-client":
                query_api = info["engine"].query_api()
                df = query_api.query_data_frame(sql)
            elif sdk == "boto3":
                table = info["engine"].Table(info["table"])
                df = pd.DataFrame(table.scan()["Items"])
            elif sdk == "elasticsearch":
                resp = info["engine"].search(index=info["index"], size=1000)
                df = pd.DataFrame([h["_source"] for h in resp["hits"]["hits"]])
            else:
                df = pd.read_sql_query(sql, info["engine"])
            self.db_quick_result_model.update_dataframe(df)
            self.db_quick_result_table.resizeColumnsToContents()
            self.db_quick_result_lbl.setText(
                str(len(df)) + " righe x " + str(len(df.columns)) + " col  [" + alias + "]")
        except Exception as exc:
            QMessageBox.critical(self, "Errore query", str(exc))

    def _db_import_table(self) -> None:
        row = self.db_saved_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selezione", "Seleziona una connessione."); return
        alias = list(self._active_connections.keys())[row]
        table, ok = QInputDialog.getText(self, "Importa tabella",
            "Nome tabella (o SELECT query):")
        if not ok or not table.strip(): return
        sql = table.strip() if table.strip().upper().startswith("SELECT")               else "SELECT * FROM " + table.strip()
        try:
            df = pd.read_sql_query(sql, self._active_connections[alias]["engine"])
            self._set_raw_df(df, label=alias + "::" + table.strip())
            self.query_subtabs.setCurrentIndex(4)
        except Exception as exc:
            QMessageBox.critical(self, "Errore importazione", str(exc))

    def _db_browse_schema(self) -> None:
        from PySide6.QtWidgets import QTreeWidgetItem
        alias = self.schema_conn_combo.currentText()
        if not alias or alias not in self._active_connections:
            QMessageBox.warning(self, "Connessione", "Seleziona una connessione attiva."); return
        if not require_optional("sqlalchemy", reason="ispezione schema database"):
            return
        try:
            import sqlalchemy as sa
            engine = self._active_connections[alias]["engine"]
            insp   = sa.inspect(engine)
            self.schema_tree.clear()
            try:
                schemas = insp.get_schema_names()
            except Exception:
                schemas = [None]
            for schema in schemas:
                schema_item = QTreeWidgetItem(self.schema_tree,
                    [schema or "(default)", "schema"])
                schema_item.setExpanded(True)
                try:
                    tables = insp.get_table_names(schema=schema)
                except Exception:
                    tables = []
                for tbl in tables:
                    tbl_item = QTreeWidgetItem(schema_item, [tbl, "table"])
                    tbl_item.setData(0, Qt.ItemDataRole.UserRole,
                                     {"alias": alias, "schema": schema, "table": tbl})
                    try:
                        cols = insp.get_columns(tbl, schema=schema)
                        for col in cols:
                            QTreeWidgetItem(tbl_item,
                                [col["name"], str(col.get("type",""))])
                    except Exception:
                        pass
            self.schema_tree.itemClicked.connect(self._db_schema_item_clicked)
            self._set_status("Schema esplorato: " + alias)
        except Exception as exc:
            QMessageBox.critical(self, "Errore schema", str(exc))

    def _db_schema_item_clicked(self, item, _col) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or "table" not in data: return
        alias  = data["alias"]; schema = data["schema"]; table = data["table"]
        info   = self._active_connections.get(alias)
        if not info: return
        try:
            import sqlalchemy as sa
            insp = sa.inspect(info["engine"])
            cols = insp.get_columns(table, schema=schema)
            pk   = insp.get_pk_constraint(table, schema=schema)
            fks  = insp.get_foreign_keys(table, schema=schema)
            idxs = insp.get_indexes(table, schema=schema)
            lines = ["Tabella: " + (schema+"." if schema else "") + table, "-"*50, "COLONNE:"]
            for c in cols:
                nullable = "" if c.get("nullable", True) else " NOT NULL"
                default  = " DEFAULT " + str(c["default"]) if c.get("default") else ""
                lines.append("  " + c["name"].ljust(25) + str(c.get("type","")).ljust(20) + nullable + default)
            if pk.get("constrained_columns"):
                lines += ["", "PRIMARY KEY: " + str(pk["constrained_columns"])]
            if fks:
                lines.append("FOREIGN KEYS:")
                for fk in fks:
                    lines.append("  " + str(fk["constrained_columns"]) +
                                 " -> " + fk["referred_table"] + "." + str(fk["referred_columns"]))
            if idxs:
                lines.append("INDICI:")
                for ix in idxs:
                    lines.append("  " + str(ix["name"]) + ": " + str(ix["column_names"]) +
                                 (" UNIQUE" if ix.get("unique") else ""))
            self.schema_detail.setPlainText("\n".join(lines))
        except Exception as exc:
            self.schema_detail.setPlainText("Errore: " + str(exc))

    def _db_preview_table(self) -> None:
        item = self.schema_tree.currentItem()
        if not item: return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or "table" not in data: return
        alias = data["alias"]; table = data["table"]; schema = data["schema"]
        fqt = (schema + "." + table) if schema and schema != "main" else table
        self._db_run_on(alias, "SELECT * FROM " + fqt + " LIMIT 200")

    def _db_load_selected_table(self) -> None:
        item = self.schema_tree.currentItem()
        if not item: return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or "table" not in data: return
        alias = data["alias"]; table = data["table"]; schema = data["schema"]
        fqt = (schema + "." + table) if schema and schema != "main" else table
        try:
            df = pd.read_sql_table(table, self._active_connections[alias]["engine"], schema=schema)
            self._set_raw_df(df, label=alias + "::" + fqt)
            self.query_subtabs.setCurrentIndex(4)
        except Exception as exc:
            QMessageBox.critical(self, "Errore caricamento", str(exc))

    def _db_quick_sqlite(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Apri SQLite", "", "SQLite (*.db *.sqlite)")
        if not path: return
        alias = Path(path).stem
        try:
            import sqlalchemy as sa
            engine = sa.create_engine("sqlite:///" + path)
            with engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            self._active_connections[alias] = {
                "engine": engine, "type": "SQLite",
                "url": "sqlite:///" + path, "url_masked": "sqlite:///" + path,
                "pool": 1, "timeout": 10,
            }
            self._db_refresh_connection_lists(alias)
        except Exception:
            pass
        try:
            df = DataImporter._load_sqlite_first_table(Path(path))
            self._set_raw_df(df, label=path)
            self.query_subtabs.setCurrentIndex(4)
        except Exception as exc:
            QMessageBox.critical(self, "Errore", str(exc))

    # ======================================================================
    # C · CLOUD DATABASE
    # ======================================================================

    _CLOUD_PROVIDERS: dict = {
        "Amazon RDS (PostgreSQL)": {
            "group":"AWS","icon":"AWS",
            "pkg":"psycopg2-binary sqlalchemy",
            "url":"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
            "port":"5432","fields":["host","port","database","user","password"],
            "hint":"AWS RDS PostgreSQL. pip install psycopg2-binary sqlalchemy",
        },
        "Amazon RDS (MySQL)": {
            "group":"AWS","icon":"AWS",
            "pkg":"pymysql sqlalchemy",
            "url":"mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
            "port":"3306","fields":["host","port","database","user","password"],
            "hint":"AWS RDS MySQL/Aurora. pip install pymysql sqlalchemy",
        },
        "Amazon Redshift": {
            "group":"AWS","icon":"AWS",
            "pkg":"redshift-connector sqlalchemy-redshift",
            "url":"redshift+redshift_connector://{user}:{password}@{host}:{port}/{database}",
            "port":"5439","fields":["host","port","database","user","password"],
            "hint":"Redshift DWH. pip install redshift-connector sqlalchemy-redshift",
        },
        "Amazon Athena": {
            "group":"AWS","icon":"AWS",
            "pkg":"PyAthena sqlalchemy",
            "url":"awsathena+rest://{user}:{password}@athena.{extra1}.amazonaws.com:443/{database}?s3_staging_dir={extra2}",
            "port":"443","fields":["database","user","password","extra1","extra2"],
            "hint":"Athena (query su S3). extra1=regione, extra2=s3://bucket/staging. pip install PyAthena",
        },
        "Google BigQuery": {
            "group":"GCP","icon":"GCP",
            "pkg":"google-cloud-bigquery sqlalchemy-bigquery",
            "url":"bigquery://{extra1}/{database}",
            "port":"","fields":["database","extra1","credentials_file"],
            "hint":"BigQuery. extra1=project_id. pip install google-cloud-bigquery sqlalchemy-bigquery",
        },
        "Google Cloud SQL (PostgreSQL)": {
            "group":"GCP","icon":"GCP",
            "pkg":"psycopg2-binary cloud-sql-python-connector sqlalchemy",
            "url":"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
            "port":"5432","fields":["host","port","database","user","password"],
            "hint":"Cloud SQL PostgreSQL. pip install psycopg2-binary cloud-sql-python-connector",
        },
        "Google Cloud Spanner": {
            "group":"GCP","icon":"GCP",
            "pkg":"sqlalchemy-spanner google-cloud-spanner",
            "url":"spanner+spanner:///projects/{extra1}/instances/{extra2}/databases/{database}",
            "port":"","fields":["database","extra1","extra2","credentials_file"],
            "hint":"Spanner. extra1=project, extra2=instance. pip install sqlalchemy-spanner google-cloud-spanner",
        },
        "Azure SQL Database": {
            "group":"Azure","icon":"Azure",
            "pkg":"pyodbc sqlalchemy",
            "url":"mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=yes",
            "port":"1433","fields":["host","port","database","user","password"],
            "hint":"Azure SQL. Richiede ODBC Driver 17+. pip install pyodbc sqlalchemy",
        },
        "Azure Synapse Analytics": {
            "group":"Azure","icon":"Azure",
            "pkg":"pyodbc sqlalchemy",
            "url":"mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server",
            "port":"1433","fields":["host","port","database","user","password"],
            "hint":"Synapse (ex SQL DW). pip install pyodbc sqlalchemy",
        },
        "Azure PostgreSQL Flexible": {
            "group":"Azure","icon":"Azure",
            "pkg":"psycopg2-binary sqlalchemy",
            "url":"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}?sslmode=require",
            "port":"5432","fields":["host","port","database","user","password"],
            "hint":"Azure Database for PostgreSQL Flexible. pip install psycopg2-binary sqlalchemy",
        },
        "Snowflake": {
            "group":"Snowflake","icon":"Snowflake",
            "pkg":"snowflake-sqlalchemy snowflake-connector-python",
            "url":"snowflake://{user}:{password}@{extra1}/{database}/{extra2}",
            "port":"","fields":["database","user","password","extra1","extra2"],
            "hint":"Snowflake DWH. extra1=account, extra2=schema/warehouse. pip install snowflake-sqlalchemy",
        },
        "Databricks SQL": {
            "group":"Databricks","icon":"Databricks",
            "pkg":"databricks-sql-connector sqlalchemy-databricks",
            "url":"databricks+connector://token:{password}@{host}:{port}/{database}?http_path={extra1}",
            "port":"443","fields":["host","port","database","password","extra1"],
            "hint":"Databricks SQL Warehouse. extra1=http_path. pip install databricks-sql-connector",
        },
        "MongoDB Atlas": {
            "group":"MongoDB","icon":"MongoDB",
            "pkg":"pymongo",
            "url":"",
            "port":"","fields":["host","database","user","password","extra1"],
            "hint":"MongoDB Atlas (SDK). extra1=collection. pip install pymongo pandas",
        },
        "Supabase (PostgreSQL)": {
            "group":"BaaS","icon":"BaaS",
            "pkg":"psycopg2-binary sqlalchemy",
            "url":"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}?sslmode=require",
            "port":"5432","fields":["host","port","database","user","password"],
            "hint":"Supabase usa PostgreSQL standard. Host: db.<project>.supabase.co",
        },
        "Neon (serverless Postgres)": {
            "group":"BaaS","icon":"BaaS",
            "pkg":"psycopg2-binary sqlalchemy",
            "url":"postgresql+psycopg2://{user}:{password}@{host}/{database}?sslmode=require&options=endpoint%3D{extra1}",
            "port":"5432","fields":["host","database","user","password","extra1"],
            "hint":"Neon serverless. extra1=endpoint_id. pip install psycopg2-binary sqlalchemy",
        },
        "CockroachDB": {
            "group":"BaaS","icon":"BaaS",
            "pkg":"psycopg2-binary sqlalchemy-cockroachdb",
            "url":"cockroachdb+psycopg2://{user}:{password}@{host}:{port}/{database}?sslmode=require",
            "port":"26257","fields":["host","port","database","user","password"],
            "hint":"CockroachDB Cloud. pip install psycopg2-binary sqlalchemy-cockroachdb",
        },
        "PlanetScale (MySQL)": {
            "group":"BaaS","icon":"BaaS",
            "pkg":"pymysql sqlalchemy",
            "url":"mysql+pymysql://{user}:{password}@{host}/{database}",
            "port":"3306","fields":["host","database","user","password"],
            "hint":"PlanetScale (MySQL compatibile, SSL). pip install pymysql sqlalchemy",
        },
        "ClickHouse": {
            "group":"OLAP","icon":"OLAP",
            "pkg":"clickhouse-driver sqlalchemy-clickhouse",
            "url":"clickhouse+native://{user}:{password}@{host}:{port}/{database}",
            "port":"9000","fields":["host","port","database","user","password"],
            "hint":"ClickHouse analytics. pip install clickhouse-driver sqlalchemy-clickhouse",
        },
        "InfluxDB 2.x": {
            "group":"Time-Series","icon":"TS",
            "pkg":"influxdb-client",
            "url":"",
            "port":"8086","fields":["host","port","database","password","extra1"],
            "hint":"InfluxDB 2.x (SDK). password=token, extra1=org. pip install influxdb-client pandas",
        },
        "Elasticsearch": {
            "group":"Search","icon":"ES",
            "pkg":"elasticsearch eland",
            "url":"",
            "port":"9200","fields":["host","port","database","user","password"],
            "hint":"Elasticsearch via SDK. database=index. pip install elasticsearch eland pandas",
        },
    }

    def _build_cloud_db_tab(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(0,0,0,0)
        inner = QTabWidget()
        inner.addTab(self._build_cloud_connect_panel(), "Connetti")
        inner.addTab(self._build_cloud_guide_panel(),   "Guida & Driver")
        inner.addTab(self._build_cloud_template_panel(),"Template codice")
        layout.addWidget(inner)
        return widget

    def _build_cloud_connect_panel(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(8,8,8,8)
        prov_bar = QHBoxLayout()
        self.cloud_group_combo = QComboBox()
        groups = sorted(set(v["group"] for v in self._CLOUD_PROVIDERS.values()))
        self.cloud_group_combo.addItem("-- Tutti --"); self.cloud_group_combo.addItems(groups)
        self.cloud_group_combo.currentTextChanged.connect(self._cloud_filter_providers)
        self.cloud_provider_combo = QComboBox(); self.cloud_provider_combo.setMinimumWidth(280)
        self.cloud_provider_combo.addItems(list(self._CLOUD_PROVIDERS.keys()))
        self.cloud_provider_combo.currentTextChanged.connect(self._cloud_on_provider_changed)
        prov_bar.addWidget(QLabel("Gruppo:")); prov_bar.addWidget(self.cloud_group_combo)
        prov_bar.addWidget(QLabel("Provider:")); prov_bar.addWidget(self.cloud_provider_combo)
        prov_bar.addStretch()
        form_group = QGroupBox("Parametri connessione cloud")
        fl = QFormLayout(form_group)
        self.cloud_alias    = QLineEdit(); self.cloud_alias.setPlaceholderText("Nome connessione")
        self.cloud_host     = QLineEdit(); self.cloud_host.setPlaceholderText("host / endpoint")
        self.cloud_port     = QLineEdit()
        self.cloud_database = QLineEdit(); self.cloud_database.setPlaceholderText("database / dataset / bucket")
        self.cloud_user     = QLineEdit(); self.cloud_user.setPlaceholderText("utente / access key / token")
        self.cloud_pass     = QLineEdit(); self.cloud_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.cloud_pass.setPlaceholderText("password / secret / token")
        btn_show_cp = QPushButton("mostra"); btn_show_cp.setMaximumWidth(55); btn_show_cp.setCheckable(True)
        btn_show_cp.clicked.connect(
            lambda c: self.cloud_pass.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        cp_row = QHBoxLayout(); cp_row.addWidget(self.cloud_pass); cp_row.addWidget(btn_show_cp)
        self.cloud_extra1   = QLineEdit(); self.cloud_extra1.setPlaceholderText("campo extra 1")
        self.cloud_extra2   = QLineEdit(); self.cloud_extra2.setPlaceholderText("campo extra 2")
        self.cloud_cred_file= QLineEdit(); self.cloud_cred_file.setPlaceholderText("JSON credenziali")
        btn_browse_cred = QPushButton("..."); btn_browse_cred.setMaximumWidth(28)
        btn_browse_cred.clicked.connect(self._cloud_browse_cred)
        cred_row = QHBoxLayout(); cred_row.addWidget(self.cloud_cred_file); cred_row.addWidget(btn_browse_cred)
        self.cloud_ssl_check  = QCheckBox("SSL/TLS")
        self.cloud_timeout    = QSpinBox(); self.cloud_timeout.setRange(5,300); self.cloud_timeout.setValue(30)
        self.cloud_timeout.setSuffix("s"); self.cloud_timeout.setPrefix("Timeout: ")
        self.cloud_pool_size  = QSpinBox(); self.cloud_pool_size.setRange(1,20); self.cloud_pool_size.setValue(3)
        self.cloud_pool_size.setPrefix("Pool: ")
        self.cloud_hint_lbl = QLabel()
        self.cloud_hint_lbl.setWordWrap(True)
        self.cloud_hint_lbl.setStyleSheet("background:#FFF8E1;padding:6px;color:#555;font-size:11px;")
        for label, w in [
            ("Alias:",         self.cloud_alias),
            ("Host/Endpoint:", self.cloud_host),
            ("Porta:",         self.cloud_port),
            ("Database:",      self.cloud_database),
            ("Utente/Key:",    self.cloud_user),
            ("Password:",      _wrap(cp_row)),
            ("Extra 1:",       self.cloud_extra1),
            ("Extra 2:",       self.cloud_extra2),
            ("Credenziali JSON:", _wrap(cred_row)),
        ]:
            fl.addRow(label, w)
        opts_r = QHBoxLayout()
        opts_r.addWidget(self.cloud_ssl_check); opts_r.addWidget(self.cloud_timeout)
        opts_r.addWidget(self.cloud_pool_size); opts_r.addStretch()
        fl.addRow("Opzioni:", _wrap(opts_r))
        fl.addRow("Nota:", self.cloud_hint_lbl)
        self.cloud_url_preview = QLabel("URL: --")
        self.cloud_url_preview.setStyleSheet("font-family:monospace;font-size:10px;color:#555;background:#f5f5f5;padding:4px;")
        self.cloud_url_preview.setWordWrap(True)
        for w in [self.cloud_host, self.cloud_port, self.cloud_database,
                  self.cloud_user, self.cloud_extra1, self.cloud_extra2]:
            w.textChanged.connect(self._cloud_update_url_preview)
        btn_test_cloud    = QPushButton("Testa connessione")
        btn_connect_cloud = QPushButton("Connetti e salva")
        btn_install       = QPushButton("Mostra pip install")
        btn_test_cloud.clicked.connect(self._cloud_test)
        btn_connect_cloud.clicked.connect(self._cloud_connect)
        btn_install.clicked.connect(self._cloud_show_install)
        act_row = QHBoxLayout()
        act_row.addWidget(btn_test_cloud); act_row.addWidget(btn_connect_cloud)
        act_row.addStretch(); act_row.addWidget(btn_install)
        self.cloud_conn_use_combo = QComboBox(); self.cloud_conn_use_combo.setMinimumWidth(180)
        btn_cloud_use   = QPushButton("Usa in SQL Editor"); btn_cloud_use.clicked.connect(self._cloud_use)
        btn_cloud_query = QPushButton("Query rapida");      btn_cloud_query.clicked.connect(self._cloud_quick_query)
        use_bar = QHBoxLayout()
        use_bar.addWidget(QLabel("Connessione:")); use_bar.addWidget(self.cloud_conn_use_combo)
        use_bar.addWidget(btn_cloud_use); use_bar.addWidget(btn_cloud_query); use_bar.addStretch()
        layout.addLayout(prov_bar); layout.addWidget(form_group); layout.addLayout(act_row)
        layout.addWidget(QLabel("URL preview:")); layout.addWidget(self.cloud_url_preview)
        layout.addSpacing(6); layout.addLayout(use_bar)
        self._cloud_on_provider_changed(self.cloud_provider_combo.currentText())
        return widget

    def _build_cloud_guide_panel(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(widget)
        guide = QTextEdit(); guide.setReadOnly(True); guide.setFont(QFont("Courier New", 10))
        lines = ["GUIDA RAPIDA CONNESSIONI CLOUD DATABASE", "="*60, ""]
        groups: Dict[str, list] = {}
        for name, cfg in self._CLOUD_PROVIDERS.items():
            groups.setdefault(cfg["group"], []).append((name, cfg))
        for grp, items in groups.items():
            lines += ["-- " + grp + " " + "-"*50, ""]
            for name, cfg in items:
                lines += [
                    "  [" + cfg["icon"] + "] " + name,
                    "     pip install: " + cfg["pkg"],
                    "     " + cfg["hint"].splitlines()[0],
                    "",
                ]
        guide.setPlainText("\n".join(lines))
        layout.addWidget(guide)
        return widget

    def _build_cloud_template_panel(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(widget)
        self.cloud_tmpl_provider = QComboBox()
        self.cloud_tmpl_provider.addItems(list(self._CLOUD_PROVIDERS.keys()))
        self.cloud_tmpl_provider.currentTextChanged.connect(self._cloud_update_template)
        self.cloud_tmpl_text = QTextEdit(); self.cloud_tmpl_text.setReadOnly(True)
        self.cloud_tmpl_text.setFont(QFont("Courier New", 10))
        btn_copy = QPushButton("Copia")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(
            self.cloud_tmpl_text.toPlainText()))
        bar = QHBoxLayout(); bar.addWidget(QLabel("Provider:"))
        bar.addWidget(self.cloud_tmpl_provider); bar.addStretch(); bar.addWidget(btn_copy)
        layout.addLayout(bar); layout.addWidget(self.cloud_tmpl_text, stretch=1)
        self._cloud_update_template(self.cloud_tmpl_provider.currentText())
        return widget

    # -- Cloud logic ---------------------------------------------------------

    def _cloud_filter_providers(self, group: str) -> None:
        self.cloud_provider_combo.blockSignals(True)
        self.cloud_provider_combo.clear()
        for name, cfg in self._CLOUD_PROVIDERS.items():
            if group in ("-- Tutti --", cfg["group"]):
                self.cloud_provider_combo.addItem(name)
        self.cloud_provider_combo.blockSignals(False)
        if self.cloud_provider_combo.count() > 0:
            self._cloud_on_provider_changed(self.cloud_provider_combo.currentText())

    def _cloud_on_provider_changed(self, _=None) -> None:
        name = self.cloud_provider_combo.currentText()
        cfg  = self._CLOUD_PROVIDERS.get(name, {})
        fields = cfg.get("fields", [])
        self.cloud_host.setEnabled("host" in fields)
        self.cloud_port.setEnabled("port" in fields)
        self.cloud_port.setText(cfg.get("port",""))
        self.cloud_database.setEnabled("database" in fields)
        self.cloud_user.setEnabled(any(f in fields for f in ["user","aws_key","token"]))
        self.cloud_pass.setEnabled("password" in fields)
        self.cloud_cred_file.setEnabled("credentials_file" in fields)
        self.cloud_extra1.setEnabled("extra1" in fields)
        self.cloud_extra2.setEnabled("extra2" in fields)
        self.cloud_hint_lbl.setText(cfg.get("hint",""))
        self._cloud_update_url_preview()

    def _cloud_build_url(self) -> str:
        name = self.cloud_provider_combo.currentText()
        cfg  = self._CLOUD_PROVIDERS.get(name, {})
        if not cfg.get("url"): return "(SDK diretto - nessuna URL SQLAlchemy)"
        import urllib.parse
        pwd_enc = urllib.parse.quote_plus(self.cloud_pass.text()) if self.cloud_pass.text() else ""
        try:
            url = cfg["url"].format(
                host=self.cloud_host.text().strip() or "host",
                port=self.cloud_port.text().strip() or cfg.get("port",""),
                database=self.cloud_database.text().strip() or "database",
                user=self.cloud_user.text().strip() or "user",
                password=pwd_enc,
                extra1=self.cloud_extra1.text().strip() or "extra1",
                extra2=self.cloud_extra2.text().strip() or "extra2",
            )
        except KeyError:
            url = cfg.get("url","")
        return url

    def _cloud_update_url_preview(self, *_) -> None:
        import re
        url = self._cloud_build_url()
        url_d = re.sub(r":[^:@/]{2,}@", ":***@", url)
        self.cloud_url_preview.setText("URL: " + url_d)

    def _cloud_browse_cred(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Credenziali JSON", "", "JSON (*.json)")
        if path: self.cloud_cred_file.setText(path)

    def _cloud_test(self) -> None:
        name = self.cloud_provider_combo.currentText()
        cfg  = self._CLOUD_PROVIDERS.get(name, {})
        url  = self._cloud_build_url()
        if "(SDK" in url:
            QMessageBox.information(self, "SDK",
                name + " usa SDK Python diretto.\nUsa 'Connetti e salva'."); return
        # Installa sqlalchemy + driver del provider
        if not require_optional("sqlalchemy", reason="connessioni cloud database"):
            return
        pkg_list = [p.strip() for p in cfg.get("pkg","").split() if p.strip()]
        if pkg_list:
            if not require_optional_group(name, pkg_list,
                    reason="driver per " + name):
                return
        try:
            import sqlalchemy as sa, re
            engine = sa.create_engine(url, pool_pre_ping=True)
            with engine.connect() as conn: conn.execute(sa.text("SELECT 1"))
            engine.dispose()
            url_d = re.sub(r":[^:@/]{2,}@", ":***@", url)
            QMessageBox.information(self, "Test superato", "Connessione riuscita!\n" + url_d)
        except Exception as exc:
            QMessageBox.critical(self, "Test fallito", str(exc))

    def _cloud_connect(self) -> None:
        alias = self.cloud_alias.text().strip()
        name  = self.cloud_provider_combo.currentText()
        cfg   = self._CLOUD_PROVIDERS.get(name, {})
        if not alias:
            QMessageBox.warning(self, "Alias", "Inserisci un alias."); return
        url = self._cloud_build_url()
        if "(SDK" in url:
            self._cloud_connect_sdk(alias, name, cfg); return
        # Installa dipendenze necessarie
        if not require_optional("sqlalchemy", reason="connessioni database cloud"):
            return
        pkg_list = [p.strip() for p in cfg.get("pkg","").split() if p.strip()]
        if pkg_list and not require_optional_group(name, pkg_list,
                reason="driver per " + name):
            return
        try:
            import sqlalchemy as sa, re
            pool = self.cloud_pool_size.value()
            engine = sa.create_engine(url, pool_size=pool, max_overflow=5, pool_pre_ping=True)
            with engine.connect() as conn: conn.execute(sa.text("SELECT 1"))
            url_masked = re.sub(r":[^:@/]{2,}@", ":***@", url)
            self._active_connections[alias] = {
                "engine": engine, "type": name,
                "url": url, "url_masked": url_masked,
                "pool": pool, "timeout": self.cloud_timeout.value(), "cloud": True,
            }
            self._db_refresh_connection_lists(alias)
            QMessageBox.information(self, "Connesso",
                "Connessione cloud '" + alias + "' stabilita.\n" + url_masked)
        except Exception as exc:
            QMessageBox.critical(self, "Errore", str(exc))

    def _cloud_connect_sdk(self, alias: str, name: str, cfg: Dict) -> None:
        # Installa il pacchetto SDK necessario prima di procedere
        pkg_list = [p.strip() for p in cfg.get("pkg","").split() if p.strip()]
        if pkg_list and not require_optional_group(name, pkg_list,
                reason="SDK per " + name):
            return
        try:
            if "MongoDB" in name:
                pymongo = importlib.import_module("pymongo")
                uri = ("mongodb+srv://" + self.cloud_user.text() + ":" +
                       self.cloud_pass.text() + "@" + self.cloud_host.text() +
                       "/" + self.cloud_database.text())
                client = pymongo.MongoClient(uri,
                    serverSelectionTimeoutMS=self.cloud_timeout.value()*1000)
                client.server_info()
                self._active_connections[alias] = {
                    "engine": client, "type": name,
                    "url": "", "url_masked": "mongodb+srv://***@" + self.cloud_host.text(),
                    "pool": 1, "timeout": self.cloud_timeout.value(), "cloud": True,
                    "sdk": "pymongo", "db_name": self.cloud_database.text(),
                    "collection": self.cloud_extra1.text().strip(),
                }
            elif "InfluxDB" in name:
                from influxdb_client import InfluxDBClient  # type: ignore
                scheme = "https" if self.cloud_ssl_check.isChecked() else "http"
                client = InfluxDBClient(
                    url=scheme + "://" + self.cloud_host.text() + ":" + self.cloud_port.text(),
                    token=self.cloud_pass.text(), org=self.cloud_extra1.text())
                client.ping()
                self._active_connections[alias] = {
                    "engine": client, "type": name, "url": "", "url_masked": "",
                    "pool": 1, "timeout": self.cloud_timeout.value(), "cloud": True,
                    "sdk": "influxdb-client", "org": self.cloud_extra1.text(),
                    "bucket": self.cloud_database.text(),
                }
            elif "Elasticsearch" in name:
                from elasticsearch import Elasticsearch  # type: ignore
                scheme = "https" if self.cloud_ssl_check.isChecked() else "http"
                es = Elasticsearch(
                    scheme + "://" + self.cloud_host.text() + ":" + self.cloud_port.text(),
                    http_auth=(self.cloud_user.text(), self.cloud_pass.text()))
                es.info()
                self._active_connections[alias] = {
                    "engine": es, "type": name, "url": "", "url_masked": "",
                    "pool": 1, "timeout": self.cloud_timeout.value(), "cloud": True,
                    "sdk": "elasticsearch", "index": self.cloud_database.text(),
                }
            else:
                QMessageBox.warning(self, "SDK",
                    "SDK per '" + name + "' non ancora implementato."); return
            self._db_refresh_connection_lists(alias)
            QMessageBox.information(self, "Connesso SDK",
                "Connessione '" + alias + "' tramite SDK stabilita.")
        except ImportError as exc:
            QMessageBox.warning(self, "Libreria mancante",
                "pip install " + cfg.get("pkg","") + "\n\n" + str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Errore SDK", str(exc))

    def _cloud_show_install(self) -> None:
        name = self.cloud_provider_combo.currentText()
        cfg  = self._CLOUD_PROVIDERS.get(name, {})
        QMessageBox.information(self, "Installa driver - " + name,
            "pip install sqlalchemy " + cfg.get("pkg","") + "\n\n" +
            "URL template:\n" + cfg.get("url","(SDK diretto)"))

    def _cloud_use(self) -> None:
        alias = self.cloud_conn_use_combo.currentText()
        if not alias: return
        idx = self.sql_conn_combo.findText(alias)
        if idx >= 0: self.sql_conn_combo.setCurrentIndex(idx)
        self.query_subtabs.setCurrentIndex(3)

    def _cloud_quick_query(self) -> None:
        alias = self.cloud_conn_use_combo.currentText()
        if not alias: return
        sql, ok = QInputDialog.getText(self, "Query rapida",
            "SELECT query:", text="SELECT 1")
        if ok and sql.strip():
            self._db_run_on(alias, sql.strip())

    def _cloud_update_template(self, name: str) -> None:
        cfg = self._CLOUD_PROVIDERS.get(name, {})
        url_tmpl = cfg.get("url", "")
        lines = [
            "# Template connessione - " + name,
            "# Installa: pip install sqlalchemy " + cfg.get("pkg",""),
            "",
            "from sqlalchemy import create_engine, text",
            "import pandas as pd",
            "",
        ]
        if url_tmpl and "(SDK" not in url_tmpl:
            lines += [
                "engine = create_engine(",
                '    "' + url_tmpl + '",',
                "    pool_size=5, max_overflow=10, pool_pre_ping=True",
                ")",
                "",
                "# Leggi tabella",
                'df = pd.read_sql_table("nome_tabella", engine)',
                "",
                "# Query custom",
                'df = pd.read_sql_query("SELECT * FROM tabella LIMIT 100", engine)',
                "",
                "engine.dispose()",
            ]
        elif "MongoDB" in name:
            lines += [
                "import pymongo",
                'client = pymongo.MongoClient("mongodb+srv://user:pass@host/db")',
                'coll = client["database"]["collection"]',
                "df = pd.DataFrame(list(coll.find({}, {'_id': 0})))",
            ]
        elif "InfluxDB" in name:
            lines += [
                "from influxdb_client import InfluxDBClient",
                'client = InfluxDBClient(url="http://host:8086", token="TOKEN", org="ORG")',
                "api = client.query_api()",
                "df = api.query_data_frame(",
                "    'from(bucket:\"bucket\") |> range(start: -1h)'",
                ")",
            ]
        elif "BigQuery" in name:
            lines += [
                "from google.cloud import bigquery",
                'client = bigquery.Client(project="PROJECT")',
                'df = client.query("SELECT * FROM `dataset.table` LIMIT 100").to_dataframe()',
            ]
        elif "Elasticsearch" in name:
            lines += [
                "from elasticsearch import Elasticsearch",
                'es = Elasticsearch("http://host:9200",',
                '    http_auth=("user","pass"))',
                'resp = es.search(index="my_index", size=1000)',
                "df = pd.DataFrame([h['_source'] for h in resp['hits']['hits']])",
            ]
        self.cloud_tmpl_text.setPlainText("\n".join(lines))

    # -- Override SQL editor to use real connections --------------------------

    # ── D · Editor SQL ────────────────────────────────────────────


    def _build_sql_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        bar = QHBoxLayout()
        self.sql_conn_combo = QComboBox()
        self.sql_conn_combo.addItem("Locale (dataset caricato)")
        self.sql_conn_combo.setMinimumWidth(300)

        btn_run    = QPushButton("▶  Esegui")
        btn_run.clicked.connect(self._sql_run)
        btn_clear  = QPushButton("⊗  Cancella")
        btn_clear.clicked.connect(lambda: self.sql_editor.clear())
        btn_save   = QPushButton("💾  Salva .sql")
        btn_save.clicked.connect(self._sql_save)
        btn_open   = QPushButton("📂  Apri .sql")
        btn_open.clicked.connect(self._sql_open)
        btn_theme  = QPushButton("☾  Tema")
        btn_theme.setCheckable(True)
        btn_theme.setChecked(True)
        btn_theme.clicked.connect(self._sql_toggle_theme)
        btn_to_etl = QPushButton("➡  Invia a ETL")
        btn_to_etl.clicked.connect(self._sql_to_etl)

        bar.addWidget(QLabel("Connessione:"))
        bar.addWidget(self.sql_conn_combo)
        bar.addStretch()
        for b in [btn_theme, btn_open, btn_save, btn_clear, btn_run, btn_to_etl]:
            bar.addWidget(b)

        self.sql_editor = QTextEdit()
        self.sql_editor.setFont(QFont("Courier New", 12))
        self.sql_editor.setPlaceholderText(
            "-- La tabella locale si chiama «dati»\n"
            "SELECT *\nFROM dati\nWHERE colonna = 'valore'\nLIMIT 100;"
        )
        self.sql_highlighter = SQLHighlighter(self.sql_editor.document())

        self.sql_result_info  = QLabel("Nessuna query eseguita.")
        self.sql_result_model = PandasTableModel()
        self.sql_result_table = _make_table_view(self.sql_result_model)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.sql_editor)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 4, 0, 0)
        bl.addWidget(self.sql_result_info)
        bl.addWidget(self.sql_result_table)
        splitter.addWidget(bottom)
        splitter.setSizes([300, 280])

        layout.addLayout(bar)
        layout.addWidget(splitter, stretch=1)

        self._sql_apply_theme()
        return widget

    def _sql_run(self) -> None:
        query = self.sql_editor.toPlainText().strip()
        if not query:
            QMessageBox.warning(self, "Query vuota", "Scrivi una query SQL prima di eseguire.")
            return
        if self.sql_conn_combo.currentIndex() == 0:
            # Esecuzione locale su SQLite in memoria
            if self.working_df.empty:
                QMessageBox.warning(
                    self, "Dati mancanti",
                    "Nessun dataset caricato.\n"
                    "Vai alla tab «A · Sorgenti Dati» e carica un file.",
                )
                return
            try:
                conn = sqlite3.connect(":memory:")
                self.working_df.to_sql("dati", conn, if_exists="replace", index=False)
                result = pd.read_sql_query(query, conn)
                conn.close()
                self.sql_result_df = result
                self.sql_result_model.update_dataframe(result)
                self.sql_result_table.resizeColumnsToContents()
                self.sql_result_info.setText(
                    f"✔  {len(result):,} righe × {len(result.columns)} colonne  "
                    f"(tabella locale: «dati»)"
                )
                self._set_status(f"Query eseguita — {len(result):,} righe restituite.")
            except Exception as exc:
                QMessageBox.critical(self, "Errore SQL", str(exc))
        else:
            QMessageBox.information(
                self, "Connessione esterna",
                "L'esecuzione su database remoti richiede i driver specifici.\n"
                "Configura la connessione nella tab «B · Connessioni DB».",
            )

    def _sql_to_etl(self) -> None:
        if self.sql_result_df.empty:
            QMessageBox.warning(self, "Nessun risultato", "Esegui prima una query SQL.")
            return
        self._set_raw_df(self.sql_result_df, label="Risultato SQL")
        self.query_subtabs.setCurrentIndex(4)

    def _sql_save(self) -> None:
        query = self.sql_editor.toPlainText().strip()
        if not query:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva query", "", "SQL (*.sql);;Testo (*.txt)"
        )
        if path:
            Path(path).write_text(query, encoding="utf-8")
            self._set_status(f"Query salvata: {path}")

    def _sql_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Apri file SQL", "", "SQL (*.sql);;Testo (*.txt)"
        )
        if path:
            self.sql_editor.setPlainText(Path(path).read_text(encoding="utf-8"))

    def _sql_toggle_theme(self) -> None:
        self.sql_theme_dark = not self.sql_theme_dark
        self._sql_apply_theme()

    def _sql_apply_theme(self) -> None:
        if self.sql_theme_dark:
            self.sql_editor.setStyleSheet(
                "QTextEdit { background:#1E1E1E; color:#D4D4D4; "
                "font-family:'Courier New'; font-size:12px; "
                "border:1px solid #3C3C3C; }"
            )
        else:
            self.sql_editor.setStyleSheet(
                "QTextEdit { background:#FAFAFA; color:#111111; "
                "font-family:'Courier New'; font-size:12px; "
                "border:1px solid #CCCCCC; }"
            )

    # ── D · ETL / Trasformazioni ──────────────────────────────────────────────

    def _build_etl_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ── Intestazione ──────────────────────────────────────────────────────
        header = QHBoxLayout()
        self.etl_info_lbl = QLabel("Nessun dataset caricato.")
        btn_reset    = QPushButton("↩ Ripristina")
        btn_undo     = QPushButton("↺ Annulla")
        btn_export   = QPushButton("📤 Esporta")
        btn_norm     = QPushButton("🔤 Norm. colonne")
        btn_dedup    = QPushButton("🗑 Dedup")
        btn_dropnull = QPushButton("⊘ Drop nulli")
        btn_addidx   = QPushButton("# Aggiungi indice")
        for b, slot in [
            (btn_reset,    self._etl_reset),
            (btn_undo,     self._etl_undo),
            (btn_export,   self._etl_export),
            (btn_norm,     self._etl_normalize),
            (btn_dedup,    self._etl_dedup),
            (btn_dropnull, self._etl_drop_nulls),
            (btn_addidx,   self._etl_add_index),
        ]:
            b.clicked.connect(slot)
        btn_undo.setToolTip("Annulla l'ultima trasformazione (max 20 livelli)")
        header.addWidget(self.etl_info_lbl)
        header.addStretch()
        for b in [btn_norm, btn_dedup, btn_dropnull, btn_addidx,
                  btn_undo, btn_reset, btn_export]:
            header.addWidget(b)

        # ── Sotto-tab operazioni ──────────────────────────────────────────────
        ops_tabs = QTabWidget()
        ops_tabs.setMaximumHeight(200)
        ops_tabs.addTab(self._build_etl_ops_column(),   "Colonne")
        ops_tabs.addTab(self._build_etl_ops_filter(),   "Filtri")
        ops_tabs.addTab(self._build_etl_ops_sort(),     "Ordina")
        ops_tabs.addTab(self._build_etl_ops_agg(),      "Aggrega")
        ops_tabs.addTab(self._build_etl_ops_text(),     "Testo")
        ops_tabs.addTab(self._build_etl_ops_numeric(),  "Numerico")
        ops_tabs.addTab(self._build_etl_ops_datetime(), "Data/Ora")
        ops_tabs.addTab(self._build_etl_ops_formula(),  "Formula")
        ops_tabs.addTab(self._build_etl_ops_reshape(),  "Reshape")
        ops_tabs.addTab(self._build_etl_ops_outlier(),  "Outlier")
        ops_tabs.addTab(self._build_etl_ops_sample(),   "Campiona")

        # ── Anteprima ─────────────────────────────────────────────────────────
        self.etl_model = PandasTableModel()
        self.etl_table = _make_table_view(self.etl_model)

        # ── Log ───────────────────────────────────────────────────────────────
        self.etl_log = QTextEdit()
        self.etl_log.setReadOnly(True)
        self.etl_log.setMaximumHeight(90)
        self.etl_log.setPlaceholderText("Log trasformazioni ETL…")

        layout.addLayout(header)
        layout.addWidget(ops_tabs)
        layout.addWidget(QLabel("Dati correnti:"))
        layout.addWidget(self.etl_table, stretch=1)
        layout.addWidget(QLabel("Log ETL:"))
        layout.addWidget(self.etl_log)
        return widget

    # ── helper layout ─────────────────────────────────────────────────────────

    def _etl_row(self, *widgets) -> QWidget:
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(4,2,4,2)
        for ww in widgets:
            if isinstance(ww, int): l.addSpacing(ww)
            elif ww == "stretch":   l.addStretch()
            else:                   l.addWidget(ww)
        return w

    # ── pannelli operazioni ───────────────────────────────────────────────────

    def _build_etl_ops_column(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_col = QComboBox(); self.etl_col.setMinimumWidth(140)
        self.etl_cast = QComboBox()
        self.etl_cast.addItems(["string","int","float","datetime","boolean","category","timedelta"])
        self.etl_date_fmt = QLineEdit(); self.etl_date_fmt.setPlaceholderText("fmt (es. %d/%m/%Y)")
        self.etl_date_fmt.setMaximumWidth(140)
        self.etl_fill_strategy = QComboBox()
        self.etl_fill_strategy.addItems([
            "valore","media","mediana","moda",
            "forward fill","backward fill","interpolazione lineare",
            "zero","stringa vuota",
        ])
        self.etl_fill_val = QLineEdit(); self.etl_fill_val.setPlaceholderText("valore")
        self.etl_fill_val.setMaximumWidth(100)
        self.etl_new_col_name = QLineEdit(); self.etl_new_col_name.setPlaceholderText("nuovo nome")
        self.etl_new_col_name.setMaximumWidth(130)
        btn_cast   = QPushButton("Converti tipo"); btn_cast.clicked.connect(self._etl_cast)
        btn_rename = QPushButton("Rinomina");      btn_rename.clicked.connect(self._etl_rename)
        btn_dropc  = QPushButton("Elimina");       btn_dropc.clicked.connect(self._etl_drop_col)
        btn_fill   = QPushButton("Riempi nulli");  btn_fill.clicked.connect(self._etl_fill)
        l.addWidget(self._etl_row(
            QLabel("Colonna:"), self.etl_col, 8,
            QLabel("→ tipo:"), self.etl_cast, self.etl_date_fmt, btn_cast,
        ))
        l.addWidget(self._etl_row(
            QLabel("Riempi:"), self.etl_fill_strategy, self.etl_fill_val, btn_fill, 12,
            QLabel("Rinomina →"), self.etl_new_col_name, btn_rename, 8, btn_dropc, "stretch",
        ))
        return w

    def _build_etl_ops_filter(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        btn_add = QPushButton("➕ Aggiungi filtro"); btn_add.clicked.connect(self._etl_add_filter)
        self.etl_filter_col2 = QComboBox(); self.etl_filter_col2.setMinimumWidth(130)
        self.etl_filter_iqr_factor = QDoubleSpinBox()
        self.etl_filter_iqr_factor.setRange(0.5,5.0); self.etl_filter_iqr_factor.setValue(1.5)
        self.etl_filter_iqr_factor.setSingleStep(0.25); self.etl_filter_iqr_factor.setPrefix("k=")
        btn_drop_out = QPushButton("🚫 Rimuovi outlier IQR")
        btn_drop_out.clicked.connect(self._etl_remove_outliers_filter)
        l.addWidget(self._etl_row(btn_add, "stretch"))
        l.addWidget(self._etl_row(
            QLabel("Colonna:"), self.etl_filter_col2,
            self.etl_filter_iqr_factor, btn_drop_out, "stretch",
        ))
        return w

    def _build_etl_ops_sort(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_sort_col  = QComboBox(); self.etl_sort_col.setMinimumWidth(130)
        self.etl_sort_col2 = QComboBox(); self.etl_sort_col2.setMinimumWidth(130)
        self.etl_sort_col2.addItems(["(nessuna)"])
        self.etl_sort_asc  = QCheckBox("Asc 1"); self.etl_sort_asc.setChecked(True)
        self.etl_sort_asc2 = QCheckBox("Asc 2"); self.etl_sort_asc2.setChecked(True)
        btn_sort    = QPushButton("↕ Ordina");   btn_sort.clicked.connect(self._etl_sort)
        btn_shuffle = QPushButton("🔀 Mescola"); btn_shuffle.clicked.connect(self._etl_shuffle)
        l.addWidget(self._etl_row(
            QLabel("Col 1:"), self.etl_sort_col, self.etl_sort_asc, 12,
            QLabel("Col 2:"), self.etl_sort_col2, self.etl_sort_asc2, 12,
            btn_sort, btn_shuffle, "stretch",
        ))
        return w

    def _build_etl_ops_agg(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_grp_by  = QLineEdit(); self.etl_grp_by.setPlaceholderText("col1, col2, …")
        self.etl_grp_by.setMaximumWidth(180)
        self.etl_agg_col = QComboBox(); self.etl_agg_col.setMinimumWidth(130)
        self.etl_agg_fn  = QComboBox()
        self.etl_agg_fn.addItems(["sum","mean","count","min","max","median","std","var","first","last","nunique"])
        btn_agg = QPushButton("∑ Aggrega"); btn_agg.clicked.connect(self._etl_aggregate)
        self.etl_pivot_idx = QComboBox(); self.etl_pivot_idx.setMinimumWidth(100)
        self.etl_pivot_col = QComboBox(); self.etl_pivot_col.setMinimumWidth(100)
        self.etl_pivot_val = QComboBox(); self.etl_pivot_val.setMinimumWidth(100)
        self.etl_pivot_agg = QComboBox(); self.etl_pivot_agg.addItems(["mean","sum","count","min","max"])
        btn_pivot   = QPushButton("⊞ Pivot");        btn_pivot.clicked.connect(self._etl_pivot)
        btn_unpivot = QPushButton("⊟ Unpivot (melt)"); btn_unpivot.clicked.connect(self._etl_unpivot)
        self.etl_unpivot_id = QLineEdit(); self.etl_unpivot_id.setPlaceholderText("id cols (virgola)")
        self.etl_unpivot_id.setMaximumWidth(160)
        l.addWidget(self._etl_row(
            QLabel("Raggruppa:"), self.etl_grp_by,
            QLabel("Col:"), self.etl_agg_col, QLabel("Fn:"), self.etl_agg_fn, btn_agg, "stretch",
        ))
        l.addWidget(self._etl_row(
            QLabel("Pivot idx:"), self.etl_pivot_idx,
            QLabel("cols:"), self.etl_pivot_col,
            QLabel("val:"), self.etl_pivot_val,
            QLabel("agg:"), self.etl_pivot_agg, btn_pivot, 12,
            QLabel("id:"), self.etl_unpivot_id, btn_unpivot, "stretch",
        ))
        return w

    def _build_etl_ops_text(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_txt_col = QComboBox(); self.etl_txt_col.setMinimumWidth(130)
        self.etl_txt_op  = QComboBox()
        self.etl_txt_op.addItems([
            "maiuscolo","minuscolo","title case","strip","lstrip","rstrip",
            "sostituisci","prefisso","suffisso","estrai regex",
            "lunghezza","split","rimuovi spazi multipli",
            "rimuovi caratteri speciali","codifica url",
        ])
        self.etl_txt_extra = QLineEdit()
        self.etl_txt_extra.setPlaceholderText("extra (dipende op.): es. vec→nuo  /  sep|pos")
        self.etl_txt_extra.setMaximumWidth(220)
        btn_txt = QPushButton("Applica"); btn_txt.clicked.connect(self._etl_text_transform)
        l.addWidget(self._etl_row(
            QLabel("Colonna:"), self.etl_txt_col,
            QLabel("Op.:"), self.etl_txt_op,
            QLabel("Extra:"), self.etl_txt_extra, btn_txt, "stretch",
        ))
        return w

    def _build_etl_ops_numeric(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_num_col = QComboBox(); self.etl_num_col.setMinimumWidth(130)
        self.etl_num_op  = QComboBox()
        self.etl_num_op.addItems([
            "arrotonda","assoluto","logaritmo","log10","radice quadrata",
            "normalizza 0-1","standardizza (z-score)","clip","potenza",
            "percentuale sul totale","rank","bin","cumsum","cumprod",
            "diff","shift","rolling mean","rolling std",
        ])
        self.etl_num_extra = QLineEdit()
        self.etl_num_extra.setPlaceholderText("param (es. decimali, min,max, n_bins, window)")
        self.etl_num_extra.setMaximumWidth(200)
        btn_num = QPushButton("Applica"); btn_num.clicked.connect(self._etl_numeric_transform)
        l.addWidget(self._etl_row(
            QLabel("Colonna:"), self.etl_num_col,
            QLabel("Op.:"), self.etl_num_op,
            QLabel("Param.:"), self.etl_num_extra, btn_num, "stretch",
        ))
        return w

    def _build_etl_ops_datetime(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_dt_col   = QComboBox(); self.etl_dt_col.setMinimumWidth(130)
        self.etl_dt_parts = QLineEdit()
        self.etl_dt_parts.setPlaceholderText("anno,mese,giorno,ora,giorno_settimana,trimestre,is_weekend,nome_mese…")
        btn_ext = QPushButton("Estrai"); btn_ext.clicked.connect(self._etl_dt_extract)
        self.etl_dt_col2   = QComboBox(); self.etl_dt_col2.setMinimumWidth(130)
        self.etl_dt_unit   = QComboBox()
        self.etl_dt_unit.addItems(["days","hours","minutes","seconds","weeks","months","years"])
        self.etl_dt_newcol = QLineEdit(); self.etl_dt_newcol.setPlaceholderText("nome col risultato")
        self.etl_dt_newcol.setMaximumWidth(150)
        btn_diff = QPushButton("Diff date"); btn_diff.clicked.connect(self._etl_dt_diff)
        l.addWidget(self._etl_row(
            QLabel("Col data:"), self.etl_dt_col,
            QLabel("Componenti:"), self.etl_dt_parts, btn_ext, "stretch",
        ))
        l.addWidget(self._etl_row(
            QLabel("Col1:"), self.etl_dt_col, QLabel("- Col2:"), self.etl_dt_col2,
            QLabel("Unità:"), self.etl_dt_unit, self.etl_dt_newcol, btn_diff, "stretch",
        ))
        return w

    def _build_etl_ops_formula(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_formula_col  = QLineEdit(); self.etl_formula_col.setPlaceholderText("nome nuova colonna")
        self.etl_formula_col.setMaximumWidth(150)
        self.etl_formula_expr = QLineEdit()
        self.etl_formula_expr.setPlaceholderText("es.  prezzo * quantita * 1.22  o  col_a + col_b")
        btn_formula = QPushButton("Crea col."); btn_formula.clicked.connect(self._etl_formula)
        self.etl_cond_col   = QComboBox(); self.etl_cond_col.setMinimumWidth(100)
        self.etl_cond_op    = QComboBox()
        self.etl_cond_op.addItems(["==","!=",">",">=","<","<=","contiene","non contiene"])
        self.etl_cond_val   = QLineEdit(); self.etl_cond_val.setPlaceholderText("valore cond.")
        self.etl_cond_val.setMaximumWidth(90)
        self.etl_cond_true  = QLineEdit(); self.etl_cond_true.setPlaceholderText("se vero")
        self.etl_cond_true.setMaximumWidth(80)
        self.etl_cond_false = QLineEdit(); self.etl_cond_false.setPlaceholderText("se falso")
        self.etl_cond_false.setMaximumWidth(80)
        self.etl_cond_new   = QLineEdit(); self.etl_cond_new.setPlaceholderText("nuova col")
        self.etl_cond_new.setMaximumWidth(110)
        btn_cond = QPushButton("IF/ELSE"); btn_cond.clicked.connect(self._etl_conditional)
        self.etl_map_src  = QComboBox(); self.etl_map_src.setMinimumWidth(100)
        self.etl_map_new  = QLineEdit(); self.etl_map_new.setPlaceholderText("col risultato")
        self.etl_map_new.setMaximumWidth(130)
        self.etl_map_expr = QLineEdit(); self.etl_map_expr.setPlaceholderText("A→1,B→2,C→3")
        btn_map = QPushButton("Map valori"); btn_map.clicked.connect(self._etl_map)
        l.addWidget(self._etl_row(
            QLabel("Col:"), self.etl_formula_col, QLabel("="), self.etl_formula_expr, btn_formula, "stretch",
        ))
        l.addWidget(self._etl_row(
            QLabel("SE:"), self.etl_cond_col, self.etl_cond_op, self.etl_cond_val,
            QLabel("→"), self.etl_cond_true, QLabel("/"), self.etl_cond_false,
            QLabel("→"), self.etl_cond_new, btn_cond, 12,
            QLabel("Map:"), self.etl_map_src, QLabel("→"), self.etl_map_new,
            self.etl_map_expr, btn_map, "stretch",
        ))
        return w

    def _build_etl_ops_reshape(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_keep_cols_edit = QLineEdit()
        self.etl_keep_cols_edit.setPlaceholderText("Mantieni solo: col1, col2, …")
        btn_keep = QPushButton("Mantieni"); btn_keep.clicked.connect(self._etl_keep_cols)
        self.etl_drop_cols_multi_edit = QLineEdit()
        self.etl_drop_cols_multi_edit.setPlaceholderText("Elimina: col1, col2, …")
        btn_drop_multi = QPushButton("Elimina"); btn_drop_multi.clicked.connect(self._etl_drop_cols_multi)
        self.etl_reorder_cols_edit = QLineEdit()
        self.etl_reorder_cols_edit.setPlaceholderText("Riordina: col2, col1, col3, … (resto in fondo)")
        btn_reorder = QPushButton("Riordina"); btn_reorder.clicked.connect(self._etl_reorder_cols)
        l.addWidget(self._etl_row(self.etl_keep_cols_edit, btn_keep, "stretch"))
        l.addWidget(self._etl_row(self.etl_drop_cols_multi_edit, btn_drop_multi, "stretch"))
        l.addWidget(self._etl_row(self.etl_reorder_cols_edit, btn_reorder, "stretch"))
        return w

    def _build_etl_ops_outlier(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_out_cols = QLineEdit()
        self.etl_out_cols.setPlaceholderText("Colonne numeriche sep. da virgola (vuoto = tutte)")
        self.etl_out_factor = QDoubleSpinBox()
        self.etl_out_factor.setRange(0.5,5.0); self.etl_out_factor.setValue(1.5)
        self.etl_out_factor.setSingleStep(0.25); self.etl_out_factor.setPrefix("k=")
        btn_remove = QPushButton("🚫 Rimuovi outlier"); btn_remove.clicked.connect(self._etl_remove_outliers)
        btn_cap    = QPushButton("📌 Cap (Winsorize)"); btn_cap.clicked.connect(self._etl_cap_outliers)
        l.addWidget(self._etl_row(
            QLabel("Colonne:"), self.etl_out_cols,
            self.etl_out_factor, btn_remove, btn_cap, "stretch",
        ))
        return w

    def _build_etl_ops_sample(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4,4,4,4)
        self.etl_sample_n    = QSpinBox(); self.etl_sample_n.setRange(1,1_000_000)
        self.etl_sample_n.setValue(100); self.etl_sample_n.setPrefix("n=")
        self.etl_sample_frac = QDoubleSpinBox(); self.etl_sample_frac.setRange(0.001,1.0)
        self.etl_sample_frac.setValue(0.1); self.etl_sample_frac.setSingleStep(0.05)
        self.etl_sample_frac.setPrefix("frac=")
        self.etl_sample_seed = QSpinBox(); self.etl_sample_seed.setRange(0,99999)
        self.etl_sample_seed.setValue(42); self.etl_sample_seed.setPrefix("seed=")
        self.etl_sample_mode = QComboBox(); self.etl_sample_mode.addItems(["n righe","frazione"])
        btn_sample = QPushButton("Campiona"); btn_sample.clicked.connect(self._etl_sample)
        btn_head   = QPushButton("Prime N");  btn_head.clicked.connect(self._etl_head)
        btn_tail   = QPushButton("Ultime N"); btn_tail.clicked.connect(self._etl_tail)
        l.addWidget(self._etl_row(
            self.etl_sample_mode, self.etl_sample_n, self.etl_sample_frac,
            self.etl_sample_seed, btn_sample, 8, btn_head, btn_tail, "stretch",
        ))
        return w

    # ── undo stack ────────────────────────────────────────────────────────────

    def _etl_push(self) -> None:
        if not hasattr(self, "_etl_undo_stack"):
            self._etl_undo_stack: List[pd.DataFrame] = []
        self._etl_undo_stack.append(self.working_df.copy())
        if len(self._etl_undo_stack) > 20:
            self._etl_undo_stack.pop(0)

    def _etl_undo(self) -> None:
        if not hasattr(self, "_etl_undo_stack") or not self._etl_undo_stack:
            QMessageBox.information(self, "Undo", "Nessuna operazione da annullare."); return
        self.working_df = self._etl_undo_stack.pop()
        self.etl_steps.append("  ↺  Ultima operazione annullata.")
        self._etl_refresh()

    # ── refresh e log ─────────────────────────────────────────────────────────

    def _etl_refresh(self) -> None:
        df = self.working_df
        self.etl_model.update_dataframe(df)
        self.etl_table.resizeColumnsToContents()
        self.etl_info_lbl.setText(
            f"Dataset: {len(df):,} righe × {len(df.columns)} colonne"
        )
        cols = list(df.columns)
        cols_none = ["(nessuna)"] + cols
        for combo, items in [
            (self.etl_col,           cols),
            (self.etl_sort_col,      cols),
            (self.etl_sort_col2,     cols_none),
            (self.etl_agg_col,       cols),
            (self.etl_pivot_idx,     cols),
            (self.etl_pivot_col,     cols),
            (self.etl_pivot_val,     cols),
            (self.etl_txt_col,       cols),
            (self.etl_num_col,       cols),
            (self.etl_dt_col,        cols),
            (self.etl_dt_col2,       cols),
            (self.etl_cond_col,      cols),
            (self.etl_map_src,       cols),
            (self.etl_filter_col2,   cols),
        ]:
            cur = combo.currentText()
            combo.blockSignals(True); combo.clear(); combo.addItems(items)
            if cur in items: combo.setCurrentText(cur)
            combo.blockSignals(False)
        self.etl_log.setPlainText(
            "\n".join(self.etl_steps[-40:]) if self.etl_steps else "—"
        )

    def _etl_log(self, msg: str) -> None:
        self.etl_steps.append(f"  ✔  {msg}")
        self._set_status(msg)

    def _etl_apply(self, fn, description: str) -> None:
        """Applica una trasformazione con undo automatico."""
        self._etl_push()
        try:
            result = fn()
            self.working_df = result
            self._etl_log(description)
            self._etl_refresh()
        except Exception as exc:
            if hasattr(self, "_etl_undo_stack") and self._etl_undo_stack:
                self._etl_undo_stack.pop()
            QMessageBox.critical(self, "Errore ETL", str(exc))

    # ── azioni globali ────────────────────────────────────────────────────────

    def _etl_reset(self) -> None:
        if self.raw_df.empty: return
        self._etl_push()
        self.working_df = self.raw_df.copy()
        self.etl_steps.clear()
        self._etl_log("Dataset ripristinato all'originale.")
        self._etl_refresh()

    def _etl_normalize(self) -> None:
        self._etl_apply(
            lambda: ETLEngine.normalize_column_names(self.working_df),
            "Nomi colonne normalizzati."
        )

    def _etl_dedup(self) -> None:
        items = ["first", "last", "Rimuovi tutti (False)"]
        choice, ok = QInputDialog.getItem(self, "Rimuovi duplicati",
            "Quale occorrenza mantenere?", items, 0, False)
        if not ok: return
        keep = cast(Literal["first", "last", False], False if "False" in choice else choice)
        before = len(self.working_df)
        self._etl_apply(
            lambda: ETLEngine.drop_duplicates(self.working_df, keep=keep),
            f"Rimosse righe duplicate (keep={keep})."
        )

    def _etl_drop_nulls(self) -> None:
        before = len(self.working_df)
        self._etl_apply(
            lambda: ETLEngine.drop_nulls(self.working_df),
            f"Righe con nulli eliminate (erano {before - len(self.working_df)})."
        )

    def _etl_add_index(self) -> None:
        name, ok = QInputDialog.getText(self, "Aggiungi indice",
            "Nome colonna indice:", text="row_id")
        if not ok or not name.strip(): return
        self._etl_apply(
            lambda: ETLEngine.add_row_index(self.working_df, name.strip()),
            f"Aggiunta colonna indice «{name.strip()}»."
        )

    # ── colonne ───────────────────────────────────────────────────────────────

    def _etl_cast(self) -> None:
        col, dtype = self.etl_col.currentText(), self.etl_cast.currentText()
        fmt = self.etl_date_fmt.text().strip()
        if not col: return
        self._etl_apply(
            lambda: ETLEngine.cast_column(self.working_df, col, dtype, fmt),
            f"«{col}» convertita in {dtype}."
        )

    def _etl_rename(self) -> None:
        col = self.etl_col.currentText()
        new = self.etl_new_col_name.text().strip()
        if not col or not new:
            QMessageBox.warning(self, "Rinomina", "Seleziona colonna e inserisci il nuovo nome."); return
        self._etl_apply(
            lambda: ETLEngine.rename_column(self.working_df, col, new),
            f"«{col}» rinominata in «{new}»."
        )

    def _etl_drop_col(self) -> None:
        col = self.etl_col.currentText()
        if not col: return
        if QMessageBox.question(self, "Conferma", f"Eliminare «{col}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes: return
        self._etl_apply(
            lambda: ETLEngine.drop_column(self.working_df, col),
            f"Colonna «{col}» eliminata."
        )

    def _etl_fill(self) -> None:
        col      = self.etl_col.currentText()
        strategy = self.etl_fill_strategy.currentText()
        val      = self.etl_fill_val.text()
        if not col: return
        self._etl_apply(
            lambda: ETLEngine.fill_nulls(self.working_df, col, strategy, val),
            f"Nulli di «{col}» riempiti con strategia «{strategy}»."
        )

    def _etl_keep_cols(self) -> None:
        cols = [c.strip() for c in self.etl_keep_cols_edit.text().split(",") if c.strip()]
        if not cols:
            QMessageBox.warning(self, "Mantieni", "Inserisci almeno una colonna."); return
        self._etl_apply(
            lambda: ETLEngine.keep_columns(self.working_df, cols),
            f"Mantenute solo: {cols}."
        )

    def _etl_drop_cols_multi(self) -> None:
        cols = [c.strip() for c in self.etl_drop_cols_multi_edit.text().split(",") if c.strip()]
        if not cols:
            QMessageBox.warning(self, "Elimina", "Inserisci almeno una colonna."); return
        self._etl_apply(
            lambda: ETLEngine.drop_columns(self.working_df, cols),
            f"Eliminate colonne: {cols}."
        )

    def _etl_reorder_cols(self) -> None:
        cols = [c.strip() for c in self.etl_reorder_cols_edit.text().split(",") if c.strip()]
        if not cols:
            QMessageBox.warning(self, "Riordina", "Inserisci l'ordine desiderato."); return
        self._etl_apply(
            lambda: ETLEngine.reorder_columns(self.working_df, cols),
            f"Colonne riordinate."
        )

    # ── filtri ────────────────────────────────────────────────────────────────

    def _etl_add_filter(self) -> None:
        if self.working_df.empty:
            QMessageBox.warning(self, "Dati mancanti", "Nessun dataset caricato."); return
        dlg = FilterDialog(list(self.working_df.columns), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            col, op, val = dlg.result_values()
            before = len(self.working_df)
            self._etl_apply(
                lambda: ETLEngine.filter_rows(self.working_df, col, op, val),
                f"Filtro: {col} {op} {val!r} ({before} → ? righe)"
            )

    def _etl_remove_outliers_filter(self) -> None:
        col = self.etl_filter_col2.currentText()
        k   = self.etl_filter_iqr_factor.value()
        if not col: return
        before = len(self.working_df)
        self._etl_apply(
            lambda: ETLEngine.remove_outliers_iqr(self.working_df, [col], k),
            f"Outlier IQR rimossi da «{col}» (k={k})."
        )

    # ── ordinamento ───────────────────────────────────────────────────────────

    def _etl_sort(self) -> None:
        col1 = self.etl_sort_col.currentText()
        col2 = self.etl_sort_col2.currentText()
        if not col1: return
        cols = [col1]; asc = [self.etl_sort_asc.isChecked()]
        if col2 not in {"", "(nessuna)"}:
            cols.append(col2); asc.append(self.etl_sort_asc2.isChecked())
        self._etl_apply(
            lambda: ETLEngine.sort_rows(self.working_df, cols, asc),
            f"Ordinato per {cols}."
        )

    def _etl_shuffle(self) -> None:
        self._etl_apply(
            lambda: self.working_df.sample(frac=1, random_state=None).reset_index(drop=True),
            "Righe mescolate casualmente."
        )

    # ── aggregazione ──────────────────────────────────────────────────────────

    def _etl_aggregate(self) -> None:
        grp = self.etl_grp_by.text().strip()
        if not grp:
            QMessageBox.warning(self, "Raggruppa", "Inserisci colonne di raggruppamento."); return
        group_cols = [c.strip() for c in grp.split(",") if c.strip()]
        agg_col = self.etl_agg_col.currentText()
        agg_fn  = self.etl_agg_fn.currentText()
        self._etl_apply(
            lambda: ETLEngine.aggregate(self.working_df, group_cols, agg_col, agg_fn),
            f"GROUP BY {group_cols} → {agg_fn}({agg_col})"
        )

    def _etl_pivot(self) -> None:
        idx = self.etl_pivot_idx.currentText()
        col = self.etl_pivot_col.currentText()
        val = self.etl_pivot_val.currentText()
        agg = self.etl_pivot_agg.currentText()
        if not all([idx, col, val]):
            QMessageBox.warning(self, "Pivot", "Seleziona indice, colonne e valori."); return
        self._etl_apply(
            lambda: ETLEngine.pivot(self.working_df, idx, col, val, agg),
            f"Pivot: index={idx}, columns={col}, values={val}, agg={agg}"
        )

    def _etl_unpivot(self) -> None:
        id_vars = [c.strip() for c in self.etl_unpivot_id.text().split(",") if c.strip()]
        if not id_vars:
            QMessageBox.warning(self, "Unpivot", "Specifica le colonne ID."); return
        self._etl_apply(
            lambda: ETLEngine.unpivot(self.working_df, id_vars),
            f"Unpivot (melt): id_vars={id_vars}"
        )

    # ── testo ─────────────────────────────────────────────────────────────────

    def _etl_text_transform(self) -> None:
        col   = self.etl_txt_col.currentText()
        op    = self.etl_txt_op.currentText()
        extra = self.etl_txt_extra.text()
        if not col: return
        self._etl_apply(
            lambda: ETLEngine.text_transform(self.working_df, col, op, extra),
            f"Testo [{op}] su «{col}»."
        )

    # ── numerico ──────────────────────────────────────────────────────────────

    def _etl_numeric_transform(self) -> None:
        col   = self.etl_num_col.currentText()
        op    = self.etl_num_op.currentText()
        extra = self.etl_num_extra.text()
        if not col: return
        self._etl_apply(
            lambda: ETLEngine.numeric_transform(self.working_df, col, op, extra),
            f"Numerico [{op}] su «{col}»."
        )

    # ── data/ora ──────────────────────────────────────────────────────────────

    def _etl_dt_extract(self) -> None:
        col   = self.etl_dt_col.currentText()
        parts = [p.strip() for p in self.etl_dt_parts.text().split(",") if p.strip()]
        if not col or not parts:
            QMessageBox.warning(self, "Estrai", "Seleziona colonna e componenti."); return
        self._etl_apply(
            lambda: ETLEngine.datetime_extract(self.working_df, col, parts),
            f"Estratte da «{col}»: {parts}"
        )

    def _etl_dt_diff(self) -> None:
        col1 = self.etl_dt_col.currentText()
        col2 = self.etl_dt_col2.currentText()
        unit = self.etl_dt_unit.currentText()
        new  = self.etl_dt_newcol.text().strip()
        if not col1 or not col2 or col1 == col2:
            QMessageBox.warning(self, "Diff date", "Seleziona due colonne diverse."); return
        self._etl_apply(
            lambda: ETLEngine.datetime_diff(self.working_df, col1, col2, unit, new),
            f"Diff {col1} - {col2} in {unit}."
        )

    # ── formula / condizionale / map ──────────────────────────────────────────

    def _etl_formula(self) -> None:
        new_col = self.etl_formula_col.text().strip()
        expr    = self.etl_formula_expr.text().strip()
        if not new_col or not expr:
            QMessageBox.warning(self, "Formula", "Inserisci nome colonna e formula."); return
        self._etl_apply(
            lambda: ETLEngine.add_formula_column(self.working_df, new_col, expr),
            f"Colonna «{new_col}» = {expr}"
        )

    def _etl_conditional(self) -> None:
        cond_col  = self.etl_cond_col.currentText()
        cond_op   = self.etl_cond_op.currentText()
        cond_val  = self.etl_cond_val.text()
        true_val  = self.etl_cond_true.text()
        false_val = self.etl_cond_false.text()
        new_col   = self.etl_cond_new.text().strip()
        if not cond_col or not new_col:
            QMessageBox.warning(self, "IF/ELSE", "Inserisci tutti i campi."); return
        self._etl_apply(
            lambda: ETLEngine.add_conditional_column(
                self.working_df, new_col, cond_col, cond_op, cond_val, true_val, false_val),
            f"IF «{cond_col}» {cond_op} {cond_val!r} → «{new_col}»"
        )

    def _etl_map(self) -> None:
        src     = self.etl_map_src.currentText()
        new     = self.etl_map_new.text().strip()
        mapping = self.etl_map_expr.text().strip()
        if not src or not new or not mapping:
            QMessageBox.warning(self, "Map", "Inserisci tutti i campi."); return
        self._etl_apply(
            lambda: ETLEngine.add_map_column(self.working_df, src, new, mapping),
            f"Map: «{src}» → «{new}»"
        )

    # ── outlier ───────────────────────────────────────────────────────────────

    def _etl_remove_outliers(self) -> None:
        text     = self.etl_out_cols.text().strip()
        num_cols = self.working_df.select_dtypes(include="number").columns.tolist()
        cols     = [c.strip() for c in text.split(",") if c.strip()] or num_cols
        k        = self.etl_out_factor.value()
        self._etl_apply(
            lambda: ETLEngine.remove_outliers_iqr(self.working_df, cols, k),
            f"Outlier IQR rimossi (k={k}) da {cols}."
        )

    def _etl_cap_outliers(self) -> None:
        text     = self.etl_out_cols.text().strip()
        num_cols = self.working_df.select_dtypes(include="number").columns.tolist()
        cols     = [c.strip() for c in text.split(",") if c.strip()] or num_cols
        k        = self.etl_out_factor.value()
        self._etl_apply(
            lambda: ETLEngine.cap_outliers_iqr(self.working_df, cols, k),
            f"Outlier limitati (cap, k={k}) su {cols}."
        )

    # ── campionamento ─────────────────────────────────────────────────────────

    def _etl_sample(self) -> None:
        seed = self.etl_sample_seed.value()
        if self.etl_sample_mode.currentText() == "n righe":
            n = self.etl_sample_n.value()
            self._etl_apply(
                lambda: ETLEngine.sample_rows(self.working_df, n=n, seed=seed),
                f"Campionate {n} righe (seed={seed})."
            )
        else:
            frac = self.etl_sample_frac.value()
            self._etl_apply(
                lambda: ETLEngine.sample_rows(self.working_df, frac=frac, seed=seed),
                f"Campionate {frac*100:.0f}% righe (seed={seed})."
            )

    def _etl_head(self) -> None:
        n = self.etl_sample_n.value()
        self._etl_apply(
            lambda: self.working_df.head(n).reset_index(drop=True),
            f"Mantenute prime {n} righe."
        )

    def _etl_tail(self) -> None:
        n = self.etl_sample_n.value()
        self._etl_apply(
            lambda: self.working_df.tail(n).reset_index(drop=True),
            f"Mantenute ultime {n} righe."
        )

    # ── export ────────────────────────────────────────────────────────────────

    def _etl_export(self) -> None:
        if self.working_df.empty:
            QMessageBox.warning(self, "Nessun dato", "Nessun dataset da esportare."); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta dati", "",
            "CSV (*.csv);;TSV (*.tsv);;Excel (*.xlsx);;JSON (*.json);;"
            "Parquet (*.parquet);;HTML (*.html);;Pickle (*.pkl)",
        )
        if path:
            try:
                ETLEngine.export(self.working_df, Path(path))
                QMessageBox.information(self, "Esportato", f"File salvato:\n{path}")
                self._set_status(f"Esportato: {path}")
            except Exception as exc:
                QMessageBox.critical(self, "Errore esportazione", str(exc))


    def _build_report_tab(self) -> QWidget:
        widget = QWidget()
        root = QVBoxLayout(widget)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── Header esportazione ──────────────────────────────────────────────
        exp_group = QGroupBox("Esportazione Report")
        exp_layout = QHBoxLayout(exp_group)
        exp_layout.setSpacing(6)

        self.rpt_title_edit = QLineEdit("HealthReport Studio – Report")
        self.rpt_title_edit.setPlaceholderText("Titolo documento…")
        self.rpt_title_edit.setMaximumWidth(300)
        self.rpt_author_edit = QLineEdit()
        self.rpt_author_edit.setPlaceholderText("Autore")
        self.rpt_author_edit.setMaximumWidth(180)
        self.rpt_dpi_spin = QSpinBox()
        self.rpt_dpi_spin.setRange(72, 600); self.rpt_dpi_spin.setValue(150)
        self.rpt_dpi_spin.setSuffix(" DPI")
        self.rpt_paper_combo = QComboBox()
        self.rpt_paper_combo.addItems(["A4","A3","Letter","Legal"])
        self.rpt_orient_combo = QComboBox()
        self.rpt_orient_combo.addItems(["Portrait","Landscape"])

        for lbl, fmt, tip in [
            ("📄 PDF",      "pdf",  "Tutti i grafici e tabelle in un unico PDF"),
            ("📊 Excel",    "xlsx", "Tabelle statistiche in Excel"),
            ("🌐 HTML",     "html", "Report completo come pagina HTML"),
            ("📑 PPTX",     "pptx", "Ogni grafico come diapositiva PowerPoint"),
            ("🖼 PNG/SVG",  "png",  "Ogni grafico come PNG + SVG ad alta risoluzione"),
            ("📋 CSV",      "csv",  "Statistiche descrittive in CSV"),
            ("📝 ODT",      "odt",  "Report in formato ODT (LibreOffice)"),
        ]:
            b = QPushButton(lbl)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, f=fmt: self._rpt_export(f))
            exp_layout.addWidget(b)

        exp_layout.insertWidget(0, QLabel("Titolo:"))
        exp_layout.insertWidget(1, self.rpt_title_edit)
        exp_layout.insertWidget(2, QLabel("Autore:"))
        exp_layout.insertWidget(3, self.rpt_author_edit)
        exp_layout.insertWidget(4, QLabel("Carta:"))
        exp_layout.insertWidget(5, self.rpt_paper_combo)
        exp_layout.insertWidget(6, self.rpt_orient_combo)
        exp_layout.insertWidget(7, self.rpt_dpi_spin)
        exp_layout.insertWidget(8, _separator())
        exp_layout.addStretch()

        self.rpt_subtabs = QTabWidget()
        self.rpt_subtabs.addTab(self._build_rpt_overview_tab(),  "I · Panoramica Dataset")
        self.rpt_subtabs.addTab(self._build_rpt_charts_tab(),    "II · Grafici Base")
        self.rpt_subtabs.addTab(self._build_rpt_advanced_tab(),  "III · Statistiche Avanzate")
        self.rpt_subtabs.addTab(self._build_rpt_forecast_tab(),  "IV · Previsioni & Probabilità")

        root.addWidget(exp_group)
        root.addWidget(self.rpt_subtabs, stretch=1)
        return widget

    # ── I · Panoramica Dataset ───────────────────────────────────────────────

    def _build_rpt_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        bar = QHBoxLayout()
        btn_analyze = QPushButton("🔍  Analizza Dataset")
        btn_analyze.clicked.connect(self._rpt_run_overview)
        btn_copy = QPushButton("📋  Copia testo")
        btn_copy.clicked.connect(lambda: (
            QApplication.clipboard().setText(self.rpt_ov_text.toPlainText()),
            self._set_status("Testo copiato.")
        ))
        bar.addWidget(btn_analyze); bar.addWidget(btn_copy); bar.addStretch()
        self.rpt_ov_progress = QProgressBar()
        self.rpt_ov_progress.setRange(0, 0); self.rpt_ov_progress.setVisible(False)
        self.rpt_ov_progress.setMaximumWidth(160)
        bar.addWidget(self.rpt_ov_progress)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.rpt_ov_text = QTextEdit()
        self.rpt_ov_text.setReadOnly(True)
        self.rpt_ov_text.setFont(QFont("Courier New", 10))
        self.rpt_ov_text.setPlaceholderText(
            "Premi «Analizza Dataset» per la profilazione automatica.\n\n"
            "Verranno rilevati:\n"
            "  • Tipo di ogni colonna (numerico, categorico, datetime, booleano)\n"
            "  • Percentuale di valori nulli per colonna\n"
            "  • Statistiche descrittive (min, max, media, mediana, std, skewness, kurtosi)\n"
            "  • Cardinalità colonne categoriche + top valori\n"
            "  • Correlazioni significative (|r| ≥ 0.7)\n"
            "  • Outlier rilevati con metodo IQR\n"
            "  • Suggerimenti automatici sui tipi di analisi applicabili"
        )

        self.rpt_ov_canvas_area = QScrollArea()
        self.rpt_ov_canvas_area.setWidgetResizable(True)
        self.rpt_ov_canvas_inner = QWidget()
        self.rpt_ov_canvas_layout = QVBoxLayout(self.rpt_ov_canvas_inner)
        self.rpt_ov_canvas_area.setWidget(self.rpt_ov_canvas_inner)

        splitter.addWidget(self.rpt_ov_text)
        splitter.addWidget(self.rpt_ov_canvas_area)
        splitter.setSizes([480, 480])

        layout.addLayout(bar)
        layout.addWidget(splitter, stretch=1)
        return widget

    def _rpt_run_overview(self) -> None:
        df = self.working_df
        if df.empty:
            QMessageBox.warning(self, "Dati mancanti",
                "Nessun dataset. Vai a «Data Query» e carica un file."); return

        self.rpt_ov_progress.setVisible(True)
        QApplication.processEvents()

        lines: List[str] = []
        SEP = "─" * 68
        num_cols  = df.select_dtypes(include="number").columns.tolist()
        cat_cols  = df.select_dtypes(include=["object","category","string"]).columns.tolist()
        dt_cols   = df.select_dtypes(include=["datetime","datetimetz"]).columns.tolist()
        bool_cols = df.select_dtypes(include="bool").columns.tolist()

        lines += [
            "╔══════════════════════════════════════════════════════════════════╗",
            "║           PROFILAZIONE AUTOMATICA DEL DATASET                   ║",
            "╚══════════════════════════════════════════════════════════════════╝",
            f"  Righe   : {len(df):,}    Colonne: {len(df.columns)}",
            f"  Memoria : {df.memory_usage(deep=True).sum()/1024:.1f} KB", SEP,
            "TIPI DI COLONNA",
            f"  Numeriche   ({len(num_cols)}): {', '.join(num_cols) or '—'}",
            f"  Categoriche ({len(cat_cols)}): {', '.join(cat_cols) or '—'}",
            f"  Datetime    ({len(dt_cols)}): {', '.join(dt_cols) or '—'}",
            f"  Booleane    ({len(bool_cols)}): {', '.join(bool_cols) or '—'}", SEP,
        ]

        # Nulli
        null_counts = df.isnull().sum()
        null_pct    = null_counts / len(df) * 100
        lines.append("VALORI NULLI")
        for col in df.columns:
            pct  = null_pct[col]
            flag = "  ⚠ ALTA" if pct > 30 else ("  ⚡" if pct > 10 else "")
            lines.append(f"  {col:<30} {null_counts[col]:>6} ({pct:5.1f}%){flag}")
        lines.append(SEP)

        # Statistiche numeriche
        if num_cols:
            lines.append("STATISTICHE DESCRITTIVE")
            desc = df[num_cols].describe(percentiles=[.05,.25,.5,.75,.95]).T
            try:
                skew_vals = df[num_cols].skew()
                kurt_vals = df[num_cols].kurtosis()
            except Exception:
                skew_vals = pd.Series({c: float("nan") for c in num_cols})
                kurt_vals = pd.Series({c: float("nan") for c in num_cols})
            for col in num_cols:
                r = desc.loc[col]
                lines += [
                    f"  {col}",
                    f"    min={r['min']:.4g}  max={r['max']:.4g}  mean={r['mean']:.4g}  median={r['50%']:.4g}",
                    f"    std={r['std']:.4g}  skew={skew_vals[col]:.3f}  kurt={kurt_vals[col]:.3f}",
                    f"    p05={r['5%']:.4g}  p25={r['25%']:.4g}  p75={r['75%']:.4g}  p95={r['95%']:.4g}",
                ]
            lines.append(SEP)

        # Categoriche
        if cat_cols:
            lines.append("COLONNE CATEGORICHE")
            for col in cat_cols:
                vc = df[col].value_counts(dropna=False)
                top3 = ", ".join(f"{v!r}({c})" for v, c in vc.head(3).items())
                lines.append(f"  {col:<30} card={len(vc):,}  top3: {top3}")
            lines.append(SEP)

        # Correlazioni
        if len(num_cols) >= 2:
            corr = df[num_cols].corr().abs()
            corr_values = corr.to_numpy(dtype=float)
            high: List[Tuple[str, str, float]] = []
            for i, c1 in enumerate(num_cols):
                for j, c2 in enumerate(num_cols[i+1:], start=i+1):
                    corr_value = corr_values[i, j]
                    if not math.isnan(corr_value) and corr_value >= 0.7:
                        high.append((c1, c2, corr_value))
            lines.append("CORRELAZIONI SIGNIFICATIVE (|r| ≥ 0.7)")
            if high:
                for c1,c2,v in sorted(high, key=lambda x: -x[2]):
                    lines.append(f"  {c1} ↔ {c2}: r = {v:.3f}")
            else:
                lines.append("  Nessuna.")
            lines.append(SEP)

        # Outlier IQR
        if num_cols:
            lines.append("OUTLIER (metodo IQR)")
            for col in num_cols:
                s = df[col].dropna()
                q1,q3 = s.quantile(0.25), s.quantile(0.75)
                iqr   = q3 - q1
                n_out = int(((s < q1-1.5*iqr)|(s > q3+1.5*iqr)).sum())
                if n_out > 0:
                    lines.append(f"  {col:<30} {n_out:>5} ({n_out/len(s)*100:.1f}%)")
            lines.append(SEP)

        # Suggerimenti
        sugg: List[str] = []
        if len(num_cols) >= 1: sugg += ["• Istogrammi e box-plot (distribuzioni numeriche)",
                                         "• Statistiche descrittive complete"]
        if len(num_cols) >= 2: sugg += ["• Scatter plot e matrice di correlazione",
                                         "• Regressione lineare / multipla"]
        if cat_cols and num_cols: sugg += ["• Box-plot per gruppo", "• Test ANOVA / Kruskal-Wallis",
                                            "• Barre aggregate per categoria"]
        if cat_cols: sugg += ["• Grafici a torta / barre (frequenze)", "• Test Chi-quadro"]
        if dt_cols:  sugg += ["• Serie temporali e trend", "• Decomposizione stagionale",
                               "• Previsioni ARIMA"]
        if len(num_cols) >= 3: sugg += ["• PCA", "• Clustering K-Means / DBSCAN"]
        lines.append("ANALISI SUGGERITE")
        lines += [f"  {s}" for s in sugg]

        self.rpt_ov_text.setPlainText("\n".join(lines))
        self._rpt_build_overview_charts(df, num_cols, cat_cols)
        self.rpt_ov_progress.setVisible(False)
        self._set_status(f"Profilazione completata — {len(df.columns)} colonne.")

    def _rpt_build_overview_charts(self, df, num_cols: list, cat_cols: list) -> None:
        for i in reversed(range(self.rpt_ov_canvas_layout.count())):
            item = self.rpt_ov_canvas_layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w: w.deleteLater()

        dpi = self.rpt_dpi_spin.value()

        # ① Valori nulli
        null_pct = df.isnull().mean() * 100
        if null_pct.sum() > 0:
            fig, ax = plt.subplots(figsize=(6, max(2.5, len(df.columns)*0.32)), dpi=dpi)
            null_pct.sort_values(ascending=True).plot.barh(ax=ax, color="#E07070")
            ax.set_xlabel("% valori nulli"); ax.set_title("Valori mancanti")
            ax.axvline(30, color="red", ls="--", lw=0.8, label="30%"); ax.legend(fontsize=8)
            plt.tight_layout(); self._rpt_add_canvas(fig, "Valori mancanti")

        # ② Torta tipi di colonna
        tc = {k:v for k,v in {"Numeriche":len(num_cols),"Categoriche":len(cat_cols),
              "Datetime":len(df.select_dtypes(include=["datetime","datetimetz"]).columns),
              "Booleane":len(df.select_dtypes(include="bool").columns)}.items() if v}
        if tc:
            fig, ax = plt.subplots(figsize=(4.5, 3.5), dpi=dpi)
            ax.pie(list(tc.values()), labels=list(tc.keys()), autopct="%1.0f%%", startangle=90)
            ax.set_title("Tipi di colonna"); plt.tight_layout()
            self._rpt_add_canvas(fig, "Tipi colonna")

        # ③ Box-plot numeriche
        if num_cols:
            show = num_cols[:12]
            fig, ax = plt.subplots(figsize=(max(5, len(show)*0.8), 4), dpi=dpi)
            box_data: List[np.ndarray] = [
                pd.to_numeric(df[c], errors="coerce").dropna().to_numpy(dtype=float)
                for c in show
            ]
            ax.boxplot(box_data, patch_artist=True)
            ax.set_xticks(range(1, len(show) + 1))
            ax.set_xticklabels([str(v) for v in show], rotation=45, ha="right", fontsize=8)
            ax.set_title("Box-plot variabili numeriche"); plt.tight_layout()
            self._rpt_add_canvas(fig, "Boxplot")

        # ④ Heatmap correlazione
        if len(num_cols) >= 2:
            show = num_cols[:14]
            corr = df[show].corr()
            corr_values = corr.to_numpy(dtype=float)
            n = len(show)
            fig, ax = plt.subplots(figsize=(max(4, n*0.55), max(3.5, n*0.5)), dpi=dpi)
            im = ax.imshow(corr_values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
            ax.set_xticks(range(n)); ax.set_xticklabels(show, rotation=45, ha="right", fontsize=7)
            ax.set_yticks(range(n)); ax.set_yticklabels(show, fontsize=7)
            for i in range(n):
                for j in range(n):
                    ax.text(j, i, f"{corr_values[i,j]:.2f}", ha="center", va="center", fontsize=6)
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            ax.set_title("Matrice di correlazione"); plt.tight_layout()
            self._rpt_add_canvas(fig, "Correlazione")

        # ⑤ Top categoria
        if cat_cols:
            col = cat_cols[0]
            vc = df[col].value_counts(dropna=False).head(15)
            fig, ax = plt.subplots(figsize=(6, max(2.5, len(vc)*0.35)), dpi=dpi)
            vc.sort_values().plot.barh(ax=ax, color="#6699CC")
            ax.set_title(f"Frequenze — {col}"); ax.set_xlabel("Conteggio")
            plt.tight_layout(); self._rpt_add_canvas(fig, f"Freq {col}")

    def _rpt_add_canvas(self, fig: Figure, title: str) -> None:
        self._report_figures[title] = fig
        lbl = QLabel(f"<b>{title}</b>")
        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(280)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.rpt_ov_canvas_layout.addWidget(lbl)
        self.rpt_ov_canvas_layout.addWidget(canvas)

    # ── II · Grafici Base ────────────────────────────────────────────────────

    def _build_rpt_charts_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        ctrl = QGroupBox("Configurazione grafico")
        cl = QFormLayout(ctrl)

        self.rpt_ch_type = QComboBox()
        self.rpt_ch_type.addItems([
            "Istogramma", "Box-plot", "Grafico a barre (conteggio)",
            "Grafico a barre (aggregato)", "Grafico a torta / donut",
            "Scatter plot", "Line chart", "Area chart", "Violin plot",
            "Strip / Swarm plot", "Bar chart orizzontale",
            "Grafico a bolle (bubble)", "Heatmap (pivot aggregato)",
            "Pareto chart", "Waterfall chart",
        ])
        self.rpt_ch_type.currentIndexChanged.connect(self._rpt_ch_update_controls)

        self.rpt_ch_x       = QComboBox(); self.rpt_ch_x.setMinimumWidth(160)
        self.rpt_ch_y       = QComboBox(); self.rpt_ch_y.setMinimumWidth(160)
        self.rpt_ch_hue     = QComboBox(); self.rpt_ch_hue.setMinimumWidth(130)
        self.rpt_ch_bins    = QSpinBox();  self.rpt_ch_bins.setRange(2,200); self.rpt_ch_bins.setValue(20)
        self.rpt_ch_agg     = QComboBox(); self.rpt_ch_agg.addItems(["mean","sum","count","median","std","min","max"])
        self.rpt_ch_palette = QComboBox(); self.rpt_ch_palette.addItems(["tab10","Set2","Set3","Pastel1","Dark2","viridis","plasma","coolwarm"])
        self.rpt_ch_title   = QLineEdit(); self.rpt_ch_title.setPlaceholderText("Titolo (auto)")
        self.rpt_ch_logx    = QCheckBox("Log X"); self.rpt_ch_logy = QCheckBox("Log Y")
        self.rpt_ch_grid    = QCheckBox("Griglia"); self.rpt_ch_grid.setChecked(True)
        self.rpt_ch_annot   = QCheckBox("Annotazioni")
        self.rpt_ch_kde     = QCheckBox("KDE")
        self.rpt_ch_cumul   = QCheckBox("Cumulativo")

        cl.addRow("Tipo:",              self.rpt_ch_type)
        cl.addRow("Asse X / Colonna:",  self.rpt_ch_x)
        cl.addRow("Asse Y / Valore:",   self.rpt_ch_y)
        cl.addRow("Raggruppamento:",     self.rpt_ch_hue)
        cl.addRow("N° bin:",            self.rpt_ch_bins)
        cl.addRow("Aggregazione:",      self.rpt_ch_agg)
        cl.addRow("Palette:",           self.rpt_ch_palette)
        cl.addRow("Titolo:",            self.rpt_ch_title)
        opt = QHBoxLayout()
        for chk in [self.rpt_ch_logx, self.rpt_ch_logy, self.rpt_ch_grid,
                    self.rpt_ch_annot, self.rpt_ch_kde, self.rpt_ch_cumul]:
            opt.addWidget(chk)
        opt.addStretch()
        cl.addRow("Opzioni:", _wrap(opt))

        btn_gen   = QPushButton("▶  Genera"); btn_gen.clicked.connect(self._rpt_ch_generate)
        btn_add   = QPushButton("➕  Aggiungi"); btn_add.clicked.connect(self._rpt_ch_add_to_report)
        btn_clear = QPushButton("🗑  Pulisci"); btn_clear.clicked.connect(self._rpt_ch_clear)
        btn_bar = QHBoxLayout()
        for b in [btn_gen, btn_add, btn_clear]: btn_bar.addWidget(b)
        btn_bar.addStretch()

        self.rpt_ch_fig = Figure(figsize=(8, 5))
        self.rpt_ch_canvas = FigureCanvas(self.rpt_ch_fig)
        self.rpt_ch_canvas.setMinimumHeight(350)

        layout.addWidget(ctrl)
        layout.addLayout(btn_bar)
        layout.addWidget(self.rpt_ch_canvas, stretch=1)
        return widget

    def _rpt_ch_update_controls(self, _=None) -> None:
        t = self.rpt_ch_type.currentText()
        self.rpt_ch_y.setEnabled(t in {"Scatter plot","Line chart","Area chart",
            "Grafico a barre (aggregato)","Grafico a bolle (bubble)",
            "Heatmap (pivot aggregato)","Waterfall chart"})
        self.rpt_ch_bins.setEnabled(t == "Istogramma")
        self.rpt_ch_agg.setEnabled(t in {"Grafico a barre (aggregato)",
            "Heatmap (pivot aggregato)","Waterfall chart"})
        self.rpt_ch_kde.setEnabled(t == "Istogramma")
        self.rpt_ch_cumul.setEnabled(t in {"Istogramma","Line chart"})

    def _rpt_ch_populate_combos(self) -> None:
        cols = ["(nessuna)"] + list(self.working_df.columns)
        for combo in [self.rpt_ch_x, self.rpt_ch_y, self.rpt_ch_hue]:
            cur = combo.currentText()
            combo.blockSignals(True); combo.clear(); combo.addItems(cols)
            if cur in cols: combo.setCurrentText(cur)
            combo.blockSignals(False)

    def _rpt_ch_generate(self) -> None:
        df = self.working_df
        if df.empty:
            QMessageBox.warning(self, "Dati mancanti", "Nessun dataset caricato."); return
        self._rpt_ch_populate_combos()
        t    = self.rpt_ch_type.currentText()
        xcol = self.rpt_ch_x.currentText()
        ycol = self.rpt_ch_y.currentText()
        hue  = self.rpt_ch_hue.currentText()
        bins = self.rpt_ch_bins.value()
        agg  = self.rpt_ch_agg.currentText()
        title= self.rpt_ch_title.text().strip() or t
        logx = self.rpt_ch_logx.isChecked(); logy = self.rpt_ch_logy.isChecked()
        grid = self.rpt_ch_grid.isChecked(); annot= self.rpt_ch_annot.isChecked()
        kde  = self.rpt_ch_kde.isChecked(); cumul= self.rpt_ch_cumul.isChecked()

        if xcol == "(nessuna)":
            QMessageBox.warning(self, "Colonna X", "Seleziona la colonna X."); return

        self.rpt_ch_fig.clear()
        ax = self.rpt_ch_fig.add_subplot(111)

        try:
            x = df[xcol] if xcol != "(nessuna)" else None
            y = df[ycol] if ycol not in {"(nessuna)",""} else None
            h = df[hue]  if hue  not in {"(nessuna)",""} else None
            if x is None:
                QMessageBox.warning(self,"Colonna mancante","Seleziona una colonna X."); return

            if t == "Istogramma":
                vals = pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float)
                if vals.size == 0:
                    QMessageBox.warning(self,"Dati non validi","La colonna selezionata non contiene valori numerici."); return
                if cumul:
                    ax.hist(vals, bins=bins, cumulative=True, density=True, color="#4477AA")
                else:
                    ax.hist(vals, bins=bins, color="#4477AA", edgecolor="white", alpha=0.8)
                if kde:
                    try:
                        from scipy.stats import gaussian_kde
                        kd = gaussian_kde(vals)
                        xi = np.linspace(vals.min(), vals.max(), 300)
                        ax2 = ax.twinx()
                        ax2.plot(xi, kd(xi), color="crimson", lw=2, label="KDE")
                        ax2.set_ylabel("Densità"); ax2.legend(loc="upper right")
                    except ImportError:
                        pass
                ax.set_xlabel(xcol); ax.set_ylabel("Frequenza" if not cumul else "Prob. cumulata")

            elif t == "Box-plot":
                if h is not None:
                    hue_values = list(df[hue].dropna().unique())
                    groups: List[np.ndarray] = [
                        pd.to_numeric(df[xcol][df[hue] == v], errors="coerce").dropna().to_numpy(dtype=float)
                        for v in hue_values
                    ]
                    ax.boxplot(groups, patch_artist=True)
                    ax.set_xticks(range(1, len(hue_values) + 1))
                    ax.set_xticklabels([str(v) for v in hue_values], rotation=30, ha="right")
                else:
                    ax.boxplot(pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float),
                               patch_artist=True, boxprops=dict(facecolor="#88AACC"))
                ax.set_ylabel(xcol)

            elif t == "Grafico a barre (conteggio)":
                vc = x.value_counts(dropna=False).head(30)
                vc_values = vc.to_numpy()
                bars = ax.bar(range(len(vc)), vc_values, color="#4477AA", edgecolor="white")
                ax.set_xticks(range(len(vc)))
                ax.set_xticklabels([str(v) for v in vc.index], rotation=45, ha="right", fontsize=8)
                ax.set_ylabel("Conteggio")
                if annot:
                    for bar, val in zip(bars, vc_values):
                        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(),
                                str(val), ha="center", va="bottom", fontsize=8)

            elif t == "Grafico a barre (aggregato)":
                if y is None:
                    QMessageBox.warning(self,"Y","Seleziona colonna Y."); return
                grp = df.groupby(xcol)[ycol].agg(agg).head(30)
                grp_values = pd.to_numeric(grp, errors="coerce").to_numpy(dtype=float)
                bars = ax.bar(range(len(grp)), grp_values, color="#5599AA", edgecolor="white")
                ax.set_xticks(range(len(grp)))
                ax.set_xticklabels([str(v) for v in grp.index], rotation=45, ha="right", fontsize=8)
                ax.set_ylabel(f"{agg}({ycol})")
                if annot:
                    for bar, val in zip(bars, grp_values):
                        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(),
                                f"{val:.2g}", ha="center", va="bottom", fontsize=8)

            elif t == "Grafico a torta / donut":
                vc = x.value_counts(dropna=False).head(12)
                ax.pie(vc.to_numpy(), labels=[str(v) for v in vc.index],
                       autopct="%1.1f%%", startangle=90)
                ax.add_patch(Circle((0,0), 0.55, fc="white"))

            elif t == "Scatter plot":
                if y is None:
                    QMessageBox.warning(self,"Y","Seleziona colonna Y."); return
                if h is not None:
                    for v in df[hue].unique():
                        mask = df[hue]==v
                        ax.scatter(pd.to_numeric(df.loc[mask,xcol], errors="coerce"),
                                   pd.to_numeric(df.loc[mask,ycol], errors="coerce"),
                                   label=str(v), alpha=0.6, s=30)
                    ax.legend(fontsize=8, title=hue)
                else:
                    ax.scatter(pd.to_numeric(x, errors="coerce"),
                               pd.to_numeric(y, errors="coerce"), alpha=0.5, color="#4477AA", s=25)
                ax.set_xlabel(xcol); ax.set_ylabel(ycol)

            elif t == "Line chart":
                nx = pd.to_numeric(x, errors="coerce")
                if y is not None:
                    ax.plot(nx.to_numpy(dtype=float), pd.to_numeric(y, errors="coerce").to_numpy(dtype=float),
                            color="#4477AA", lw=1.5)
                    ax.set_ylabel(ycol)
                else:
                    ax.plot(nx.to_numpy(dtype=float), color="#4477AA", lw=1.5)
                ax.set_xlabel(xcol)

            elif t == "Area chart":
                src = pd.to_numeric(y if y is not None else x, errors="coerce").dropna().to_numpy(dtype=float)
                area_x = np.arange(len(src), dtype=float)
                baseline = np.zeros_like(src)
                ax.fill(
                    np.concatenate([area_x, area_x[::-1]]),
                    np.concatenate([src, baseline[::-1]]),
                    alpha=0.5,
                    color="#4477AA",
                )
                ax.set_xlabel("Indice"); ax.set_ylabel(ycol if y is not None else xcol)

            elif t == "Violin plot":
                if h is not None:
                    hue_values = list(df[hue].dropna().unique())
                    groups = [
                        pd.to_numeric(df[xcol][df[hue] == v], errors="coerce").dropna().to_numpy(dtype=float)
                        for v in hue_values
                    ]
                    ax.violinplot(groups, showmedians=True)
                    ax.set_xticks(range(1, len(hue_values)+1))
                    ax.set_xticklabels([str(v) for v in hue_values], rotation=30, ha="right")
                else:
                    ax.violinplot(pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float), showmedians=True)
                ax.set_ylabel(xcol)

            elif t == "Strip / Swarm plot":
                vals = pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float)
                ax.scatter(np.random.uniform(-0.2,0.2,len(vals)), vals,
                           alpha=0.4, s=15, color="#4477AA")
                ax.set_xticks([]); ax.set_ylabel(xcol)

            elif t == "Bar chart orizzontale":
                vc = x.value_counts(dropna=False).head(25)
                ax.barh(range(len(vc)), vc.to_numpy(), color="#4477AA", edgecolor="white")
                ax.set_yticks(range(len(vc)))
                ax.set_yticklabels([str(v) for v in vc.index], fontsize=8)
                ax.set_xlabel("Conteggio")

            elif t == "Grafico a bolle (bubble)":
                if y is None:
                    QMessageBox.warning(self,"Y","Seleziona colonna Y."); return
                sizes = pd.to_numeric(df[ycol], errors="coerce").fillna(1)
                sizes = (sizes-sizes.min())/(sizes.max()-sizes.min()+1e-9)*800+20
                ax.scatter(pd.to_numeric(x,errors="coerce"),
                           pd.to_numeric(y,errors="coerce"),
                           s=sizes.to_numpy(dtype=float), alpha=0.5, color="#4477AA")
                ax.set_xlabel(xcol); ax.set_ylabel(ycol)

            elif t == "Heatmap (pivot aggregato)":
                if y is None or hue == "(nessuna)":
                    QMessageBox.warning(self,"Selezione",
                        "Servono X, Y e Raggruppamento per la heatmap."); return
                pivot = df.pivot_table(index=hue, columns=xcol, values=ycol, aggfunc=cast(Any, agg))
                pivot_values = pivot.to_numpy(dtype=float)
                im = ax.imshow(pivot_values, cmap="YlOrRd", aspect="auto")
                ax.set_xticks(range(len(pivot.columns)))
                ax.set_xticklabels([str(v) for v in pivot.columns], rotation=45, ha="right", fontsize=7)
                ax.set_yticks(range(len(pivot.index)))
                ax.set_yticklabels([str(v) for v in pivot.index], fontsize=7)
                self.rpt_ch_fig.colorbar(im, ax=ax)

            elif t == "Pareto chart":
                vc = x.value_counts(dropna=False).head(20)
                vc_values = vc.to_numpy(dtype=float)
                cum_pct = vc_values.cumsum()/vc_values.sum()*100
                ax.bar(range(len(vc)), vc_values, color="#4477AA", edgecolor="white")
                ax2 = ax.twinx()
                ax2.plot(range(len(vc)), cum_pct, color="crimson", marker="o", ms=4, lw=1.5)
                ax2.axhline(80, color="orange", ls="--", lw=1)
                ax2.set_ylim(0, 110); ax2.set_ylabel("% cumulata")
                ax.set_xticks(range(len(vc)))
                ax.set_xticklabels([str(v) for v in vc.index], rotation=45, ha="right", fontsize=8)
                ax.set_ylabel("Frequenza")

            elif t == "Waterfall chart":
                if y is None:
                    QMessageBox.warning(self,"Y","Seleziona colonna Y (valori delta)."); return
                vals  = pd.to_numeric(y, errors="coerce").dropna().to_numpy(dtype=float)[:20]
                lbls  = x.dropna().astype(str).to_numpy()[:20]
                run = 0.0
                for idx,(lbl,v) in enumerate(zip(lbls,vals)):
                    ax.bar(idx, v, bottom=run, color="#4CAF50" if v>=0 else "#F44336",
                           edgecolor="white", width=0.6)
                    run += v
                ax.set_xticks(range(len(lbls)))
                ax.set_xticklabels(lbls, rotation=45, ha="right", fontsize=8)
                ax.axhline(0, color="black", lw=0.8); ax.set_ylabel(ycol)

            if logx:
                try: ax.set_xscale("log")
                except Exception: pass
            if logy:
                try: ax.set_yscale("log")
                except Exception: pass
            if grid: ax.grid(True, ls="--", lw=0.5, alpha=0.7)
            ax.set_title(title, fontsize=12, fontweight="bold")
            self.rpt_ch_fig.tight_layout(); self.rpt_ch_canvas.draw()
            self._set_status(f"Grafico «{title}» generato.")

        except Exception as exc:
            QMessageBox.critical(self, "Errore grafico", str(exc))

    def _rpt_ch_add_to_report(self) -> None:
        title = self.rpt_ch_title.text().strip() or self.rpt_ch_type.currentText()
        self._report_figures[title] = self.rpt_ch_fig
        self._set_status(f"«{title}» aggiunto al report.")
        QMessageBox.information(self, "Aggiunto", f"«{title}» pronto per l'esportazione.")

    def _rpt_ch_clear(self) -> None:
        self.rpt_ch_fig.clear(); self.rpt_ch_canvas.draw()

    # ── III · Statistiche Avanzate ───────────────────────────────────────────

    def _build_rpt_advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        ctrl = QGroupBox("Analisi avanzata")
        cl = QFormLayout(ctrl)

        self.rpt_adv_type = QComboBox()
        self.rpt_adv_type.addItems([
            "Matrice di correlazione (heatmap)",
            "Scatter matrix (pair-plot)",
            "PCA – componenti principali",
            "Distribuzione di probabilità (fitting)",
            "Q-Q plot (normalità)",
            "Test di Shapiro-Wilk",
            "Test di Mann-Whitney (2 gruppi)",
            "Test ANOVA a 1 fattore",
            "Test Chi-quadro (indipendenza)",
            "Decomposizione stagionale",
            "Autocorrelazione (ACF / PACF)",
            "Distribuzione empirica CDF",
            "Outlier multivariati (Mahalanobis)",
            "Curva di Lorenz / Gini",
            "Radar / Spider chart",
            "Funnel chart",
            "Pareto esteso (ABC)",
        ])
        self.rpt_adv_type.currentIndexChanged.connect(self._rpt_adv_update_desc)

        self.rpt_adv_x    = QComboBox(); self.rpt_adv_x.setMinimumWidth(150)
        self.rpt_adv_y    = QComboBox(); self.rpt_adv_y.setMinimumWidth(150)
        self.rpt_adv_grp  = QComboBox(); self.rpt_adv_grp.setMinimumWidth(130)
        self.rpt_adv_n    = QSpinBox();  self.rpt_adv_n.setRange(1,20); self.rpt_adv_n.setValue(2)
        self.rpt_adv_n.setPrefix("n componenti: ")
        self.rpt_adv_alpha= QDoubleSpinBox()
        self.rpt_adv_alpha.setRange(0.001,0.5); self.rpt_adv_alpha.setValue(0.05)
        self.rpt_adv_alpha.setSingleStep(0.01); self.rpt_adv_alpha.setPrefix("α = ")
        self.rpt_adv_dist = QComboBox()
        self.rpt_adv_dist.addItems(["norm","lognorm","expon","gamma","beta","uniform","t","chi2"])
        self.rpt_adv_desc = QLabel("")
        self.rpt_adv_desc.setWordWrap(True)
        self.rpt_adv_desc.setStyleSheet("color:#555;font-style:italic;")

        cl.addRow("Analisi:",        self.rpt_adv_type)
        cl.addRow("Descrizione:",    self.rpt_adv_desc)
        cl.addRow("Colonna X:",      self.rpt_adv_x)
        cl.addRow("Colonna Y:",      self.rpt_adv_y)
        cl.addRow("Raggruppamento:", self.rpt_adv_grp)
        cl.addRow("PCA n comp.:",    self.rpt_adv_n)
        cl.addRow("Distribuzione:",  self.rpt_adv_dist)
        cl.addRow("Soglia α:",       self.rpt_adv_alpha)

        btn_run = QPushButton("▶  Esegui"); btn_run.clicked.connect(self._rpt_adv_run)
        btn_add = QPushButton("➕  Aggiungi"); btn_add.clicked.connect(self._rpt_adv_add)
        bbar = QHBoxLayout(); bbar.addWidget(btn_run); bbar.addWidget(btn_add); bbar.addStretch()

        self.rpt_adv_result = QTextEdit()
        self.rpt_adv_result.setReadOnly(True); self.rpt_adv_result.setFont(QFont("Courier New",10))
        self.rpt_adv_result.setMaximumHeight(180)

        self.rpt_adv_fig = Figure(figsize=(8,5))
        self.rpt_adv_canvas = FigureCanvas(self.rpt_adv_fig)
        self.rpt_adv_canvas.setMinimumHeight(340)

        layout.addWidget(ctrl); layout.addLayout(bbar)
        layout.addWidget(QLabel("Risultati:")); layout.addWidget(self.rpt_adv_result)
        layout.addWidget(self.rpt_adv_canvas, stretch=1)
        self._rpt_adv_update_desc(0)
        return widget

    _ADV_DESCRIPTIONS = {
        "Matrice di correlazione (heatmap)":
            "Heatmap Pearson tra tutte le variabili numeriche.",
        "Scatter matrix (pair-plot)":
            "Griglia scatter per ogni coppia numerica (max 6).",
        "PCA – componenti principali":
            "Score plot + Scree plot con varianza spiegata.",
        "Distribuzione di probabilità (fitting)":
            "Fitta una distribuzione teorica (KS test).",
        "Q-Q plot (normalità)":
            "Quantili empirici vs teorici normali.",
        "Test di Shapiro-Wilk":
            "H₀: la variabile segue distribuzione normale.",
        "Test di Mann-Whitney (2 gruppi)":
            "Test non-parametrico per 2 gruppi indipendenti.",
        "Test ANOVA a 1 fattore":
            "Medie di 3+ gruppi significativamente diverse?",
        "Test Chi-quadro (indipendenza)":
            "Indipendenza tra due variabili categoriche.",
        "Decomposizione stagionale":
            "Trend + stagionalità + residuo (STL).",
        "Autocorrelazione (ACF / PACF)":
            "ACF e PACF per analisi serie temporali.",
        "Distribuzione empirica CDF":
            "ECDF empirica vs CDF teorica.",
        "Outlier multivariati (Mahalanobis)":
            "Distanza di Mahalanobis per outlier multivariati.",
        "Curva di Lorenz / Gini":
            "Concentrazione/disuguaglianza + coefficiente Gini.",
        "Radar / Spider chart":
            "Profilo multi-variabile su assi radiali.",
        "Funnel chart":
            "Riduzione progressiva (pipeline/conversioni).",
        "Pareto esteso (ABC)":
            "Analisi ABC: categorie A (80%), B (95%), C (100%).",
    }

    def _rpt_adv_update_desc(self, _=None) -> None:
        self.rpt_adv_desc.setText(self._ADV_DESCRIPTIONS.get(self.rpt_adv_type.currentText(),""))

    def _rpt_adv_run(self) -> None:  # pyright: ignore[reportGeneralTypeIssues]
        df = self.working_df
        if df.empty:
            QMessageBox.warning(self,"Dati mancanti","Nessun dataset caricato."); return
        cols_all = ["(nessuna)"] + list(df.columns)
        num_cols = df.select_dtypes(include="number").columns.tolist()
        for combo in [self.rpt_adv_x, self.rpt_adv_y, self.rpt_adv_grp]:
            cur=combo.currentText(); combo.blockSignals(True); combo.clear()
            combo.addItems(cols_all)
            if cur in cols_all: combo.setCurrentText(cur)
            combo.blockSignals(False)
        t    = self.rpt_adv_type.currentText()
        xcol = self.rpt_adv_x.currentText()
        ycol = self.rpt_adv_y.currentText()
        grp  = self.rpt_adv_grp.currentText()
        n_pc = self.rpt_adv_n.value()
        alpha= self.rpt_adv_alpha.value()
        dist = self.rpt_adv_dist.currentText()
        self.rpt_adv_fig.clear(); result_lines: List[str] = []
        try:
            if t == "Matrice di correlazione (heatmap)":
                cols = num_cols[:16]; corr = df[cols].corr()
                corr_values = corr.to_numpy(dtype=float)
                ax = self.rpt_adv_fig.add_subplot(111)
                im = ax.imshow(corr_values, cmap="RdBu_r", vmin=-1, vmax=1)
                n = len(cols)
                ax.set_xticks(range(n)); ax.set_xticklabels(cols,rotation=45,ha="right",fontsize=7)
                ax.set_yticks(range(n)); ax.set_yticklabels(cols,fontsize=7)
                for i in range(n):
                    for j in range(n):
                        ax.text(j,i,f"{corr_values[i,j]:.2f}",ha="center",va="center",fontsize=6)
                self.rpt_adv_fig.colorbar(im); ax.set_title("Matrice di correlazione (Pearson)")
                result_lines.append("Top correlazioni (|r|≥0.7):")
                for i,c1 in enumerate(cols):
                    for c2 in cols[i+1:]:
                        v=float(corr.at[c1,c2])
                        if abs(v)>=0.7: result_lines.append(f"  {c1} ↔ {c2}: r={v:.4f}")

            elif t == "Scatter matrix (pair-plot)":
                show=num_cols[:6]; n=len(show)
                if n<2: QMessageBox.warning(self,"Dati","Servono ≥2 colonne numeriche."); return
                axes=self.rpt_adv_fig.subplots(n,n)
                for i,ci in enumerate(show):
                    for j,cj in enumerate(show):
                        ax=axes[i][j]
                        if i==j: ax.hist(df[ci].dropna(),bins=15,color="#4477AA",alpha=0.7)
                        else: ax.scatter(df[cj],df[ci],alpha=0.3,s=6,color="#4477AA")
                        if i==n-1: ax.set_xlabel(cj,fontsize=7)
                        if j==0: ax.set_ylabel(ci,fontsize=7)
                        ax.tick_params(labelsize=6)
                self.rpt_adv_fig.suptitle("Scatter matrix",fontsize=11)

            elif t == "PCA – componenti principali":
                from sklearn.preprocessing import StandardScaler
                from sklearn.decomposition import PCA
                data=df[num_cols].dropna(); X=StandardScaler().fit_transform(data)
                n_comp=min(n_pc,X.shape[1],X.shape[0])
                pca=PCA(n_components=n_comp); scores=pca.fit_transform(X)
                var=pca.explained_variance_ratio_*100
                ax1,ax2=self.rpt_adv_fig.subplots(1,2)
                ax1.scatter(scores[:,0],scores[:,1] if n_comp>1 else np.zeros(len(scores)),
                            alpha=0.4,s=15,color="#4477AA")
                ax1.set_xlabel(f"PC1 ({var[0]:.1f}%)")
                ax1.set_ylabel(f"PC2 ({var[1]:.1f}%)" if n_comp>1 else "")
                ax1.set_title("Score plot PCA"); ax1.grid(True,ls="--",lw=0.5)
                ax2.bar(range(1,len(var)+1),var,color="#4477AA",edgecolor="white")
                ax2.plot(range(1,len(var)+1),np.cumsum(var),color="crimson",marker="o",ms=5)
                ax2.axhline(90,color="orange",ls="--",lw=1); ax2.set_title("Scree plot")
                result_lines+=[f"PC{i+1}: {v:.2f}%" for i,v in enumerate(var)]

            elif t == "Distribuzione di probabilità (fitting)":
                from scipy import stats as sp
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona X."); return
                vals=pd.to_numeric(df[xcol],errors="coerce").dropna().to_numpy(dtype=float)
                dist_fn=getattr(sp,dist); params=dist_fn.fit(vals)
                x_r=np.linspace(vals.min(),vals.max(),300)
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.hist(vals,bins=30,density=True,alpha=0.6,color="#4477AA",edgecolor="white",label="Empirica")
                ax.plot(x_r,dist_fn.pdf(x_r,*params),color="crimson",lw=2,label=f"{dist} fit")
                ax.set_title(f"Fitting {dist} — {xcol}"); ax.legend()
                ks,p=sp.kstest(vals,dist,params)
                result_lines+=[f"Params: {params}",f"KS stat={ks:.4f}  p={p:.4f}",
                               "H₀ OK" if p>alpha else "H₀ rifiutata"]

            elif t == "Q-Q plot (normalità)":
                from scipy import stats as sp
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona X."); return
                vals=pd.to_numeric(df[xcol],errors="coerce").dropna().to_numpy(dtype=float)
                ax=self.rpt_adv_fig.add_subplot(111)
                (osm,osr),(slope,intercept,r)=sp.probplot(vals,dist="norm")
                ax.plot(osm,osr,"o",ms=4,alpha=0.5,color="#4477AA")
                ax.plot(osm,slope*np.array(osm)+intercept,color="crimson",lw=2)
                ax.set_xlabel("Quantili teorici"); ax.set_ylabel("Quantili empirici")
                ax.set_title(f"Q-Q plot — {xcol}"); ax.grid(True,ls="--",lw=0.5)
                result_lines.append(f"r²={r**2:.4f}")

            elif t == "Test di Shapiro-Wilk":
                from scipy import stats as sp
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona X."); return
                vals=pd.to_numeric(df[xcol],errors="coerce").dropna().to_numpy(dtype=float)[:5000]
                stat,p=sp.shapiro(vals)
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.hist(vals,bins=30,density=True,alpha=0.6,color="#4477AA",edgecolor="white")
                from scipy.stats import norm
                x_r=np.linspace(vals.min(),vals.max(),300)
                ax.plot(x_r,norm.pdf(x_r,vals.mean(),vals.std()),color="crimson",lw=2)
                ax.set_title(f"Shapiro-Wilk — {xcol}")
                result_lines+=[f"W={stat:.6f}",f"p={p:.6f}",
                               "→ NORMALE" if p>alpha else "→ NON normale"]

            elif t == "Test di Mann-Whitney (2 gruppi)":
                from scipy import stats as sp
                if xcol=="(nessuna)" or grp=="(nessuna)":
                    QMessageBox.warning(self,"Selezione","Scegli X e Raggruppamento."); return
                groups=df[grp].dropna().unique()
                if len(groups)<2:
                    QMessageBox.warning(self,"Gruppi","Servono ≥2 gruppi."); return
                g1=pd.to_numeric(df.loc[df[grp]==groups[0],xcol],errors="coerce").dropna()
                g2=pd.to_numeric(df.loc[df[grp]==groups[1],xcol],errors="coerce").dropna()
                stat,p=sp.mannwhitneyu(g1,g2,alternative="two-sided")
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.boxplot([g1.to_numpy(dtype=float),g2.to_numpy(dtype=float)],
                           tick_labels=[str(groups[0]),str(groups[1])],
                           patch_artist=True,boxprops=dict(facecolor="#88AACC"),
                           medianprops=dict(color="crimson",lw=2))
                ax.set_title(f"Mann-Whitney: {xcol} per {grp}"); ax.set_ylabel(xcol)
                result_lines+=[f"n1={len(g1)} median={g1.median():.4g}",
                               f"n2={len(g2)} median={g2.median():.4g}",
                               f"U={stat:.4f}  p={p:.6f}",
                               "NON significativo" if p>alpha else "SIGNIFICATIVO"]

            elif t == "Test ANOVA a 1 fattore":
                from scipy import stats as sp
                if xcol=="(nessuna)" or grp=="(nessuna)":
                    QMessageBox.warning(self,"Selezione","Scegli X e Raggruppamento."); return
                groups=df[grp].dropna().unique()
                samples=[pd.to_numeric(df.loc[df[grp]==g,xcol],errors="coerce").dropna().to_numpy(dtype=float)
                         for g in groups]
                stat,p=sp.f_oneway(*samples)
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.boxplot(samples,tick_labels=[str(g) for g in groups],patch_artist=True)
                ax.set_xticklabels([str(g) for g in groups],rotation=30,ha="right")
                ax.set_title(f"ANOVA: {xcol}~{grp}"); ax.set_ylabel(xcol)
                result_lines+=[f"F={stat:.4f}  p={p:.6f}",
                               "NON significativo" if p>alpha else "SIGNIFICATIVO"]

            elif t == "Test Chi-quadro (indipendenza)":
                from scipy import stats as sp
                if xcol=="(nessuna)" or ycol=="(nessuna)":
                    QMessageBox.warning(self,"Selezione","Scegli X e Y categorici."); return
                ct=pd.crosstab(df[xcol],df[ycol])
                chi2,p,dof,_=sp.chi2_contingency(ct)
                ax=self.rpt_adv_fig.add_subplot(111)
                ct_values = ct.to_numpy()
                im=ax.imshow(ct_values,cmap="Blues",aspect="auto")
                ax.set_xticks(range(len(ct.columns)))
                ax.set_xticklabels([str(v) for v in ct.columns],rotation=45,ha="right",fontsize=8)
                ax.set_yticks(range(len(ct.index))); ax.set_yticklabels([str(v) for v in ct.index],fontsize=8)
                for i in range(ct_values.shape[0]):
                    for j in range(ct_values.shape[1]):
                        ax.text(j,i,str(ct_values[i,j]),ha="center",va="center",fontsize=8)
                self.rpt_adv_fig.colorbar(im)
                ax.set_title(f"Contingenza {xcol}×{ycol}")
                result_lines+=[f"χ²={chi2:.4f}  p={p:.6f}  dof={dof}",
                               "INDIPENDENTI" if p>alpha else "DIPENDENTI"]

            elif t == "Decomposizione stagionale":
                from statsmodels.tsa.seasonal import seasonal_decompose
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona la serie."); return
                series=pd.to_numeric(df[xcol],errors="coerce").dropna()
                period=max(2,len(series)//10)
                result=seasonal_decompose(series,model="additive",period=period)
                axes=self.rpt_adv_fig.subplots(4,1,sharex=True)
                for ax_s,data_s,lbl in zip(axes,
                    [result.observed,result.trend,result.seasonal,result.resid],
                    ["Osservata","Trend","Stagionalità","Residuo"]):
                    ax_s.plot(data_s,lw=1.2,color="#4477AA")
                    ax_s.set_ylabel(lbl,fontsize=8); ax_s.grid(True,ls="--",lw=0.4)
                self.rpt_adv_fig.suptitle(f"Decomposizione — {xcol} (p={period})")

            elif t == "Autocorrelazione (ACF / PACF)":
                from statsmodels.graphics.tsaplots import plot_acf,plot_pacf
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona la serie."); return
                series=pd.to_numeric(df[xcol],errors="coerce").dropna()
                lags=min(40,len(series)//2-1)
                ax1,ax2=self.rpt_adv_fig.subplots(2,1)
                plot_acf(series,lags=lags,ax=ax1,title="ACF")
                plot_pacf(series,lags=lags,ax=ax2,title="PACF",method="ywm")

            elif t == "Distribuzione empirica CDF":
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona X."); return
                from scipy import stats as sp
                vals=pd.to_numeric(df[xcol],errors="coerce").dropna().sort_values().to_numpy(dtype=float)
                ecdf=np.arange(1,len(vals)+1)/len(vals)
                dist_fn=getattr(sp,dist); params=dist_fn.fit(vals)
                x_r=np.linspace(vals.min(),vals.max(),300)
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.step(vals,ecdf,where="post",color="#4477AA",lw=1.5,label="ECDF")
                ax.plot(x_r,dist_fn.cdf(x_r,*params),color="crimson",lw=1.5,ls="--",label=f"CDF {dist}")
                ax.set_title(f"CDF empirica vs teorica — {xcol}"); ax.legend(); ax.grid(True,ls="--",lw=0.4)

            elif t == "Outlier multivariati (Mahalanobis)":
                cols_mv=num_cols[:10]; data=df[cols_mv].dropna()
                data_values = data.to_numpy(dtype=float)
                mu=data.mean().to_numpy(dtype=float); cov=np.cov(data_values.T)
                inv_cov=np.linalg.pinv(cov); diff=data_values-mu
                maha=np.sqrt(np.einsum("ij,jk,ik->i",diff,inv_cov,diff))
                thr=np.percentile(maha,97.5); n_out=int((maha>thr).sum())
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.scatter(range(len(maha)),maha,s=10,alpha=0.5,color="#4477AA")
                ax.axhline(thr,color="crimson",ls="--",label=f"Soglia 97.5% ({thr:.2f})")
                ax.scatter(np.where(maha>thr)[0],maha[maha>thr],color="red",s=20,zorder=5,label="Outlier")
                ax.set_title("Outlier multivariati (Mahalanobis)"); ax.legend(fontsize=8)
                result_lines+=[f"Outlier rilevati: {n_out} ({n_out/len(data)*100:.1f}%)"]

            elif t == "Curva di Lorenz / Gini":
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona X."); return
                vals=pd.to_numeric(df[xcol],errors="coerce").dropna().sort_values().to_numpy(dtype=float)
                vals=vals[vals>=0]
                cum_v=np.cumsum(vals)/vals.sum(); cum_p=np.arange(1,len(vals)+1)/len(vals)
                gini=1-2*np.trapz(cum_v,cum_p)
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.plot([0]+list(cum_p),[0]+list(cum_v),color="#4477AA",lw=2,label=f"Lorenz (Gini={gini:.3f})")
                ax.plot([0,1],[0,1],color="gray",ls="--",lw=1)
                ax.fill_between([0]+list(cum_p),[0]+list(cum_v),[0]+list(cum_p),alpha=0.2,color="#4477AA")
                ax.set_title(f"Lorenz / Gini — {xcol}"); ax.legend(); ax.grid(True,ls="--",lw=0.4)
                result_lines.append(f"Gini: {gini:.4f}")

            elif t == "Radar / Spider chart":
                cols_r=[c for c in num_cols[:8]]
                if len(cols_r)<3: QMessageBox.warning(self,"Variabili","Servono ≥3 numeriche."); return
                means=df[cols_r].mean().to_numpy(dtype=float)
                rng=means.max()-means.min()
                vals_n=(means-means.min())/(rng+1e-9)
                angles=np.linspace(0,2*np.pi,len(cols_r),endpoint=False).tolist()
                vals_n=np.concatenate([vals_n,[vals_n[0]]]); angles+=angles[:1]
                ax=self.rpt_adv_fig.add_subplot(111,polar=True)
                ax.plot(angles,vals_n,color="#4477AA",lw=2)
                ax.fill(angles,vals_n,color="#4477AA",alpha=0.25)
                ax.set_xticks(angles[:-1]); ax.set_xticklabels(cols_r,fontsize=8)
                ax.set_title("Radar chart (medie normalizzate)")

            elif t == "Funnel chart":
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona X categorica."); return
                vc=df[xcol].value_counts(dropna=False).head(10).sort_values(ascending=False)
                labels=[str(v) for v in vc.index]; values=vc.to_numpy(dtype=float)
                ax=self.rpt_adv_fig.add_subplot(111)
                for i,(lbl,val) in enumerate(zip(labels,values)):
                    w=val/values[0]
                    ax.barh(i,w,color=plt.get_cmap("Blues")(0.3+0.6*w),height=0.6,edgecolor="white")
                    ax.text(w/2,i,f"{lbl}: {val:,}",ha="center",va="center",fontsize=8,
                            color="white" if w>0.4 else "black")
                ax.set_yticks([]); ax.set_xlabel("Proporzione")
                ax.set_title(f"Funnel — {xcol}"); ax.invert_yaxis()

            elif t == "Pareto esteso (ABC)":
                if xcol=="(nessuna)": QMessageBox.warning(self,"X","Seleziona X."); return
                vc=df[xcol].value_counts(dropna=False).sort_values(ascending=False)
                vc_values = vc.to_numpy(dtype=float)
                cum=vc_values.cumsum()/vc_values.sum()*100
                colors=["#4CAF50" if c<=80 else "#FF9800" if c<=95 else "#F44336" for c in cum]
                ax=self.rpt_adv_fig.add_subplot(111)
                ax.bar(range(len(vc)),vc_values,color=colors,edgecolor="white")
                ax2=ax.twinx()
                ax2.plot(range(len(vc)),cum,color="#333",marker="o",ms=3,lw=1.5)
                for thr,lbl in [(80,"A (80%)"),(95,"B (95%)")]:
                    ax2.axhline(thr,color="gray",ls="--",lw=0.8,label=lbl)
                ax2.set_ylim(0,110); ax2.legend(fontsize=8)
                ax.set_xticks(range(len(vc)))
                ax.set_xticklabels([str(v) for v in vc.index],rotation=45,ha="right",fontsize=7)
                ax.set_title(f"Pareto esteso ABC — {xcol}")

            else:
                result_lines.append(f"«{t}» in implementazione.")

            self.rpt_adv_fig.tight_layout(); self.rpt_adv_canvas.draw()
            self.rpt_adv_result.setPlainText("\n".join(result_lines) or "—")
            self._set_status(f"Analisi avanzata «{t}» completata.")

        except ImportError as exc:
            QMessageBox.warning(self,"Libreria mancante",
                f"Installa: pip install scipy scikit-learn statsmodels\n\n{exc}")
        except Exception as exc:
            QMessageBox.critical(self,"Errore",str(exc))

    def _rpt_adv_add(self) -> None:
        t = self.rpt_adv_type.currentText()
        self._report_figures[f"Avanzata – {t}"] = self.rpt_adv_fig
        QMessageBox.information(self,"Aggiunto",f"«{t}» aggiunto al report.")

    # ── IV · Previsioni & Probabilità ────────────────────────────────────────

    def _build_rpt_forecast_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        ctrl = QGroupBox("Configurazione previsione")
        cl = QFormLayout(ctrl)

        self.rpt_fc_type = QComboBox()
        self.rpt_fc_type.addItems([
            "Regressione lineare semplice (con IC)",
            "Regressione polinomiale",
            "Media mobile (SMA/EMA)",
            "Smoothing esponenziale (ETS)",
            "Previsione naive / seasonal naive",
            "ARIMA (auto-order)",
            "Decomposizione + proiezione trend",
            "Monte Carlo (fan chart percentili)",
            "Bootstrap (bande di predizione)",
            "Value at Risk (VaR) e CVaR",
            "Intervalli di predizione (regressione)",
            "Crescita esponenziale / logistica",
        ])
        self.rpt_fc_type.currentIndexChanged.connect(self._rpt_fc_update_desc)

        self.rpt_fc_x      = QComboBox(); self.rpt_fc_x.setMinimumWidth(150)
        self.rpt_fc_y      = QComboBox(); self.rpt_fc_y.setMinimumWidth(150)
        self.rpt_fc_h      = QSpinBox(); self.rpt_fc_h.setRange(1,500); self.rpt_fc_h.setValue(10)
        self.rpt_fc_h.setPrefix("Periodi: ")
        self.rpt_fc_degree = QSpinBox(); self.rpt_fc_degree.setRange(1,8); self.rpt_fc_degree.setValue(2)
        self.rpt_fc_degree.setPrefix("Grado poly: ")
        self.rpt_fc_ci     = QDoubleSpinBox(); self.rpt_fc_ci.setRange(0.5,0.999); self.rpt_fc_ci.setValue(0.95)
        self.rpt_fc_ci.setSingleStep(0.01); self.rpt_fc_ci.setPrefix("IC: ")
        self.rpt_fc_nsim   = QSpinBox(); self.rpt_fc_nsim.setRange(100,10000); self.rpt_fc_nsim.setValue(1000)
        self.rpt_fc_nsim.setPrefix("Sim: ")
        self.rpt_fc_var    = QDoubleSpinBox(); self.rpt_fc_var.setRange(0.01,0.99); self.rpt_fc_var.setValue(0.05)
        self.rpt_fc_var.setPrefix("VaR α: ")
        self.rpt_fc_window = QSpinBox(); self.rpt_fc_window.setRange(2,200); self.rpt_fc_window.setValue(7)
        self.rpt_fc_window.setPrefix("Finestra MA: ")
        self.rpt_fc_desc = QLabel(""); self.rpt_fc_desc.setWordWrap(True)
        self.rpt_fc_desc.setStyleSheet("color:#555;font-style:italic;")

        cl.addRow("Metodo:", self.rpt_fc_type)
        cl.addRow("Descrizione:", self.rpt_fc_desc)
        cl.addRow("Colonna X:", self.rpt_fc_x)
        cl.addRow("Colonna Y (target):", self.rpt_fc_y)
        cl.addRow("Orizzonte:", self.rpt_fc_h)
        cl.addRow("Grado polinomiale:", self.rpt_fc_degree)
        cl.addRow("Livello IC:", self.rpt_fc_ci)
        cl.addRow("N° simulazioni:", self.rpt_fc_nsim)
        cl.addRow("VaR α:", self.rpt_fc_var)
        cl.addRow("Finestra MA:", self.rpt_fc_window)

        btn_run = QPushButton("▶  Esegui"); btn_run.clicked.connect(self._rpt_fc_run)
        btn_add = QPushButton("➕  Aggiungi"); btn_add.clicked.connect(self._rpt_fc_add)
        bbar = QHBoxLayout(); bbar.addWidget(btn_run); bbar.addWidget(btn_add); bbar.addStretch()

        self.rpt_fc_result = QTextEdit()
        self.rpt_fc_result.setReadOnly(True); self.rpt_fc_result.setFont(QFont("Courier New",10))
        self.rpt_fc_result.setMaximumHeight(160)

        self.rpt_fc_fig = Figure(figsize=(8,5))
        self.rpt_fc_canvas = FigureCanvas(self.rpt_fc_fig)
        self.rpt_fc_canvas.setMinimumHeight(340)

        layout.addWidget(ctrl); layout.addLayout(bbar)
        layout.addWidget(QLabel("Risultati:")); layout.addWidget(self.rpt_fc_result)
        layout.addWidget(self.rpt_fc_canvas, stretch=1)
        self._rpt_fc_update_desc(0)
        return widget

    _FC_DESCRIPTIONS = {
        "Regressione lineare semplice (con IC)":   "y=ax+b con banda di confidenza proiettata in avanti.",
        "Regressione polinomiale":                 "Curva polinomiale di grado n con proiezione.",
        "Media mobile (SMA/EMA)":                  "SMA ed EMA con proiezione piatta finale.",
        "Smoothing esponenziale (ETS)":             "Holt-Winters con trend e stagionalità (statsmodels).",
        "Previsione naive / seasonal naive":        "Baseline: naive=ultimo valore; seasonal=periodo precedente.",
        "ARIMA (auto-order)":                       "ARIMA con ricerca AIC automatica (statsmodels).",
        "Decomposizione + proiezione trend":        "Estrae il trend lineare e lo proietta avanti.",
        "Monte Carlo (fan chart percentili)":       "N percorsi gaussiani; fan chart p05/p25/p50/p75/p95.",
        "Bootstrap (bande di predizione)":          "Ricampiona residui per PI non-parametrici.",
        "Value at Risk (VaR) e CVaR":               "VaR α-percentile e CVaR sui rendimenti.",
        "Intervalli di predizione (regressione)":   "Banda di predizione individuale (più larga degli IC).",
        "Crescita esponenziale / logistica":         "Fit y=a·e^(bx) e curva logistica con proiezione.",
    }

    def _rpt_fc_update_desc(self, _=None) -> None:
        self.rpt_fc_desc.setText(self._FC_DESCRIPTIONS.get(self.rpt_fc_type.currentText(),""))

    def _rpt_fc_run(self) -> None:
        df = self.working_df
        if df.empty:
            QMessageBox.warning(self,"Dati mancanti","Nessun dataset."); return
        cols_all=["(nessuna)"]+list(df.columns)
        for combo in [self.rpt_fc_x, self.rpt_fc_y]:
            cur=combo.currentText(); combo.blockSignals(True); combo.clear()
            combo.addItems(cols_all)
            if cur in cols_all: combo.setCurrentText(cur)
            combo.blockSignals(False)
        t      = self.rpt_fc_type.currentText()
        xcol   = self.rpt_fc_x.currentText()
        ycol   = self.rpt_fc_y.currentText()
        h      = self.rpt_fc_h.value()
        degree = self.rpt_fc_degree.value()
        ci_lvl = self.rpt_fc_ci.value()
        n_sim  = self.rpt_fc_nsim.value()
        var_a  = self.rpt_fc_var.value()
        window = self.rpt_fc_window.value()
        self.rpt_fc_fig.clear(); result_lines: List[str] = []

        def _ser(col: str) -> np.ndarray:
            return pd.to_numeric(df[col],errors="coerce").dropna().to_numpy(dtype=float)

        try:
            if t == "Regressione lineare semplice (con IC)":
                if ycol=="(nessuna)": QMessageBox.warning(self,"Y","Seleziona Y."); return
                y=_ser(ycol); x=np.arange(len(y),dtype=float); xf=np.arange(len(y),len(y)+h,dtype=float)
                c=np.polyfit(x,y,1); yfit=np.polyval(c,x); resid=y-yfit
                s=np.std(resid,ddof=2)
                from scipy.stats import t as td
                tc=td.ppf((1+ci_lvl)/2,df=len(y)-2)
                xa=np.concatenate([x,xf]); xm=x.mean()
                se=s*np.sqrt(1/len(y)+(xa-xm)**2/np.sum((x-xm)**2))
                ya=np.polyval(c,xa)
                ax=self.rpt_fc_fig.add_subplot(111)
                ax.plot(x,y,"o",ms=4,alpha=0.5,color="#4477AA",label="Storico")
                ax.plot(x,yfit,color="#4477AA",lw=1.5)
                ax.plot(xf,np.polyval(c,xf),color="crimson",lw=2,ls="--",label=f"Prev (h={h})")
                ax.fill_between(xa,ya-tc*se,ya+tc*se,alpha=0.2,color="crimson",label=f"IC {int(ci_lvl*100)}%")
                ax.axvline(len(y)-1,color="gray",ls=":",lw=1); ax.legend(fontsize=8)
                ax.set_title(f"Regressione lineare — {ycol}"); ax.grid(True,ls="--",lw=0.4)
                result_lines+=[f"a={c[0]:.6g}  b={c[1]:.6g}",
                               f"RMSE={np.sqrt(np.mean(resid**2)):.4g}",
                               f"t+{h}: {np.polyval(c,xf[-1]):.4g}"]

            elif t == "Regressione polinomiale":
                if ycol=="(nessuna)": QMessageBox.warning(self,"Y","Seleziona Y."); return
                y=_ser(ycol); x=np.arange(len(y),dtype=float); xf=np.arange(len(y),len(y)+h,dtype=float)
                c=np.polyfit(x,y,degree)
                xs=np.linspace(x[0],xf[-1],400)
                ax=self.rpt_fc_fig.add_subplot(111)
                ax.plot(x,y,"o",ms=4,alpha=0.5,color="#4477AA",label="Storico")
                ax.plot(xs,np.polyval(c,xs),color="crimson",lw=1.5,label=f"Poly grado {degree}")
                ax.axvline(len(y)-1,color="gray",ls=":",lw=1); ax.legend(fontsize=8)
                ax.set_title(f"Poly grado {degree} — {ycol}"); ax.grid(True,ls="--",lw=0.4)
                result_lines.append(f"t+{h}: {np.polyval(c,xf[-1]):.4g}")

            elif t == "Media mobile (SMA/EMA)":
                if ycol=="(nessuna)": QMessageBox.warning(self,"Y","Seleziona Y."); return
                ys=pd.to_numeric(df[ycol],errors="coerce").dropna()
                if ys.empty:
                    QMessageBox.warning(self,"Dati non validi",f"La colonna «{ycol}» non contiene valori numerici."); return
                effective_window = min(window, len(ys))
                sma=ys.rolling(effective_window, min_periods=1).mean()
                ema=ys.ewm(span=effective_window,adjust=False).mean()
                ax=self.rpt_fc_fig.add_subplot(111)
                y_values=ys.to_numpy(dtype=float)
                sma_values=sma.to_numpy(dtype=float)
                ema_values=ema.to_numpy(dtype=float)
                ax.plot(y_values,alpha=0.5,color="#4477AA",lw=1,label="Originale")
                ax.plot(sma_values,color="crimson",lw=1.5,label=f"SMA({effective_window})")
                ax.plot(ema_values,color="#22AA44",lw=1.5,label=f"EMA({effective_window})")
                last=ema.iloc[-1]
                ax.plot(range(len(ys),len(ys)+h),[last]*h,color="#22AA44",lw=1.5,ls="--")
                ax.legend(fontsize=8); ax.set_title(f"SMA/EMA — {ycol}"); ax.grid(True,ls="--",lw=0.4)
                result_lines+=[f"SMA={sma.iloc[-1]:.4g}",f"EMA={last:.4g}",f"Prev EMA t+{h}: {last:.4g}"]

            elif t == "Monte Carlo (fan chart percentili)":
                if ycol=="(nessuna)": QMessageBox.warning(self,"Y","Seleziona Y."); return
                y=_ser(ycol); ret=np.diff(y)/(y[:-1]+1e-12)
                mu_r,sig_r=ret.mean(),ret.std(); last=y[-1]
                rng=np.random.default_rng(42)
                paths=np.zeros((n_sim,h))
                for s in range(n_sim):
                    v=last
                    for step in range(h):
                        v=v*(1+rng.normal(mu_r,sig_r)); paths[s,step]=v
                qnt=np.percentile(paths,[5,25,50,75,95],axis=0)
                xf=np.arange(len(y),len(y)+h)
                ax=self.rpt_fc_fig.add_subplot(111)
                ax.plot(y,color="#4477AA",lw=1.5,label="Storico")
                ax.fill_between(xf,qnt[0],qnt[4],alpha=0.15,color="crimson",label="5-95%")
                ax.fill_between(xf,qnt[1],qnt[3],alpha=0.3,color="crimson",label="25-75%")
                ax.plot(xf,qnt[2],color="crimson",lw=2,ls="--",label="Mediana")
                ax.axvline(len(y)-1,color="gray",ls=":",lw=1)
                ax.legend(fontsize=8); ax.set_title(f"Monte Carlo ({n_sim} sim.) — {ycol}")
                ax.grid(True,ls="--",lw=0.4)
                result_lines+=[f"μ ret={mu_r:.4f}  σ={sig_r:.4f}",
                               f"t+{h} p50={qnt[2,-1]:.4g}  p05={qnt[0,-1]:.4g}  p95={qnt[4,-1]:.4g}"]

            elif t == "Value at Risk (VaR) e CVaR":
                if ycol=="(nessuna)": QMessageBox.warning(self,"Y","Seleziona Y."); return
                y=_ser(ycol); ret=np.diff(y)/(y[:-1]+1e-12)
                var_v=np.percentile(ret,var_a*100); cvar_v=ret[ret<=var_v].mean()
                ax=self.rpt_fc_fig.add_subplot(111)
                ax.hist(ret,bins=50,density=True,alpha=0.6,color="#4477AA",edgecolor="white")
                ax.axvline(var_v,color="crimson",lw=2,label=f"VaR {int(var_a*100)}%={var_v:.4f}")
                ax.axvline(cvar_v,color="darkred",lw=2,ls="--",label=f"CVaR={cvar_v:.4f}")
                ax.set_title(f"VaR & CVaR — {ycol}"); ax.legend(fontsize=8); ax.grid(True,ls="--",lw=0.4)
                result_lines+=[f"VaR={var_v:.6f}",f"CVaR={cvar_v:.6f}",
                               f"μ ret={ret.mean():.6f}",f"σ={ret.std():.6f}"]

            elif t == "Bootstrap (bande di predizione)":
                if ycol=="(nessuna)": QMessageBox.warning(self,"Y","Seleziona Y."); return
                y=_ser(ycol); x=np.arange(len(y),dtype=float)
                c=np.polyfit(x,y,1); resid=y-np.polyval(c,x)
                xf=np.arange(len(y),len(y)+h,dtype=float)
                rng=np.random.default_rng(42)
                bp=np.zeros((n_sim,h))
                for s in range(n_sim):
                    bp[s]=np.polyval(c,xf)+rng.choice(resid,size=h,replace=True)
                lo=np.percentile(bp,(1-ci_lvl)/2*100,axis=0)
                hi=np.percentile(bp,(1+ci_lvl)/2*100,axis=0)
                mid=np.percentile(bp,50,axis=0)
                lo=np.asarray(lo,dtype=float); hi=np.asarray(hi,dtype=float)
                mid=np.asarray(mid,dtype=float); xf=np.asarray(xf,dtype=float)
                ax=self.rpt_fc_fig.add_subplot(111)
                ax.plot(x,y,"o",ms=3,alpha=0.5,color="#4477AA",label="Storico")
                ax.plot(x,np.polyval(c,x),color="#4477AA",lw=1.5)
                ax.plot(xf,mid,color="crimson",lw=2,ls="--",label="Mediana Bootstrap")
                ax.fill_between(xf.tolist(),lo.tolist(),hi.tolist(),alpha=0.25,color="crimson",label=f"PI {int(ci_lvl*100)}%")
                ax.axvline(len(y)-1,color="gray",ls=":",lw=1)
                ax.legend(fontsize=8); ax.set_title(f"Bootstrap PI — {ycol}"); ax.grid(True,ls="--",lw=0.4)
                result_lines+=[f"Sim={n_sim}",f"t+{h}: [{lo[-1]:.4g}, {hi[-1]:.4g}]"]

            elif t == "Crescita esponenziale / logistica":
                if ycol=="(nessuna)": QMessageBox.warning(self,"Y","Seleziona Y."); return
                from scipy.optimize import curve_fit
                y=_ser(ycol); x=np.arange(len(y),dtype=float); xf=np.arange(len(y),len(y)+h,dtype=float)
                xa=np.concatenate([x,xf])
                ax=self.rpt_fc_fig.add_subplot(111)
                ax.plot(x,y,"o",ms=4,alpha=0.5,color="#4477AA",label="Storico")
                ax.axvline(len(y)-1,color="gray",ls=":",lw=1)
                def exp_fn(x,a,b): return a*np.exp(b*x)
                def log_fn(x,L,k,x0): return L/(1+np.exp(-k*(x-x0)))
                try:
                    po,_=curve_fit(exp_fn,x,y,p0=[y[0],0.01],maxfev=5000)
                    ax.plot(xa,exp_fn(xa,*po),color="crimson",lw=1.5,
                            label=f"Exp: a={po[0]:.3g}, b={po[1]:.4f}")
                    result_lines.append(f"Exp t+{h}: {exp_fn(xf[-1],*po):.4g}")
                except Exception as e:
                    result_lines.append(f"Exp fallito: {e}")
                try:
                    po,_=curve_fit(log_fn,x,y,p0=[y.max()*2,0.1,len(y)/2],maxfev=5000)
                    ax.plot(xa,log_fn(xa,*po),color="#22AA44",lw=1.5,ls="--",
                            label=f"Logistica L={po[0]:.3g}")
                    result_lines.append(f"Log t+{h}: {log_fn(xf[-1],*po):.4g}")
                except Exception as e:
                    result_lines.append(f"Log fallita: {e}")
                ax.legend(fontsize=8); ax.set_title(f"Crescita — {ycol}"); ax.grid(True,ls="--",lw=0.4)

            else:
                result_lines.append(f"«{t}» in implementazione avanzata.")

            self.rpt_fc_fig.tight_layout(); self.rpt_fc_canvas.draw()
            self.rpt_fc_result.setPlainText("\n".join(result_lines) or "—")
            self._set_status(f"Previsione «{t}» completata.")

        except ImportError as exc:
            QMessageBox.warning(self,"Libreria mancante",
                f"Installa: pip install scipy statsmodels\n\n{exc}")
        except Exception as exc:
            QMessageBox.critical(self,"Errore previsione",str(exc))

    def _rpt_fc_add(self) -> None:
        t = self.rpt_fc_type.currentText()
        self._report_figures[f"Previsione – {t}"] = self.rpt_fc_fig
        QMessageBox.information(self,"Aggiunto",f"«{t}» aggiunto al report.")

    # ── Esportazione ─────────────────────────────────────────────────────────

    def _rpt_export(self, fmt: str) -> None:
        if not self._report_figures and fmt not in {"csv","xlsx"}:
            QMessageBox.warning(self,"Report vuoto",
                "Genera grafici e usa «Aggiungi» prima di esportare."); return
        title  = self.rpt_title_edit.text().strip() or "HealthReport Studio"
        author = self.rpt_author_edit.text().strip()
        dpi    = self.rpt_dpi_spin.value()
        paper  = self.rpt_paper_combo.currentText()

        if fmt == "pdf":
            path,_=QFileDialog.getSaveFileName(self,"Esporta PDF",f"{title}.pdf","PDF (*.pdf)")
            if not path: return
            try:
                from matplotlib.backends.backend_pdf import PdfPages
                import datetime
                with PdfPages(path) as pp:
                    fig_c=plt.figure(figsize=(8.27,11.69) if paper=="A4" else (11.69,16.54) if paper=="A3" else (8.5,11))
                    fig_c.text(0.5,0.65,title,ha="center",va="center",fontsize=22,fontweight="bold")
                    if author: fig_c.text(0.5,0.55,f"Autore: {author}",ha="center",va="center",fontsize=14)
                    fig_c.text(0.5,0.45,datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                               ha="center",va="center",fontsize=11,color="gray")
                    pp.savefig(fig_c,dpi=dpi); plt.close(fig_c)
                    for _,fig in self._report_figures.items():
                        pp.savefig(fig,dpi=dpi,bbox_inches="tight")
                    d=pp.infodict(); d["Title"]=title; d["Author"]=author
                QMessageBox.information(self,"PDF","Salvato:\n"+path)
            except Exception as exc:
                QMessageBox.critical(self,"Errore PDF",str(exc))

        elif fmt == "xlsx":
            path,_=QFileDialog.getSaveFileName(self,"Esporta Excel",f"{title}.xlsx","Excel (*.xlsx)")
            if not path: return
            try:
                with pd.ExcelWriter(path,engine="openpyxl") as w:
                    if not self.working_df.empty:
                        self.working_df.to_excel(w,sheet_name="Dataset",index=False)
                    num_df=self.working_df.select_dtypes(include="number")
                    if not num_df.empty:
                        num_df.describe(percentiles=[.05,.25,.5,.75,.95]).to_excel(
                            w,sheet_name="Statistiche")
                    txt=self.rpt_ov_text.toPlainText()
                    if txt:
                        pd.DataFrame({"Profilazione":txt.splitlines()}).to_excel(
                            w,sheet_name="Profilazione",index=False)
                QMessageBox.information(self,"Excel","Salvato:\n"+path)
            except Exception as exc:
                QMessageBox.critical(self,"Errore Excel",str(exc))

        elif fmt == "html":
            path,_=QFileDialog.getSaveFileName(self,"Esporta HTML",f"{title}.html","HTML (*.html)")
            if not path: return
            try:
                import base64, datetime
                parts=[
                    f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>",
                    "<style>body{font-family:sans-serif;max-width:1100px;margin:auto;padding:20px}",
                    "h1{color:#2244AA}h2{color:#336699}img{max-width:100%;margin:12px 0}",
                    "pre{background:#f5f5f5;padding:12px;border-radius:6px;font-size:12px}</style></head><body>",
                    f"<h1>{title}</h1>",
                    f"<p><b>Autore:</b> {author or '—'} | <b>Data:</b> {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>",
                ]
                txt=self.rpt_ov_text.toPlainText()
                if txt: parts+=[f"<h2>Profilazione</h2><pre>{txt}</pre>"]
                for name,fig in self._report_figures.items():
                    buf=BytesIO(); fig.savefig(buf,format="png",dpi=dpi,bbox_inches="tight")
                    b64=base64.b64encode(buf.getvalue()).decode()
                    parts+=[f"<h2>{name}</h2>",f"<img src='data:image/png;base64,{b64}' alt='{name}'>"]
                if not self.working_df.empty:
                    parts+=[f"<h2>Dataset (prime 100 righe)</h2>",
                            self.working_df.head(100).to_html(index=False,border=1)]
                parts.append("</body></html>")
                Path(path).write_text("\n".join(parts),encoding="utf-8")
                QMessageBox.information(self,"HTML","Salvato:\n"+path)
            except Exception as exc:
                QMessageBox.critical(self,"Errore HTML",str(exc))

        elif fmt == "png":
            folder=QFileDialog.getExistingDirectory(self,"Cartella PNG/SVG")
            if not folder: return
            try:
                for name,fig in self._report_figures.items():
                    safe="".join(c if c.isalnum() or c in " _-" else "_" for c in name)
                    for ext in ["png","svg"]:
                        fig.savefig(str(Path(folder)/f"{safe}.{ext}"),dpi=dpi,bbox_inches="tight")
                QMessageBox.information(self,"PNG/SVG",f"{len(self._report_figures)} grafici in:\n{folder}")
            except Exception as exc:
                QMessageBox.critical(self,"Errore PNG",str(exc))

        elif fmt == "csv":
            path,_=QFileDialog.getSaveFileName(self,"Esporta CSV",f"{title}_stats.csv","CSV (*.csv)")
            if not path: return
            try:
                self.working_df.select_dtypes(include="number").describe(
                    percentiles=[.05,.25,.5,.75,.95]).to_csv(path)
                QMessageBox.information(self,"CSV","Salvato:\n"+path)
            except Exception as exc:
                QMessageBox.critical(self,"Errore CSV",str(exc))

        elif fmt == "pptx":
            if not require_optional("python-pptx", reason="esportazione PowerPoint"):
                return
            path_p, _ = QFileDialog.getSaveFileName(
                self, "Esporta PPTX", f"{title}.pptx", "PowerPoint (*.pptx)")
            if not path_p: return
            try:
                import io as _io
                pptx_module = importlib.import_module("pptx")
                pptx_util = importlib.import_module("pptx.util")
                Presentation = getattr(pptx_module, "Presentation")
                Inches = getattr(pptx_util, "Inches")
                prs = Presentation()
                prs.slide_width  = Inches(13.33)
                prs.slide_height = Inches(7.5)
                sl0 = prs.slides.add_slide(prs.slide_layouts[0])
                sl0.shapes.title.text = title
                try: sl0.placeholders[1].text = author or ""
                except Exception: pass
                for fig_name, fig in self._report_figures.items():
                    buf = _io.BytesIO()
                    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
                    buf.seek(0)
                    sl = prs.slides.add_slide(prs.slide_layouts[6])
                    sl.shapes.add_picture(buf, Inches(0.3), Inches(0.6), width=Inches(12.5))
                    txb = sl.shapes.add_textbox(Inches(0.3), Inches(0.1), Inches(12), Inches(0.4))
                    txb.text_frame.text = fig_name
                prs.save(path_p)
                QMessageBox.information(self, "PPTX esportato", f"Salvato:\n{path_p}")
            except Exception as exc:
                QMessageBox.critical(self, "Errore PPTX", str(exc))
        elif fmt == "odt":
            if not require_optional("python-docx", reason="esportazione Word/ODT"):
                return
            path_o, _ = QFileDialog.getSaveFileName(
                self, "Esporta Word", f"{title}.docx", "Word (*.docx)")
            if not path_o: return
            try:
                import io as _io2
                docx_module = importlib.import_module("docx")
                docx_shared = importlib.import_module("docx.shared")
                Document = getattr(docx_module, "Document")
                Inches2 = getattr(docx_shared, "Inches")
                doc = Document()
                doc.add_heading(title, 0)
                if author: doc.add_paragraph(f"Autore: {author}")
                ov = self.rpt_ov_text.toPlainText()
                if ov:
                    doc.add_heading("Profilazione Dataset", 1)
                    doc.add_paragraph(ov)
                for fig_name, fig in self._report_figures.items():
                    doc.add_heading(fig_name, 2)
                    buf2 = _io2.BytesIO()
                    fig.savefig(buf2, format="png", dpi=dpi, bbox_inches="tight")
                    buf2.seek(0)
                    doc.add_picture(buf2, width=Inches2(6))
                doc.save(path_o)
                QMessageBox.information(self, "Word esportato", f"Salvato:\n{path_o}")
            except Exception as exc:
                QMessageBox.critical(self, "Errore Word", str(exc))


        # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 – ANALISI ML (placeholder)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ml_placeholder(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🤖")
        icon.setFont(QFont("Arial", 48))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Analisi ML — In sviluppo")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "Questa sezione conterrà:\n\n"
            "  •  Analisi di regressione  (lineare, multipla, polinomiale)\n"
            "  •  Classificazione  (Logistic Regression, Decision Tree, Random Forest)\n"
            "  •  Clustering  (K-Means, DBSCAN)\n"
            "  •  Serie temporali  (ARIMA, Prophet)\n"
            "  •  Valutazione modelli  (metriche, curve ROC, feature importance)\n\n"
            "I dati proverranno dal dataset elaborato nella tab «Data Query»."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#666; font-size:13px;")

        layout.addWidget(icon)
        layout.addSpacing(12)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(desc)
        return widget

    # ══════════════════════════════════════════════════════════════════════════
    # Utilità
    # ══════════════════════════════════════════════════════════════════════════

    def _set_status(self, msg: str) -> None:
        self.status.showMessage(msg, 8000)


# ══════════════════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _separator() -> QWidget:
    """Separatore verticale sottile per toolbar orizzontali."""
    sep = QWidget()
    sep.setFixedWidth(1)
    sep.setStyleSheet("background:#ccc;")
    return sep


def _wrap(layout) -> QWidget:
    """Avvolge un QLayout in un QWidget (per righe QFormLayout)."""
    w = QWidget()
    w.setLayout(layout)
    return w


def _make_table_view(model: PandasTableModel) -> QTableView:
    tv = QTableView()
    tv.setModel(model)
    tv.setAlternatingRowColors(True)
    tv.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    tv.horizontalHeader().setStretchLastSection(True)
    tv.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    tv.verticalHeader().setDefaultSectionSize(22)
    return tv


# ══════════════════════════════════════════════════════════════════════════════
# AVVIO
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

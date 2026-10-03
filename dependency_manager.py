"""
dependency_manager.py — HealthReport Studio
============================================

Gestione centralizzata delle dipendenze Python:

  • Avvio automatico: installa/verifica le librerie CORE da LIBRARIES.md
  • On-demand:        installa le librerie OPZIONALI (driver DB, export, ML)
                      quando l'utente tenta di usare una funzione che le richiede,
                      mostrando una finestra Qt di consenso prima di procedere.
  • Registro:         tiene traccia in ~/.healthreport_studio/installed_optional.json
                      delle librerie opzionali già installate per non ricontrollarle
                      ad ogni avvio.
  • Rollback:         in caso di errore durante l'installazione opzionale, ripristina
                      lo stato precedente segnalando il problema senza crashare l'app.

Uso dal codice applicativo:
    from dependency_manager import require_optional

    # Dentro un metodo che usa psycopg2:
    if not require_optional("psycopg2-binary", reason="connessioni PostgreSQL"):
        return   # utente ha rifiutato o installazione fallita

    import psycopg2   # ora è sicuro
    ...
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── Costanti ──────────────────────────────────────────────────────────────────

APP_DIR = Path.home() / ".healthreport_studio"
OPTIONAL_REGISTRY_PATH = APP_DIR / "installed_optional.json"

# Mappa pip-name → import-name (quando differiscono)
_IMPORT_NAME_MAP: Dict[str, str] = {
    "psycopg2-binary":           "psycopg2",
    "pymysql":                   "pymysql",
    "pyodbc":                    "pyodbc",
    "oracledb":                  "oracledb",
    "duckdb-engine":             "duckdb_engine",
    "ibm_db_sa":                 "ibm_db_sa",
    "ibm_db":                    "ibm_db",
    "sqlalchemy-redshift":       "redshift_sqlalchemy",
    "redshift-connector":        "redshift_connector",
    "PyAthena":                  "pyathena",
    "google-cloud-bigquery":     "google.cloud.bigquery",
    "sqlalchemy-bigquery":       "sqlalchemy_bigquery",
    "pg8000":                    "pg8000",
    "cloud-sql-python-connector":"google.cloud.sql.connector",
    "google-cloud-spanner":      "google.cloud.spanner",
    "sqlalchemy-spanner":        "sqlalchemy_spanner",
    "azure-cosmos":              "azure.cosmos",
    "snowflake-connector-python":"snowflake.connector",
    "snowflake-sqlalchemy":      "snowflake.sqlalchemy",
    "databricks-sql-connector":  "databricks.sql",
    "sqlalchemy-databricks":     "sqlalchemy_databricks",
    "pymongo":                   "pymongo",
    "influxdb-client":           "influxdb_client",
    "elasticsearch":             "elasticsearch",
    "eland":                     "eland",
    "clickhouse-driver":         "clickhouse",
    "sqlalchemy-clickhouse":     "clickhouse_sqlalchemy",
    "sqlalchemy-cockroachdb":    "cockroachdb",
    "boto3":                     "boto3",
    "python-pptx":               "pptx",
    "python-docx":               "docx",
    "pyarrow":                   "pyarrow",
    "scikit-learn":              "sklearn",
    "imbalanced-learn":          "imblearn",
    "statsmodels":               "statsmodels",
    "scipy":                     "scipy",
    "numpy":                     "numpy",
    "matplotlib":                "matplotlib",
    "openpyxl":                  "openpyxl",
    "sqlalchemy":                "sqlalchemy",
    "pandas":                    "pandas",
    "fdb":                       "fdb",
}

# Dipendenze di sistema per libreria (avviso informativo, non bloccante)
_SYSTEM_DEPS: Dict[str, Dict[str, str]] = {
    "pyodbc": {
        "linux":   "sudo apt install -y unixodbc-dev",
        "macos":   "brew install unixodbc",
        "windows": "Installa ODBC Driver 17 per SQL Server da Microsoft",
    },
    "oracledb": {
        "linux":   "Oracle Instant Client richiesto: https://oracle.com/database/technologies/instant-client",
        "macos":   "Oracle Instant Client richiesto: https://oracle.com/database/technologies/instant-client",
        "windows": "Oracle Instant Client richiesto: https://oracle.com/database/technologies/instant-client",
    },
    "ibm_db": {
        "linux":   "IBM DB2 client o ODBC richiesto",
        "macos":   "IBM DB2 client richiesto",
        "windows": "IBM DB2 client richiesto",
    },
}

# Thread lock per installazioni concorrenti
_install_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════════
# UTILITÀ AMBIENTE
# ══════════════════════════════════════════════════════════════════════════════

def detect_os() -> str:
    s = platform.system().lower()
    if s == "linux":   return "linux"
    if s == "windows": return "windows"
    if s == "darwin":  return "macos"
    return "unknown"


def get_local_venv_python() -> Optional[str]:
    """Cerca un venv locale nella cartella corrente e nelle sue varianti standard."""
    cwd = Path.cwd()
    candidates = [
        cwd / "venv"  / "bin"     / "python3",
        cwd / "venv"  / "bin"     / "python",
        cwd / ".venv" / "bin"     / "python3",
        cwd / ".venv" / "bin"     / "python",
        cwd / "env"   / "bin"     / "python3",
        cwd / "venv"  / "Scripts" / "python.exe",   # Windows
        cwd / ".venv" / "Scripts" / "python.exe",
    ]
    for p in candidates:
        if p.exists():
            r = subprocess.run([str(p), "-m", "pip", "--version"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                return str(p)
    return None


def get_python_executable() -> str:
    """Ritorna il path Python da usare, preferendo il venv locale."""
    if os.environ.get("VIRTUAL_ENV"):
        return sys.executable
    venv = get_local_venv_python()
    if venv:
        return venv
    return sys.executable


def _in_venv(python_executable: str) -> bool:
    return (
        bool(os.environ.get("VIRTUAL_ENV"))
        or "venv" in python_executable.lower()
        or ".venv" in python_executable.lower()
    )


def base_pip_command(python_executable: Optional[str] = None) -> List[str]:
    if python_executable is None:
        python_executable = get_python_executable()
    return [python_executable, "-m", "pip"]


# ══════════════════════════════════════════════════════════════════════════════
# LETTURA LIBRARIES.MD
# ══════════════════════════════════════════════════════════════════════════════

def read_libraries_from_markdown(markdown_path: str = "LIBRARIES.md") -> List[str]:
    """
    Legge la lista librerie da un file Markdown.
    Supporta righe con - o * come bullet. Ignora commenti (#) e righe vuote.
    """
    path = Path(markdown_path)
    if not path.exists():
        raise FileNotFoundError(
            f"File '{markdown_path}' non trovato. "
            "Crea LIBRARIES.md nella cartella del progetto."
        )
    libraries: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^[-*]\s+([A-Za-z0-9_.[\]>=<,!-]+)", line)
        if m:
            libraries.append(m.group(1))
    if not libraries:
        raise ValueError(
            f"Nessuna libreria trovata in '{markdown_path}'. "
            "Usa righe tipo:  - pandas"
        )
    return libraries


def read_optional_libraries_from_markdown(
    markdown_path: str = "LIBRARIES_OPTIONAL.md",
) -> Dict[str, str]:
    """
    Legge LIBRARIES_OPTIONAL.md e restituisce {pip_name: descrizione}.
    Le righe commentate con # nome → descrizione vengono parsate come:
      # nome_pacchetto   → testo descrizione
    Le righe con - nome vengono incluse senza descrizione.
    """
    path = Path(markdown_path)
    if not path.exists():
        return {}
    result: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        # Formato: # nome_pacchetto   → descrizione
        m = re.match(r"^#\s+([A-Za-z0-9_.-]+)\s+[→\-]+\s+(.+)$", line)
        if m:
            result[m.group(1)] = m.group(2).strip()
            continue
        # Formato bullet: - nome_pacchetto
        m2 = re.match(r"^[-*]\s+([A-Za-z0-9_.-]+)", line)
        if m2:
            result[m2.group(1)] = m2.group(1)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRO LIBRERIE OPZIONALI
# ══════════════════════════════════════════════════════════════════════════════

def _load_optional_registry() -> Dict[str, Dict]:
    """
    Carica il registro delle librerie opzionali installate.
    Struttura: {pip_name: {"installed": bool, "version": str, "timestamp": str}}
    """
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if OPTIONAL_REGISTRY_PATH.exists():
        try:
            return json.loads(OPTIONAL_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_optional_registry(registry: Dict[str, Dict]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    OPTIONAL_REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _mark_installed(pip_name: str, version: str = "") -> None:
    import datetime
    reg = _load_optional_registry()
    reg[pip_name] = {
        "installed":  True,
        "version":    version,
        "timestamp":  datetime.datetime.now().isoformat(timespec="seconds"),
        "python":     get_python_executable(),
    }
    _save_optional_registry(reg)


def _mark_failed(pip_name: str, error: str) -> None:
    import datetime
    reg = _load_optional_registry()
    reg[pip_name] = {
        "installed":  False,
        "error":      error,
        "timestamp":  datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _save_optional_registry(reg)


# ══════════════════════════════════════════════════════════════════════════════
# VERIFICA INSTALLAZIONE
# ══════════════════════════════════════════════════════════════════════════════

def _pip_name_to_import(pip_name: str) -> str:
    """Converte il nome pip nel nome del modulo da importare."""
    if pip_name in _IMPORT_NAME_MAP:
        return _IMPORT_NAME_MAP[pip_name]
    # Euristica: sostituisci - con _ e prendi la prima parte
    return pip_name.split("[")[0].replace("-", "_").split(">")[0].split("<")[0].strip()


def is_installed(pip_name: str,
                 python_executable: Optional[str] = None) -> bool:
    """Verifica se una libreria è importabile nell'interprete corrente."""
    if python_executable is None:
        python_executable = get_python_executable()
    import_name = _pip_name_to_import(pip_name)
    # Gestisce import annidati (es. google.cloud.bigquery)
    top_module = import_name.split(".")[0]
    r = subprocess.run(
        [python_executable, "-c", f"import {top_module}"],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def check_if_libraries_installed(
    libraries: List[str],
    python_executable: Optional[str] = None,
) -> List[str]:
    """Ritorna la lista delle librerie NON ancora installate."""
    if python_executable is None:
        python_executable = get_python_executable()
    return [lib for lib in libraries if not is_installed(lib, python_executable)]


# ══════════════════════════════════════════════════════════════════════════════
# INSTALLAZIONE
# ══════════════════════════════════════════════════════════════════════════════

def get_pip_install_command(
    libraries: List[str],
    os_name: str,
    python_executable: str,
    upgrade: bool = True,
) -> List[str]:
    """Costruisce il comando pip install adatto all'OS e all'ambiente."""
    cmd = [python_executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    if os_name in {"linux", "windows", "macos"}:
        cmd.append("--prefer-binary")
    if os_name == "linux" and not _in_venv(python_executable):
        cmd.append("--user")
    cmd += libraries
    return cmd


def install_libraries(
    libraries: List[str],
    os_name: str,
    python_executable: Optional[str] = None,
    upgrade: bool = False,
    timeout: int = 300,
) -> Tuple[int, str, str]:
    """
    Installa le librerie tramite pip.
    Ritorna (returncode, stdout, stderr).
    """
    if python_executable is None:
        python_executable = get_python_executable()
    cmd = get_pip_install_command(libraries, os_name, python_executable, upgrade)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def install_single_optional(
    pip_name: str,
    python_executable: Optional[str] = None,
    progress_callback=None,
) -> Tuple[bool, str]:
    """
    Installa una singola libreria opzionale.
    Ritorna (success, message).
    progress_callback(msg: str) viene chiamata con aggiornamenti di stato.
    """
    if python_executable is None:
        python_executable = get_python_executable()
    os_name = detect_os()

    def _progress(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)
        print(msg)

    _progress(f"  Installazione di '{pip_name}'...")

    # Avviso dipendenze di sistema
    base = pip_name.split("[")[0].replace("-", "_")
    if base in _SYSTEM_DEPS:
        hint = _SYSTEM_DEPS[base].get(os_name, "")
        if hint:
            _progress(f"  ⚠ Dipendenza di sistema richiesta: {hint}")

    try:
        rc, out, err = install_libraries(
            [pip_name], os_name, python_executable,
            upgrade=False, timeout=300,
        )
        if rc == 0:
            # Verifica che sia effettivamente importabile
            if is_installed(pip_name, python_executable):
                # Leggi versione installata
                rv = subprocess.run(
                    base_pip_command(python_executable) + ["show", pip_name],
                    capture_output=True, text=True,
                )
                version = ""
                for line in rv.stdout.splitlines():
                    if line.startswith("Version:"):
                        version = line.split(":", 1)[1].strip()
                        break
                _mark_installed(pip_name, version)
                _progress(f"  ✔ '{pip_name}' installato ({version})")
                return True, f"'{pip_name}' installato con successo."
            else:
                msg = f"pip ha restituito 0 ma '{pip_name}' non è importabile."
                _mark_failed(pip_name, msg)
                _progress(f"  ✖ {msg}")
                return False, msg
        else:
            # Filtra errori comuni e dai suggerimenti utili
            err_summary = _summarize_pip_error(pip_name, err, os_name)
            _mark_failed(pip_name, err_summary)
            _progress(f"  ✖ Errore: {err_summary}")
            return False, err_summary
    except subprocess.TimeoutExpired:
        msg = f"Timeout durante l'installazione di '{pip_name}' (>300s)."
        _mark_failed(pip_name, msg)
        return False, msg
    except Exception as exc:
        msg = str(exc)
        _mark_failed(pip_name, msg)
        return False, msg


def _summarize_pip_error(pip_name: str, stderr: str, os_name: str) -> str:
    """Trasforma l'output di errore pip in un messaggio comprensibile."""
    if "externally-managed-environment" in stderr:
        return (
            "Ambiente Python 'externally-managed' (es. Ubuntu 23+). "
            "Avvia l'app da un venv: ./venv/bin/python main.py"
        )
    if "No matching distribution found" in stderr:
        return f"Nessuna versione di '{pip_name}' compatibile con questa versione Python."
    if "error: Microsoft Visual C++" in stderr:
        return (
            f"'{pip_name}' richiede Visual C++ Build Tools (Windows). "
            "Installa da: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        )
    if "gcc" in stderr.lower() or "compiler" in stderr.lower():
        if os_name == "linux":
            return (
                f"'{pip_name}' richiede gcc: sudo apt install build-essential python3-dev"
            )
        return f"'{pip_name}' richiede un compilatore C/C++."
    if "Could not find a version" in stderr:
        return f"'{pip_name}' non trovato su PyPI. Controlla il nome del pacchetto."
    # Fallback: prime 2 righe di errore significative
    lines = [l for l in stderr.splitlines() if l.strip() and "WARNING" not in l]
    return " | ".join(lines[:2]) if lines else "Errore sconosciuto."


# ══════════════════════════════════════════════════════════════════════════════
# API ON-DEMAND  (importata da main.py)
# ══════════════════════════════════════════════════════════════════════════════

# Cache in-memory per evitare dialog multipli nella stessa sessione
_session_declined: set = set()
_session_installed: set = set()


def require_optional(
    pip_name: str,
    reason: str = "",
    extra_packages: Optional[List[str]] = None,
    silent: bool = False,
) -> bool:
    """
    Verifica che una libreria opzionale sia disponibile.
    Se manca, mostra una finestra Qt di consenso e la installa.

    Parametri:
        pip_name        Nome pip del pacchetto (es. 'psycopg2-binary')
        reason          Descrizione leggibile del perché serve (es. 'connessioni PostgreSQL')
        extra_packages  Lista di pacchetti aggiuntivi da installare insieme
        silent          Se True, installa senza chiedere conferma (usare con cautela)

    Ritorna True se la libreria è disponibile, False altrimenti.
    """
    # Cache: già installato in questa sessione
    if pip_name in _session_installed or is_installed(pip_name):
        _session_installed.add(pip_name)
        return True

    # Cache: l'utente ha già rifiutato in questa sessione
    if pip_name in _session_declined:
        return False

    all_packages = [pip_name] + (extra_packages or [])

    if silent:
        return _do_install_optional(all_packages, pip_name, reason)

    # Mostra dialogo Qt (se Qt è disponibile)
    try:
        from PySide6.QtWidgets import QApplication, QDialog  # noqa
        app = QApplication.instance()
        if app is not None:
            accepted = _show_install_dialog(pip_name, reason, all_packages)
            if not accepted:
                _session_declined.add(pip_name)
                return False
            return _do_install_optional(all_packages, pip_name, reason)
    except ImportError:
        pass

    # Fallback console
    print(f"\n[Libreria mancante] '{pip_name}' necessaria per: {reason}")
    answer = input("Installare ora? [s/N] ").strip().lower()
    if answer not in {"s", "si", "sì", "y", "yes"}:
        _session_declined.add(pip_name)
        return False
    return _do_install_optional(all_packages, pip_name, reason)


def _do_install_optional(
    packages: List[str],
    primary: str,
    reason: str,
) -> bool:
    """Esegue l'installazione effettiva mostrando un dialogo di progresso Qt."""
    with _install_lock:
        # Ricontrolla dopo aver acquisito il lock
        if primary in _session_installed or is_installed(primary):
            _session_installed.add(primary)
            return True
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                success = _show_progress_dialog(packages, primary, reason)
            else:
                # Modalità console
                success = _console_install(packages, primary)
        except ImportError:
            success = _console_install(packages, primary)

        if success:
            _session_installed.add(primary)
        return success


def _console_install(packages: List[str], primary: str) -> bool:
    print(f"Installazione in corso: {', '.join(packages)}...")
    py = get_python_executable()
    os_name = detect_os()
    for pkg in packages:
        ok, msg = install_single_optional(pkg, py)
        if not ok and pkg == primary:
            print(f"✖ Installazione fallita: {msg}")
            return False
    return True


def _show_install_dialog(
    pip_name: str,
    reason: str,
    all_packages: List[str],
) -> bool:
    """
    Mostra una finestra Qt di consenso prima di installare.
    Ritorna True se l'utente acconsente.
    """
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QCheckBox, QTextEdit,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    dlg = QDialog()
    dlg.setWindowTitle("Installazione libreria richiesta")
    dlg.setMinimumWidth(480)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)

    layout = QVBoxLayout(dlg)

    icon_lbl = QLabel("📦")
    icon_lbl.setFont(QFont("Arial", 28))
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    title_lbl = QLabel(f"Libreria opzionale richiesta")
    title_lbl.setFont(QFont("Arial", 13, QFont.Weight.Bold))
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    info = QTextEdit()
    info.setReadOnly(True)
    info.setMaximumHeight(160)
    info.setFont(QFont("Courier New", 10))

    os_name = detect_os()
    sys_dep = ""
    base = pip_name.split("[")[0].replace("-", "_")
    if base in _SYSTEM_DEPS:
        sys_dep = f"\n⚠ Dipendenza di sistema: {_SYSTEM_DEPS[base].get(os_name,'')}"

    reg = _load_optional_registry()
    last_attempt = ""
    if pip_name in reg and not reg[pip_name].get("installed"):
        last_attempt = f"\n⚠ Tentativo precedente fallito: {reg[pip_name].get('error','')}"

    info.setPlainText(
        f"Funzione richiesta : {reason or pip_name}\n"
        f"Pacchetti pip      : {', '.join(all_packages)}\n"
        f"Interprete Python  : {get_python_executable()}\n"
        f"Comando            : pip install {' '.join(all_packages)}"
        f"{sys_dep}{last_attempt}"
    )

    remember_chk = QCheckBox("Ricorda la mia scelta per questa sessione")
    remember_chk.setChecked(True)

    btn_yes = QPushButton("✔  Installa ora")
    btn_yes.setDefault(True)
    btn_no  = QPushButton("✖  Non installare")

    btn_yes.clicked.connect(dlg.accept)
    btn_no.clicked.connect(dlg.reject)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(btn_yes)
    btn_row.addWidget(btn_no)

    layout.addWidget(icon_lbl)
    layout.addWidget(title_lbl)
    layout.addSpacing(8)
    layout.addWidget(info)
    layout.addWidget(remember_chk)
    layout.addLayout(btn_row)

    return dlg.exec() == QDialog.DialogCode.Accepted


def _show_progress_dialog(
    packages: List[str],
    primary: str,
    reason: str,
) -> bool:
    """
    Mostra una finestra Qt con barra di progresso durante l'installazione.
    Ritorna True se tutti i pacchetti sono stati installati.
    """
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QProgressBar, QTextEdit, QPushButton,
    )
    from PySide6.QtCore import Qt, QThread, Signal, QObject
    from PySide6.QtGui import QFont

    class InstallerWorker(QObject):
        log     = Signal(str)
        done    = Signal(bool, str)

        def __init__(self, pkgs: List[str], py: str) -> None:
            super().__init__()
            self.pkgs = pkgs
            self.py   = py

        def run(self) -> None:
            overall_ok = True
            last_msg   = ""
            for pkg in self.pkgs:
                self.log.emit(f"▶ Installazione: {pkg}...")
                ok, msg = install_single_optional(
                    pkg, self.py,
                    progress_callback=lambda m: self.log.emit("  " + m),
                )
                if not ok:
                    overall_ok = False
                    last_msg   = msg
                    self.log.emit(f"  ✖ {msg}")
                    if pkg == self.pkgs[0]:   # pacchetto primario fallito: stop
                        break
                else:
                    self.log.emit(f"  ✔ {pkg} installato.")
            self.done.emit(overall_ok, last_msg)

    dlg = QDialog()
    dlg.setWindowTitle(f"Installazione — {primary}")
    dlg.setMinimumWidth(520)
    dlg.setMinimumHeight(300)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)

    layout = QVBoxLayout(dlg)
    status_lbl = QLabel(f"Installazione di: {', '.join(packages)}")
    status_lbl.setFont(QFont("Arial", 11, QFont.Weight.Bold))

    progress = QProgressBar()
    progress.setRange(0, 0)   # indeterminate

    log_box = QTextEdit()
    log_box.setReadOnly(True)
    log_box.setFont(QFont("Courier New", 10))
    log_box.setMaximumHeight(180)

    close_btn = QPushButton("Chiudi")
    close_btn.setEnabled(False)
    close_btn.clicked.connect(dlg.accept)

    layout.addWidget(status_lbl)
    layout.addWidget(progress)
    layout.addWidget(QLabel("Log:"))
    layout.addWidget(log_box)
    layout.addWidget(close_btn)

    result_holder: Dict[str, object] = {"ok": False, "msg": ""}

    thread   = QThread()
    py_exec  = get_python_executable()
    worker   = InstallerWorker(packages, py_exec)
    worker.moveToThread(thread)

    def on_log(msg: str) -> None:
        log_box.append(msg)

    def on_done(ok: bool, msg: str) -> None:
        result_holder["ok"]  = ok
        result_holder["msg"] = msg
        progress.setRange(0, 1)
        progress.setValue(1)
        if ok:
            status_lbl.setText("✔ Installazione completata.")
            progress.setStyleSheet("QProgressBar::chunk { background:#4CAF50; }")
        else:
            status_lbl.setText("✖ Installazione fallita.")
            progress.setStyleSheet("QProgressBar::chunk { background:#F44336; }")
            log_box.append(f"\nErrore: {msg}")
        close_btn.setEnabled(True)

    worker.log.connect(on_log)
    worker.done.connect(on_done)
    thread.started.connect(worker.run)
    thread.start()

    dlg.exec()
    thread.quit()
    thread.wait(3000)

    return bool(result_holder["ok"])


def require_optional_group(
    group_name: str,
    packages: List[str],
    reason: str = "",
    silent: bool = False,
) -> bool:
    """
    Installa un gruppo di pacchetti correlati (es. tutti i driver Snowflake).
    Ritorna True solo se TUTTI i pacchetti sono disponibili.
    """
    # Prima verifica: tutti già installati?
    missing = [p for p in packages if not is_installed(p)]
    if not missing:
        return True

    full_reason = reason or f"gruppo '{group_name}'"
    primary = missing[0]
    extra   = missing[1:]
    return require_optional(primary, full_reason, extra, silent)


# ══════════════════════════════════════════════════════════════════════════════
# GESTIONE DIPENDENZE AVVIO (CORE)
# ══════════════════════════════════════════════════════════════════════════════

def verify_and_ensure_pip(python_executable: Optional[str] = None) -> str:
    if python_executable is None:
        python_executable = get_python_executable()
    print(f"Verifica pip con: {python_executable}")
    r = subprocess.run(
        [python_executable, "-m", "pip", "--version"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        print(f"✓ pip disponibile: {r.stdout.strip()}")
        return python_executable

    os_name = detect_os()
    print("\n⚠ pip non disponibile.")
    hints = {
        "linux":   "sudo apt update && sudo apt install -y python3-pip python3-venv",
        "macos":   "python3 -m pip install --upgrade pip",
        "windows": "Scarica get-pip.py da https://bootstrap.pypa.io/get-pip.py",
    }
    print(f"  Installa pip: {hints.get(os_name, 'python3 -m ensurepip --upgrade')}")
    raise RuntimeError("pip non disponibile. Installa pip e riavvia.")


def ensure_dependencies_before_startup(
    markdown_path: str = "LIBRARIES.md",
    auto_update: bool = True,
) -> None:
    """
    Chiamata all'avvio da main.py.
    Installa le librerie CORE da LIBRARIES.md.
    Le librerie opzionali vengono gestite on-demand tramite require_optional().
    """
    SEP = "=" * 70
    print(f"\n{SEP}")
    print("GESTIONE DIPENDENZE — HealthReport Studio")
    print(SEP)

    os_name = detect_os()
    libraries = read_libraries_from_markdown(markdown_path)
    print(f"\nOS         : {os_name}")
    print(f"Core libs  : {', '.join(libraries)}")

    # STEP 0 — Crea venv su Linux se necessario
    python_executable = get_python_executable()
    if os_name == "linux" and not os.environ.get("VIRTUAL_ENV"):
        cwd = Path.cwd()
        venv_py = cwd / "venv" / "bin" / "python3"
        if not venv_py.exists():
            print("\n[STEP 0] Creazione venv locale...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", str(cwd / "venv")],
                    check=True, capture_output=True, timeout=60,
                )
                subprocess.run(
                    [str(venv_py), "-m", "ensurepip", "--upgrade"],
                    check=False, capture_output=True, timeout=30,
                )
                python_executable = str(venv_py)
                print(f"✓ venv creato: {venv_py}")
            except Exception as exc:
                print(f"⚠ Impossibile creare venv: {exc} — uso Python di sistema.")
        else:
            python_executable = str(venv_py)
            print(f"✓ venv trovato: {venv_py}")

    # STEP 1 — Verifica pip
    print("\n[STEP 1] Verifica pip...")
    try:
        python_executable = verify_and_ensure_pip(python_executable)
    except RuntimeError as exc:
        print(f"❌ {exc}")
        raise

    # STEP 2 — Controlla quali core libs mancano
    print("\n[STEP 2] Verifica librerie core...")
    missing = check_if_libraries_installed(libraries, python_executable)
    if not missing:
        print("✓ Tutte le librerie core sono installate.")
        _print_ready()
        return

    print(f"⚠ Mancanti: {', '.join(missing)}")
    if not auto_update:
        print("⚠ auto_update disabilitato.")
        _print_ready()
        return

    # STEP 3 — Aggiorna pip e installa le mancanti
    print("\n[STEP 3] Installazione librerie core...")
    r = subprocess.run(
        base_pip_command(python_executable) + ["install", "--upgrade", "pip"],
        capture_output=True, text=True,
    )
    if "externally-managed-environment" in r.stderr:
        print("⚠ Ambiente externally-managed. Avviare l'app dal venv.")
        return

    rc, out, err = install_libraries(missing, os_name, python_executable, upgrade=True)
    if rc == 0:
        print("✓ Installazione completata.")
        _print_ready()
        return

    # Verifica parziale
    still_missing = check_if_libraries_installed(libraries, python_executable)
    if not still_missing:
        print("✓ Tutte le librerie risultano installate (nonostante exit code != 0).")
        _print_ready()
        return

    installed_n = len(missing) - len(still_missing)
    if installed_n > 0:
        print(f"⚠ Installazione parziale: {installed_n}/{len(missing)} OK, "
              f"mancanti: {', '.join(still_missing)}")
        _print_ready(warning=True)
        return

    raise RuntimeError(
        "Installazione librerie core fallita.\n"
        "Verifica connessione internet, permessi e dipendenze di sistema."
    )


def _print_ready(warning: bool = False) -> None:
    SEP = "=" * 70
    print(f"\n{SEP}")
    if warning:
        print("⚠ AVVIO CON AVVERTIMENTI — alcune librerie non installate")
    else:
        print("✓ DIPENDENZE OK — APPLICAZIONE PRONTA")
    print(SEP + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# PANNELLO DI GESTIONE OPZIONALI (QDialog Qt)
# ══════════════════════════════════════════════════════════════════════════════

def open_optional_manager(parent=None) -> None:
    """
    Apre il pannello grafico di gestione delle librerie opzionali.
    Può essere chiamato dal menu Strumenti → Gestione dipendenze opzionali.
    """
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
        QTableWidgetItem, QPushButton, QHeaderView, QProgressBar,
        QTextEdit, QSplitter, QCheckBox, QLineEdit,
    )
    from PySide6.QtCore import Qt, QThread, Signal, QObject
    from PySide6.QtGui import QFont, QColor

    optional_md = read_optional_libraries_from_markdown(
        str(Path(__file__).resolve().parent / "LIBRARIES_OPTIONAL.md")
    )
    registry    = _load_optional_registry()
    py_exec     = get_python_executable()

    dlg = QDialog(parent)
    dlg.setWindowTitle("Gestione librerie opzionali — HealthReport Studio")
    dlg.resize(820, 580)
    layout = QVBoxLayout(dlg)

    # Barra ricerca
    search_bar = QHBoxLayout()
    search_edit = QLineEdit(); search_edit.setPlaceholderText("Filtra librerie...")
    search_bar.addWidget(QLabel("🔍")); search_bar.addWidget(search_edit)

    # Tabella
    headers = ["Pacchetto pip", "Descrizione", "Stato", "Versione", ""]
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    # Log area
    log_box = QTextEdit()
    log_box.setReadOnly(True)
    log_box.setFont(QFont("Courier New", 9))
    log_box.setMaximumHeight(120)
    log_box.setPlaceholderText("Log installazioni...")

    # Barra azioni
    act_bar = QHBoxLayout()
    progress = QProgressBar(); progress.setRange(0, 0); progress.setVisible(False)
    progress.setMaximumWidth(200)
    btn_install_sel  = QPushButton("📦 Installa selezionati")
    btn_install_all  = QPushButton("📦 Installa tutti mancanti")
    btn_refresh      = QPushButton("🔄 Aggiorna stato")
    btn_close        = QPushButton("Chiudi")
    act_bar.addWidget(btn_install_sel)
    act_bar.addWidget(btn_install_all)
    act_bar.addWidget(btn_refresh)
    act_bar.addStretch()
    act_bar.addWidget(progress)
    act_bar.addWidget(btn_close)

    layout.addLayout(search_bar)
    layout.addWidget(table, stretch=1)
    layout.addWidget(QLabel("Log:"))
    layout.addWidget(log_box)
    layout.addLayout(act_bar)

    # --- Popola la tabella ---
    all_rows: List[Dict] = []   # {pip_name, description, installed, version, row_idx}

    def _populate(filter_text: str = "") -> None:
        table.setRowCount(0)
        all_rows.clear()
        ft = filter_text.lower()
        for pip_name, desc in optional_md.items():
            if ft and ft not in pip_name.lower() and ft not in desc.lower():
                continue
            installed = is_installed(pip_name, py_exec)
            reg_entry = registry.get(pip_name, {})
            version   = reg_entry.get("version", "") if installed else ""
            status    = "✔ Installato" if installed else "✖ Mancante"

            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(pip_name))
            table.setItem(row, 1, QTableWidgetItem(desc))
            si = QTableWidgetItem(status)
            si.setForeground(QColor("#2E7D32") if installed else QColor("#C62828"))
            table.setItem(row, 2, si)
            table.setItem(row, 3, QTableWidgetItem(version))

            btn = QPushButton("Reinstalla" if installed else "Installa")
            btn.setMaximumHeight(24)
            btn.clicked.connect(lambda _, n=pip_name: _install_one(n))
            table.setCellWidget(row, 4, btn)

            all_rows.append({
                "pip_name": pip_name, "description": desc,
                "installed": installed, "row": row,
            })

    def _log(msg: str) -> None:
        log_box.append(msg)

    # --- Worker thread ---
    class BulkWorker(QObject):
        log  = Signal(str)
        done = Signal()

        def __init__(self, pkgs: List[str]) -> None:
            super().__init__()
            self.pkgs = pkgs

        def run(self) -> None:
            for pkg in self.pkgs:
                self.log.emit(f"▶ {pkg}...")
                ok, msg = install_single_optional(pkg, py_exec,
                    progress_callback=lambda m: self.log.emit("  " + m))
                self.log.emit(("  ✔ OK" if ok else "  ✖ " + msg))
            self.done.emit()

    _thread_holder: Dict[str, object] = {}

    def _run_bulk(packages: List[str]) -> None:
        if not packages:
            return
        progress.setVisible(True)
        btn_install_sel.setEnabled(False)
        btn_install_all.setEnabled(False)

        worker = BulkWorker(packages)
        thread = QThread()
        worker.moveToThread(thread)
        worker.log.connect(_log)

        def _on_done() -> None:
            progress.setVisible(False)
            btn_install_sel.setEnabled(True)
            btn_install_all.setEnabled(True)
            registry.update(_load_optional_registry())
            _populate(search_edit.text())
            thread.quit()

        worker.done.connect(_on_done)
        thread.started.connect(worker.run)
        _thread_holder["t"] = thread
        _thread_holder["w"] = worker
        thread.start()

    def _install_one(pip_name: str) -> None:
        _run_bulk([pip_name])

    def _install_selected() -> None:
        selected_rows = {idx.row() for idx in table.selectedIndexes()}
        pkgs = [
            r["pip_name"] for r in all_rows
            if r["row"] in selected_rows and not r["installed"]
        ]
        if not pkgs:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(dlg, "Selezione",
                "Seleziona almeno una libreria non ancora installata.")
            return
        _run_bulk(pkgs)

    def _install_all_missing() -> None:
        pkgs = [r["pip_name"] for r in all_rows if not r["installed"]]
        _run_bulk(pkgs)

    def _on_search(text: str) -> None:
        _populate(text)

    btn_install_sel.clicked.connect(_install_selected)
    btn_install_all.clicked.connect(_install_all_missing)
    btn_refresh.clicked.connect(lambda: _populate(search_edit.text()))
    btn_close.clicked.connect(dlg.accept)
    search_edit.textChanged.connect(_on_search)

    _populate()
    dlg.exec()


# ══════════════════════════════════════════════════════════════════════════════
# SHORTCUTS PER I PROVIDER DB/CLOUD
# ══════════════════════════════════════════════════════════════════════════════

# Mappa provider → pacchetti richiesti
PROVIDER_PACKAGES: Dict[str, List[str]] = {
    "PostgreSQL":          ["psycopg2-binary"],
    "MySQL":               ["pymysql"],
    "MSSQL":               ["pyodbc"],
    "Oracle":              ["oracledb"],
    "DuckDB":              ["duckdb", "duckdb-engine"],
    "IBM DB2":             ["ibm_db", "ibm_db_sa"],
    "Firebird":            ["fdb"],
    "Snowflake":           ["snowflake-connector-python", "snowflake-sqlalchemy"],
    "Databricks":          ["databricks-sql-connector", "sqlalchemy-databricks"],
    "Redshift":            ["redshift-connector", "sqlalchemy-redshift"],
    "Athena":              ["PyAthena"],
    "BigQuery":            ["google-cloud-bigquery", "sqlalchemy-bigquery"],
    "CloudSQL":            ["psycopg2-binary", "cloud-sql-python-connector"],
    "Spanner":             ["google-cloud-spanner", "sqlalchemy-spanner"],
    "AzureSQL":            ["pyodbc"],
    "CosmosDB":            ["azure-cosmos"],
    "MongoDB":             ["pymongo"],
    "InfluxDB":            ["influxdb-client"],
    "Elasticsearch":       ["elasticsearch", "eland"],
    "ClickHouse":          ["clickhouse-driver", "sqlalchemy-clickhouse"],
    "CockroachDB":         ["psycopg2-binary", "sqlalchemy-cockroachdb"],
    "DynamoDB":            ["boto3"],
    "export_pptx":         ["python-pptx"],
    "export_docx":         ["python-docx"],
}


def require_provider(provider_name: str, silent: bool = False) -> bool:
    """
    Verifica e installa tutti i pacchetti necessari per un provider DB/Cloud.

    Esempio:
        if not require_provider("PostgreSQL"):
            return
        import psycopg2
        ...
    """
    packages = PROVIDER_PACKAGES.get(provider_name, [])
    if not packages:
        return True
    return require_optional_group(
        group_name=provider_name,
        packages=packages,
        reason=f"connessione al provider {provider_name}",
        silent=silent,
    )

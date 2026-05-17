from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from pathlib import Path


def get_local_venv_python() -> str | None:
    """Rileva se esiste un virtual environment locale nella cartella corrente."""
    cwd = Path.cwd()
    
    # Possibili posizioni del venv
    venv_paths = [
        cwd / "venv" / "bin" / "python3",
        cwd / "venv" / "bin" / "python",
        cwd / ".venv" / "bin" / "python3",
        cwd / ".venv" / "bin" / "python",
        cwd / "env" / "bin" / "python3",
        cwd / "env" / "bin" / "python",
    ]
    
    for venv_python in venv_paths:
        if venv_python.exists():
            # Verifica se ha pip
            result = subprocess.run(
                [str(venv_python), "-m", "pip", "--version"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return str(venv_python)
    
    return None


def get_python_executable() -> str:
    """Ritorna il path dell'interprete Python da usare (preferibilmente da venv)."""
    # Controlla se siamo già dentro un venv
    if os.environ.get("VIRTUAL_ENV"):
        return sys.executable
    
    # Altrimenti, ricerca un venv locale
    venv_python = get_local_venv_python()
    if venv_python:
        print(f"✓ Virtual environment locale trovato: {venv_python}")
        return venv_python
    
    # Fallback al python corrente
    return sys.executable


def read_libraries_from_markdown(markdown_path: str = "LIBRARIES.md") -> list[str]:
    path = Path(markdown_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File {markdown_path} non trovato. Crea LIBRARIES.md nella cartella del progetto."
        )

    content = path.read_text(encoding="utf-8")
    libraries: list[str] = []

    for line in content.splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        match = re.match(r"^[-*]\s+([A-Za-z0-9_.[\]>=<,!-]+)", line)
        if match:
            libraries.append(match.group(1))

    if not libraries:
        raise ValueError(
            f"Nessuna libreria trovata in {markdown_path}. Usa righe tipo: - pandas"
        )

    return libraries


def detect_os() -> str:
    system = platform.system().lower()

    if system == "linux":
        return "linux"

    if system == "windows":
        return "windows"

    if system == "darwin":
        return "macos"

    return "unknown"


def verify_and_ensure_pip(python_executable: str | None = None) -> str:
    """
    Verifica se pip è disponibile nel python_executable.
    Se non è presente, stampa istruzioni di installazione per l'OS
    e genera un errore per terminare l'applicazione.
    """
    if python_executable is None:
        python_executable = get_python_executable()
    
    print(f"Verifica di pip con: {python_executable}")
    
    result = subprocess.run(
        [python_executable, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        print(f"✓ pip è disponibile: {result.stdout.strip()}")
        return python_executable

    os_name = detect_os()
    print("\n⚠ pip non è disponibile nell'interprete Python corrente.")
    print("Serve pip per installare/aggiornare le dipendenze prima dell'avvio.")
    print("\nInstallazione pip richiesta per il sistema operativo rilevato:")

    if os_name == "linux":
        print("  Linux:")
        print("    sudo apt update")
        print("    sudo apt install -y python3-pip python3-venv")
        print("    python3 -m pip --version")
        print("    python3 -m venv venv")
        print("    ./venv/bin/python3 main.py")
    elif os_name == "windows":
        print("  Windows:")
        print("    Scarica get-pip.py da: https://bootstrap.pypa.io/get-pip.py")
        print("    python get-pip.py")
        print("    python -m venv venv")
        print("    venv\\Scripts\\python main.py")
    elif os_name == "macos":
        print("  macOS:")
        print("    python3 -m pip install --upgrade pip")
        print("    python3 -m venv venv")
        print("    ./venv/bin/python3 main.py")
    else:
        print("  OS non riconosciuto. Usa il gestore pacchetti del tuo sistema per installare pip.")
        print("  Esempio: python3 -m ensurepip --upgrade")

    raise RuntimeError(
        "pip non è disponibile. Installa pip sul sistema operativo e riavvia l'applicazione."
    )


def base_pip_command(python_executable: str | None = None) -> list[str]:
    """Ritorna il comando base per pip."""
    if python_executable is None:
        python_executable = get_python_executable()
    return [python_executable, "-m", "pip"]


def upgrade_pip_for_os(os_name: str, python_executable: str | None = None) -> None:
    command = base_pip_command(python_executable) + ["install", "--upgrade", "pip"]

    if os_name in {"linux", "windows", "macos"}:
        command += ["--prefer-binary"]

    subprocess.run(command, check=False)


def get_pip_install_command(libraries: list[str], os_name: str, python_executable: str) -> list[str]:
    """Costruisce il comando di installazione pip corretto per l'OS rilevato."""
    command = [python_executable, "-m", "pip", "install", "--upgrade"]

    if os_name in {"linux", "windows", "macos"}:
        command += ["--prefer-binary"]

    in_venv = bool(os.environ.get("VIRTUAL_ENV")) or ".venv" in python_executable or "venv" in python_executable
    if os_name == "linux" and not in_venv:
        command.append("--user")

    command += libraries
    return command


def check_if_libraries_installed(libraries: list[str], python_executable: str | None = None) -> list[str]:
    """Controlla quali librerie sono già installate nel python_executable specificato."""
    if python_executable is None:
        python_executable = get_python_executable()
    
    missing = []
    for lib in libraries:
        lib_name = lib.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("!")[0].strip()
        
        # Usa il python executable corretto per verificare
        result = subprocess.run(
            [python_executable, "-c", f"import {lib_name}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            missing.append(lib)
    
    return missing


def install_or_update_libraries(libraries: list[str], os_name: str, python_executable: str | None = None) -> int:
    """Installa o aggiorna le librerie. Ritorna il codice di uscita."""
    if python_executable is None:
        python_executable = get_python_executable()

    command = get_pip_install_command(libraries, os_name, python_executable)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return int(completed.returncode)


def create_or_use_venv(os_name: str) -> str:
    """
    Crea un virtual environment locale se necessario e ritorna il path dell'interprete.
    Gestisce l'ambiente externally-managed di Debian/Ubuntu.
    """
    cwd = Path.cwd()
    venv_path = cwd / "venv"
    venv_python = venv_path / "bin" / "python3"
    
    if venv_python.exists():
        print(f"✓ Virtual environment locale già presente: {venv_path}")
        return str(venv_python)
    
    print(f"\n⚠ Ambiente externally-managed rilevato. Creazione venv locale...")
    
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            capture_output=True,
        )
        print(f"✓ Virtual environment creato: {venv_path}")
        
        # Aggiorna pip nel venv
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
            check=False,
            capture_output=True,
        )
        
        return str(venv_python)
    except Exception as e:
        raise RuntimeError(f"Impossibile creare virtual environment: {e}")


def ensure_dependencies_before_startup(
    markdown_path: str = "LIBRARIES.md",
    auto_update: bool = True,
) -> None:
    """
    Funzione esterna a main.py.

    Viene richiamata prima di ogni esecuzione.
    Legge la lista librerie da LIBRARIES.md.
    Riconosce il sistema operativo.
    Verifica e installa pip se necessario.
    Aggiorna pip e librerie in modo adatto all'ambiente.
    """

    print("\n" + "="*70)
    print("GESTIONE DIPENDENZE - HealthReport Studio")
    print("="*70)
    
    os_name = detect_os()
    libraries = read_libraries_from_markdown(markdown_path)

    print(f"\nSistema operativo: {os_name}")
    print(f"Librerie richieste: {', '.join(libraries)}\n")

    # STEP 0: Risolvi il problema di ambiente externally-managed
    python_executable = get_python_executable()
    
    # Su Linux, se non siamo in un venv, crea uno per evitare problemi externally-managed
    if os_name == "linux" and not os.environ.get("VIRTUAL_ENV"):
        cwd = Path.cwd()
        venv_path = cwd / "venv"
        venv_python = venv_path / "bin" / "python3"
        
        if not venv_python.exists():
            print("[STEP 0] Creazione venv locale per evitare restrizioni di sistema...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", str(venv_path)],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                print(f"✓ Virtual environment creato: {venv_path}")
                
                # Aggiorna pip nel venv usando ensurepip
                print("  Aggiornamento pip nel venv...")
                subprocess.run(
                    [str(venv_python), "-m", "ensurepip", "--upgrade"],
                    check=False,
                    capture_output=True,
                    timeout=30,
                )
                
                python_executable = str(venv_python)
                print(f"✓ Utilizzerò: {python_executable}\n")
            except Exception as e:
                print(f"⚠ Impossibile creare venv: {e}")
                print("Continuo con python di sistema...")
        else:
            python_executable = str(venv_python)
            print(f"✓ Virtual environment locale trovato: {venv_path}\n")

    # STEP 1: Verifica e installa pip se necessario
    print("[STEP 1] Verifica e gestione di pip...")
    try:
        python_executable = verify_and_ensure_pip(python_executable)
    except RuntimeError as e:
        print(f"\n❌ ERRORE: {e}")
        raise
    
    # STEP 2: Verifica quale libreria mancano
    print("\n[STEP 2] Verifica librerie installate...")
    missing_libraries = check_if_libraries_installed(libraries, python_executable)
    
    if not missing_libraries:
        print("✓ Tutte le librerie sono già installate.")
        print("\n" + "="*70)
        print("✓ DIPENDENZE OK - APPLICAZIONE PRONTA")
        print("="*70 + "\n")
        return

    print(f"⚠ Librerie mancanti: {', '.join(missing_libraries)}")

    if not auto_update:
        print("⚠ auto_update è disabilitato. Saltando installazione.")
        print("="*70 + "\n")
        return

    # STEP 3: Installazione librerie
    print("\n[STEP 3] Installazione librerie mancanti...")
    
    try:
        print("Aggiornamento pip...")
        result = subprocess.run(
            base_pip_command(python_executable) + ["install", "--upgrade", "pip"],
            capture_output=True,
            text=True,
        )
        
        if "externally-managed-environment" in result.stderr:
            print("\n⚠ AVVISO: Ambiente externally-managed rilevato.")
            print("  Impossibile installare pacchetti Python automaticamente su questo sistema.")
            print("\n  Opzioni:")
            print("  1. Usa manualmente un virtual environment:")
            print("     python3 -m venv venv_new")
            print("     ./venv_new/bin/python3 main.py")
            print("\n  2. Installa i pacchetti manualmente nel venv:")
            print("     ./venv_new/bin/pip install pandas openpyxl matplotlib PySide6")
            print("\n  3. Usa pipx (se disponibile):")
            print("     pipx install <package>")
            print("\n" + "="*70)
            print("⚠ AVVIO SALTATO - Installa le dipendenze e riavvia")
            print("="*70 + "\n")
            return
        
        print(f"Installazione di: {', '.join(missing_libraries)}")
        exit_code = install_or_update_libraries(missing_libraries, os_name, python_executable)

        if exit_code == 0:
            print("✓ Installazione completata con successo.")
            print("\n" + "="*70)
            print("✓ DIPENDENZE OK - APPLICAZIONE PRONTA")
            print("="*70 + "\n")
            return

        # Se exit_code != 0, controlla le librerie nel caso alcune siano state installate parzialmente
        print(f"\n⚠ Pip ha segnalato un errore (exit code: {exit_code})")
        still_missing = check_if_libraries_installed(libraries, python_executable)
        
        if not still_missing:
            print("✓ Nonostante il codice di errore, tutte le librerie risultano installate.")
            print("\n" + "="*70)
            print("✓ DIPENDENZE OK - APPLICAZIONE PRONTA")
            print("="*70 + "\n")
            return
        
        if len(still_missing) < len(missing_libraries):
            installed_count = len(missing_libraries) - len(still_missing)
            print(f"\n⚠ Installazione parziale: {installed_count} librerie installate, "
                  f"{len(still_missing)} ancora mancanti ({', '.join(still_missing)})")
            print("\n" + "="*70)
            print("⚠ AVVIO CON AVVERTIMENTO - Alcune librerie non sono state installate")
            print("="*70 + "\n")
            return
        
        # Tutte le librerie sono ancora mancanti
        raise RuntimeError(
            "Installazione librerie non riuscita. "
            "Controlla connessione, permessi, o dipendenze di sistema."
        )
        
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Pip non trovato: {e}\n"
            "Installa python3-pip o usa un virtual environment con python3 -m venv"
        )
    except Exception as e:
        print(f"\n❌ ERRORE: {e}")
        raise RuntimeError(f"Errore durante la gestione delle dipendenze: {e}")
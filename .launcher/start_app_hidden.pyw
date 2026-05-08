from __future__ import annotations

import os
import subprocess
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "output"
LOG_PATH = OUTPUT_DIR / "launcher.log"
PID_PATH = OUTPUT_DIR / "app.pid"
URL = "http://localhost:8501"
CREATE_NO_WINDOW = 0x08000000


def log(message: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message}\n")


def python_exe() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidate = Path(local_app_data) / "Programs" / "Python" / "Python311" / "python.exe"
    if candidate.exists():
        return candidate
    return Path("python.exe")


def is_app_running() -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=2) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def ensure_packages(python: Path) -> bool:
    check = subprocess.run(
        [str(python), "-c", "import streamlit, pandas, numpy"],
        cwd=PROJECT_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    if check.returncode == 0:
        return True

    log("Required packages missing. Installing requirements.txt.")
    with LOG_PATH.open("ab") as log_file:
        install = subprocess.run(
            [str(python), "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=PROJECT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    if install.returncode != 0:
        log(f"Package installation failed with exit code {install.returncode}.")
        return False
    return True


def start_app(python: Path) -> None:
    env = os.environ.copy()
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    command = [
        str(python),
        "-m",
        "streamlit",
        "run",
        str(PROJECT_DIR / "app.py"),
        "--server.port",
        "8501",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    log("Starting Streamlit.")
    log("Command: " + " ".join(command))
    log_file = LOG_PATH.open("ab")
    process = subprocess.Popen(
        command,
        cwd=PROJECT_DIR,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    PID_PATH.write_text(str(process.pid), encoding="utf-8")
    log(f"Started PID {process.pid}.")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if is_app_running():
        log("App is already running. Opening browser.")
        webbrowser.open(URL)
        return

    python = python_exe()
    if not ensure_packages(python):
        return

    start_app(python)
    for _ in range(30):
        if is_app_running():
            log("App is ready. Opening browser.")
            webbrowser.open(URL)
            return
        time.sleep(1)
    log("App did not respond within 30 seconds. Check launcher.log for details.")


if __name__ == "__main__":
    main()

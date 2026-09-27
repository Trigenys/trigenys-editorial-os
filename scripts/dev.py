from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
VENV = ROOT / ".venv"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def require(command: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise SystemExit(f"Required command not found: {command}")
    return resolved


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    npm = require("npm")
    python = venv_python()

    if not python.exists():
        raise SystemExit("Missing .venv. Run: python scripts/bootstrap.py")

    processes = [
        subprocess.Popen([npm, "run", "dev"], cwd=ROOT),
        subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                "editorial_os_api.main:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=BACKEND,
        ),
    ]

    print("Web: http://127.0.0.1:5173")
    print("API: http://127.0.0.1:8000")

    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    raise SystemExit(return_code)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            terminate(process)


if __name__ == "__main__":
    main()

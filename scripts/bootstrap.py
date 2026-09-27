from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
VENV = ROOT / ".venv"


def run(command: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=cwd, check=check, text=True)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def require(command: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise SystemExit(f"Required command not found: {command}")
    return resolved


def ensure_virtualenv() -> Path:
    python = venv_python()
    if not python.exists():
        print(f"Creating virtual environment at {VENV}")
        venv.EnvBuilder(with_pip=True).create(VENV)
    return python


def wait_for_postgres(docker: str) -> None:
    for attempt in range(1, 31):
        result = run(
            [
                docker,
                "compose",
                "exec",
                "-T",
                "db",
                "pg_isready",
                "-U",
                "editorial_os",
                "-d",
                "editorial_os",
            ],
            check=False,
        )
        if result.returncode == 0:
            return
        print(f"PostgreSQL not ready yet ({attempt}/30).")
        time.sleep(1)
    raise SystemExit("PostgreSQL did not become ready after 30 seconds.")


def main() -> None:
    npm = require("npm")
    docker = require("docker")
    python = ensure_virtualenv()

    run([npm, "install", "--ignore-scripts"])
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "-e", f"{BACKEND}[dev]"])

    run([docker, "compose", "up", "-d", "db"])
    wait_for_postgres(docker)

    run(
        [str(python), "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"],
        cwd=BACKEND,
    )

    print()
    print("Bootstrap complete.")
    print("Start both runtimes with: python scripts/dev.py")


if __name__ == "__main__":
    main()

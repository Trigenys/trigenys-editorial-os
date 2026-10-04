from __future__ import annotations

from pathlib import Path
from shutil import copytree, rmtree

ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = ROOT / "cloudflare"
WORKER_SRC = WORKER_ROOT / "src"
PACKAGE_SOURCE = ROOT / "backend" / "src" / "editorial_os_api"
PACKAGE_TARGET = WORKER_SRC / "editorial_os_api"
WEB_SOURCE = ROOT / "dist"
WEB_TARGET = WORKER_ROOT / "dist"


def _replace_tree(source: Path, target: Path) -> None:
    if not source.exists():
        raise SystemExit(f"Required build input does not exist: {source}")
    if target.exists():
        rmtree(target)
    copytree(source, target)


def main() -> None:
    _replace_tree(PACKAGE_SOURCE, PACKAGE_TARGET)
    _replace_tree(WEB_SOURCE, WEB_TARGET)


if __name__ == "__main__":
    main()

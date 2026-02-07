#!/usr/bin/env python3
"""Generate _version_static.py from pyproject.toml at build time.

This script reads the version from pyproject.toml and writes a static
version file that gets bundled into the package. The generated file
MUST NOT be committed to source control (see VERSIONING.md Rule 1).

Usage:
    python scripts/stamp_version.py
"""
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
OUTPUT = REPO_ROOT / "src" / "devlogs" / "_version_static.py"


def main():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = data["project"]["version"]
    OUTPUT.write_text(
        f'# AUTO-GENERATED at build time — do not edit or commit\n__version__ = "{version}"\n',
        encoding="utf-8",
    )
    print(f"Stamped {OUTPUT} → {version}")


if __name__ == "__main__":
    main()

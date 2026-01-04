from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "devlogs").is_dir():
            return candidate
    return None


def main() -> int:
    repo_root = _find_repo_root(Path.cwd())
    if repo_root is not None:
        venv_python = repo_root / ".venv" / "bin" / "python"
        if venv_python.is_file() and os.environ.get("DEVLOGS_WRAPPER_NO_VENV") != "1":
            os.execv(
                str(venv_python),
                [str(venv_python), "-m", "devlogs.cli", *sys.argv[1:]],
            )
        src_dir = repo_root / "src"
        if src_dir.is_dir():
            sys.path.insert(0, str(src_dir))

    from devlogs.cli import main as cli_main

    return cli_main() or 0

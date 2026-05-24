#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    alembic_args = sys.argv[1:] or ["upgrade", "head"]
    command = [sys.executable, "-m", "alembic", *alembic_args]
    return subprocess.call(command, cwd=str(project_root))


if __name__ == "__main__":
    raise SystemExit(main())

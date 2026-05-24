"""
Thin FastAPI entrypoint for Správa vozidel.
"""
from __future__ import annotations

import sys
from pathlib import Path


project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.server.bootstrap import create_app, initialize_process_runtime, run_server


app = create_app()
initialize_process_runtime()


if __name__ == "__main__":
    run_server(app)

"""Local test/import bootstrap for repository-root Python commands.

This lets `python -m unittest discover -s python/tests` work from the repo
root without requiring users or CI jobs to remember PYTHONPATH.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_DIR = ROOT / "python"
if PYTHON_DIR.is_dir():
    python_path = str(PYTHON_DIR)
    if python_path not in sys.path:
        sys.path.insert(0, python_path)

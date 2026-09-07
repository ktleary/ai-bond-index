"""Resolve AI Bond Index paths.

Scripts live in ``<repo>/code/``. Snapshots live in ``<repo>/data/`` by
default. Override with the ``AI_BOND_DATA_DIR`` environment variable
(absolute, ``~``-expanded, or relative to the repo root).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    raw = os.environ.get("AI_BOND_DATA_DIR")
    if raw:
        p = Path(raw).expanduser()
        p = p.resolve() if p.is_absolute() else (REPO_ROOT / p).resolve()
    else:
        p = (REPO_ROOT / "data").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

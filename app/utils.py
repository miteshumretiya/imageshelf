"""Small helpers shared by several modules."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> str:
    """Absolute path to a bundled file (works both from source and from a PyInstaller build).

    PyInstaller unpacks data files into sys._MEIPASS, so we look there first.
    """
    base = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    return str(base / relative)

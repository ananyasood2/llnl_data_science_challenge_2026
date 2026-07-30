"""Lattice inspection analysis API package bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

# ``npm run dev:api`` starts inside services/analysis-api.  Make the shared
# src-layout package importable even before developers run an editable install.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

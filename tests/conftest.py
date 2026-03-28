"""Conftest — ensure muninn package is loaded before any test collection."""
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `import muninn` finds the package
_REPO = str(Path(__file__).resolve().parent.parent)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# Pre-import the package so engine/core/muninn.py can never shadow it
import muninn  # noqa: E402,F401

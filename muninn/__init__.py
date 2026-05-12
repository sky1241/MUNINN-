"""
Muninn — Memory compression engine for LLMs.

Usage:
    import muninn
    muninn.boot(query="compression")
    muninn.compress_file("input.md")

CLI:
    muninn boot "query"
    muninn feed transcript.jsonl
    muninn compress file.md
    muninn status
"""
import sys
import types

# CHUNK C8 (2026-05-08): single source of truth = pyproject.toml.
try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError
    try:
        __version__ = _pkg_version("muninn")
    except PackageNotFoundError:
        __version__ = "1.0.1"  # checkout fallback (sync with pyproject.toml)
except Exception:
    __version__ = "1.0.1"

from . import _engine  # noqa: F401 — loads globals + sub-modules


class _ProxyModule(types.ModuleType):
    """Module subclass that proxies getattr/setattr to _engine."""

    def __getattr__(self, name):
        return getattr(_engine, name)

    def __setattr__(self, name, value):
        if name.startswith("__") and name.endswith("__"):
            super().__setattr__(name, value)
        else:
            setattr(_engine, name, value)

    def __delattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            super().__delattr__(name)
        else:
            delattr(_engine, name)


# Replace this module's class so setattr proxying works
sys.modules[__name__].__class__ = _ProxyModule

"""Compatibility shim — source of truth: engine/core/muninn_install.py.

Re-exports the install/hooks/cron functions extracted in chunk C.1 split
(2026-05-11 nuit) so `from muninn import install_hooks, install_cron`
keeps working through the muninn package ProxyModule.

Mirror obligatoire BUG-091 (engine/core/ ↔ muninn/ duplicated tree).
"""
from __future__ import annotations
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

# Re-export everything from the canonical module.
from muninn_install import *  # noqa: F401,F403
from muninn_install import (  # noqa: F401 — explicit re-export of privates
    _detect_init_system,
    _repos_registry_path,
    _load_repos_registry,
    _register_repo,
    _generate_bridge_hook,
    _generate_post_tool_failure_hook,
    _generate_subagent_start_hook,
    _generate_session_start_hook,
    _install_pre_tool_use_hooks,
    _install_scaling_hooks,
    _copy_hooks_from_source,
)

"""CHUNK C13 — Dependabot config sanity check.

CHUNK H4 (2026-05-08): hardened from string-grep to proper YAML parsing
+ structured invariants. A reformat of the YAML (semantically equivalent
but with different whitespace/quoting) no longer breaks the suite.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C13
        docs/BATTLE_PLAN_AUDIT3_2026-05-08.md §H4
"""
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
DEPENDABOT = REPO / ".github" / "dependabot.yml"


@pytest.fixture(scope="module")
def dependabot_data():
    if not DEPENDABOT.exists():
        pytest.skip("dependabot.yml not present")
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed; cannot parse dependabot.yml")
    text = DEPENDABOT.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def test_dependabot_config_exists():
    assert DEPENDABOT.exists(), (
        "Missing .github/dependabot.yml — see CHUNK C13"
    )


def test_dependabot_yaml_parses_clean(dependabot_data):
    """The file must parse as valid YAML and produce a dict at root."""
    assert isinstance(dependabot_data, dict), (
        f"Expected dict at YAML root, got {type(dependabot_data).__name__}"
    )


def test_dependabot_version_field_is_2(dependabot_data):
    """Dependabot v2 schema (the only supported one)."""
    assert dependabot_data.get("version") == 2, (
        f"Expected version: 2 (Dependabot v2 schema), got {dependabot_data.get('version')!r}"
    )


def test_dependabot_updates_is_list(dependabot_data):
    updates = dependabot_data.get("updates")
    assert isinstance(updates, list), (
        f"`updates` must be a YAML list, got {type(updates).__name__}"
    )
    assert len(updates) >= 1, "Need at least 1 update entry"


def test_dependabot_covers_pip_ecosystem(dependabot_data):
    """At least one entry must scan the pip ecosystem."""
    pip_entries = [
        u for u in dependabot_data["updates"]
        if u.get("package-ecosystem") == "pip"
    ]
    assert pip_entries, (
        "No `package-ecosystem: pip` entry found — Python deps not scanned"
    )
    pip = pip_entries[0]
    # Causality: must scan from the repo root (where pyproject.toml lives)
    assert pip.get("directory") == "/", (
        f"pip entry directory must be '/', got {pip.get('directory')!r}"
    )


def test_dependabot_covers_github_actions(dependabot_data):
    actions_entries = [
        u for u in dependabot_data["updates"]
        if u.get("package-ecosystem") == "github-actions"
    ]
    assert actions_entries, (
        "No `package-ecosystem: github-actions` entry found"
    )


def test_dependabot_schedule_weekly_typed(dependabot_data):
    """Each update must declare a weekly schedule (Dependabot only
    supports daily/weekly/monthly — anything else means a typo)."""
    for entry in dependabot_data["updates"]:
        schedule = entry.get("schedule") or {}
        interval = schedule.get("interval")
        assert interval == "weekly", (
            f"Entry for {entry.get('package-ecosystem')!r} has unexpected "
            f"schedule.interval={interval!r} (must be 'weekly')"
        )


def test_dependabot_pr_limit_is_sane(dependabot_data):
    """Each entry caps open PRs (otherwise Dependabot can flood the repo)."""
    for entry in dependabot_data["updates"]:
        limit = entry.get("open-pull-requests-limit")
        assert isinstance(limit, int) and 1 <= limit <= 10, (
            f"Entry for {entry.get('package-ecosystem')!r} has invalid PR "
            f"limit {limit!r} (must be int in [1, 10])"
        )

"""CHUNK C13 — Dependabot config sanity check."""
import re
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def test_dependabot_config_exists():
    assert (REPO / ".github" / "dependabot.yml").exists(), (
        "Missing .github/dependabot.yml — see CHUNK C13"
    )


def test_dependabot_covers_pip():
    src = (REPO / ".github" / "dependabot.yml").read_text()
    assert 'package-ecosystem: "pip"' in src or "package-ecosystem: pip" in src


def test_dependabot_covers_github_actions():
    src = (REPO / ".github" / "dependabot.yml").read_text()
    assert "github-actions" in src


def test_dependabot_schedule_weekly():
    src = (REPO / ".github" / "dependabot.yml").read_text()
    assert re.search(r'interval:\s*"?weekly"?', src), (
        "Dependabot schedule must be weekly"
    )


def test_dependabot_version_2():
    src = (REPO / ".github" / "dependabot.yml").read_text()
    assert src.lstrip().startswith("#") or "version: 2" in src
    assert "version: 2" in src

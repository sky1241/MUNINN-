"""
CHUNK 1 — Verifie que l'auto-memory natif Anthropic est desactive.

Pourquoi : Muninn est notre systeme memoire. Faire tourner l'auto-memory natif
de Claude Code en parallele cause de la derive entre 2 stockages et consomme
25 KB de contexte par session pour rien.

Test :
1. .claude/settings.local.json existe et est du JSON valide
2. La cle "autoMemoryEnabled" est presente
3. La valeur est booleen False
4. Les hooks Muninn (UserPromptSubmit, PreCompact, SessionEnd, Stop) sont
   toujours intacts (pas casses par l'edit)
"""
import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(REPO_ROOT, ".claude", "settings.local.json")


@pytest.fixture(scope="module")
def settings():
    if not os.path.exists(SETTINGS_PATH):
        pytest.skip(
            f"settings.local.json absent (gitignored par design). "
            f"Ce test verifie la config locale Muninn — voir CHANGELOG CHUNK 1 "
            f"pour reproduire la config sur ta machine."
        )
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_settings_is_valid_json(settings):
    """Le fichier doit etre du JSON valide (deja parse par la fixture)."""
    assert isinstance(settings, dict)


def test_auto_memory_key_present(settings):
    """La cle autoMemoryEnabled doit exister."""
    assert "autoMemoryEnabled" in settings, (
        "autoMemoryEnabled key missing — Claude Code natif va re-activer "
        "auto-memory par defaut depuis v2.1.59"
    )


def test_auto_memory_is_disabled(settings):
    """La valeur doit etre False (pas None, pas 0, pas string)."""
    val = settings["autoMemoryEnabled"]
    assert val is False, (
        f"autoMemoryEnabled should be exactly False, got {val!r} "
        f"(type: {type(val).__name__})"
    )


def test_hooks_section_intact(settings):
    """Les hooks Muninn ne doivent pas avoir ete casses par l'edit."""
    assert "hooks" in settings, "hooks section missing — Muninn ne tournerait plus"
    hooks = settings["hooks"]
    expected = {"UserPromptSubmit", "PreCompact", "SessionEnd", "Stop"}
    missing = expected - set(hooks.keys())
    assert not missing, f"Hooks Muninn manquants apres edit : {missing}"


def test_hooks_still_point_to_muninn(settings):
    """Chaque hook doit toujours appeler muninn.py ou bridge_hook.py."""
    hooks = settings["hooks"]
    for hook_name, entries in hooks.items():
        assert isinstance(entries, list) and entries, (
            f"Hook {hook_name} vide ou mal forme"
        )
        cmd = entries[0].get("command", "")
        assert ("muninn.py" in cmd) or ("bridge_hook.py" in cmd), (
            f"Hook {hook_name} ne pointe plus vers Muninn : {cmd}"
        )


def test_no_native_memory_dir_in_repo():
    """
    Verifie que le repo Muninn n'a pas accidentellement copie le dossier
    auto-memory natif Anthropic dans son arborescence.
    Le natif tourne dans ~/.claude/projects/<project>/memory/ — c'est OK qu'il
    existe la, on veut juste qu'il ne soit pas dans le repo lui-meme.
    """
    forbidden = os.path.join(REPO_ROOT, ".claude", "projects")
    assert not os.path.exists(forbidden), (
        f"Dossier auto-memory natif trouve dans le repo : {forbidden}. "
        "Devrait etre dans ~/.claude/projects/, pas dans le repo."
    )

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
    """Chaque hook doit toujours appeler un script Muninn legitime.

    Updated 2026-04-10: les hooks valides incluent maintenant les scripts
    sous .claude/hooks/ ajoutes par les chunks 4, 5, 12 (post_tool_failure,
    subagent_start, pre_tool_use_*). Le test verifie qu'aucun hook ne
    pointe vers un script externe inconnu.
    """
    hooks = settings["hooks"]
    valid_markers = (
        "muninn.py", "_engine.py",
        "bridge_hook.py",
        "post_tool_failure_hook.py",
        "subagent_start_hook.py",
        "pre_tool_use_bash_destructive.py",
        "pre_tool_use_bash_secrets.py",
        "pre_tool_use_edit_hardcode.py",
        # Chunk 15 scaling hooks (audit, edit log, config change)
        "notification_audit_hook.py",
        "post_tool_use_edit_log.py",
        "config_change_hook.py",
    )

    def _extract_commands(entries):
        """Support both simple format and matcher format (PreToolUse)."""
        cmds = []
        for e in entries or []:
            if not isinstance(e, dict):
                continue
            if "command" in e:
                cmds.append(e.get("command", ""))
            elif "hooks" in e:
                for h in e.get("hooks", []):
                    if isinstance(h, dict):
                        cmds.append(h.get("command", ""))
        return cmds

    for hook_name, entries in hooks.items():
        assert isinstance(entries, list) and entries, (
            f"Hook {hook_name} vide ou mal forme"
        )
        cmds = _extract_commands(entries)
        assert cmds, f"Hook {hook_name} aucun command extrait"
        for cmd in cmds:
            assert any(m in cmd for m in valid_markers), (
                f"Hook {hook_name} ne pointe pas vers un script Muninn legitime : {cmd}"
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

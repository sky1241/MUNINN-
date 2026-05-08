"""CHUNK C10 + C11 — env vars documented in CLAUDE.md, README drift fixed.

C10: every MUNINN_* env var actually used in code must appear in
CLAUDE.md (Configuration section).
C11: README must not claim "11 layers" / "zero deps" / etc. — pre-fix
drift items.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C10, §C11
"""
import re
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _env_vars_used_in_code() -> set[str]:
    """Scan code for every MUNINN_* env var referenced as a string literal."""
    found = set()
    for pattern in ("**/*.py", "**/*.toml"):
        for f in REPO.rglob(pattern):
            if any(part in f.parts for part in (".git", "node_modules", "build", "dist")):
                continue
            try:
                src = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.finditer(r'"(MUNINN_[A-Z_]+)"', src):
                found.add(m.group(1))
    return found


def test_all_env_vars_documented():
    """Every MUNINN_* env var used in code must appear in CLAUDE.md."""
    used = _env_vars_used_in_code()
    claude_md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    missing = [v for v in used if v not in claude_md]
    assert not missing, (
        f"Env vars used in code but not documented in CLAUDE.md: {missing}\n"
        f"Add them to the 'Configuration / Variables d'environnement' section."
    )


def test_anthropic_api_key_documented():
    """ANTHROPIC_API_KEY must also be mentioned (it's used by L9)."""
    claude_md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" in claude_md


def test_claude_md_has_configuration_section():
    """CLAUDE.md must have a section with table of env vars."""
    claude_md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Configuration" in claude_md
    assert "Variables d'environnement" in claude_md or "env var" in claude_md.lower()


def test_readme_no_more_11_layers_claim():
    """README must NOT say '11 layers' anymore — there are 12 (L0-L11 + L12)."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    # Only the literal phrase "11 layers" — "12 layers" is fine
    assert "11 layers" not in readme.lower(), (
        "README still claims '11 layers' — should be '12 layers'"
    )


def test_readme_no_zero_deps_lie():
    """README must not claim "zero dependencies" — L9 needs anthropic, L12 needs tiktoken."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    bad_phrases = ["zero dependencies", "zero dependency"]
    for phrase in bad_phrases:
        # Allow nuanced version like "no required dependency" or context
        if phrase in readme.lower():
            # Verify a qualifier is nearby (within 100 chars)
            idx = readme.lower().find(phrase)
            window = readme.lower()[max(0, idx - 100): idx + len(phrase) + 100]
            qualifiers = ["regex-only", "no required", "core only", "optional", "l9", "l12"]
            assert any(q in window for q in qualifiers), (
                f"'{phrase}' in README without nuance — L9 needs anthropic"
            )

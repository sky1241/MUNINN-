"""
CHUNK 2 — Verifie la structure du CLAUDE.md refactore.

Pourquoi : CLAUDE.md est livre comme USER MESSAGE apres le system prompt
(doc officielle Anthropic). Il ne peut pas battre le system prompt mais il
gagne contre les patterns par defaut si format optimise :
  - XML tags = compartiments d'attention
  - Negative examples = inhibent statistiquement les bad reflexes
  - Sandwich top + bottom = primacy + recency bias

Tests :
1. Bloc <MUNINN_RULES> present au top (primacy)
2. Bloc <MUNINN_SANDWICH_RECENCY> present au bottom (recency)
3. Au moins 5 RULE blocks dans MUNINN_RULES
4. Chaque RULE a: name, Directive, Bad reflex, Correction
5. UTF-8 valide
6. CLAUDE.md sub 200 lignes (recommendation officielle Anthropic)
   — soft warning, ne fail pas le test, mais affiche un warn
"""
import os
import re
import warnings

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_MD = os.path.join(REPO_ROOT, "CLAUDE.md")

RECOMMENDED_MAX_LINES = 200  # Anthropic doc: target under 200 lines per CLAUDE.md


@pytest.fixture(scope="module")
def claude_md_text():
    assert os.path.exists(CLAUDE_MD), f"CLAUDE.md missing at {CLAUDE_MD}"
    with open(CLAUDE_MD, "r", encoding="utf-8") as f:
        return f.read()


def test_utf8_valid(claude_md_text):
    """Doit etre UTF-8 valide (sinon Claude Code peut le truncate)."""
    # Si on a pu le lire en utf-8 c'est OK
    assert isinstance(claude_md_text, str)
    assert len(claude_md_text) > 0


def test_top_block_present(claude_md_text):
    """Bloc <MUNINN_RULES priority="USER_OVERRIDE"> doit etre au top."""
    # Tolere whitespace + commentaires HTML avant
    head = claude_md_text[:2000]
    assert '<MUNINN_RULES priority="USER_OVERRIDE">' in head, (
        "Bloc <MUNINN_RULES> manquant ou trop bas dans CLAUDE.md "
        "(doit etre dans les 2000 premiers chars pour primacy bias)"
    )


def test_bottom_block_present(claude_md_text):
    """Bloc <MUNINN_SANDWICH_RECENCY> doit etre au bottom."""
    tail = claude_md_text[-2000:]
    assert "<MUNINN_SANDWICH_RECENCY>" in tail, (
        "Bloc sandwich bottom manquant ou trop haut "
        "(doit etre dans les 2000 derniers chars pour recency bias)"
    )


def test_top_block_closes(claude_md_text):
    """Le bloc top doit etre referme avec </MUNINN_RULES>."""
    assert "</MUNINN_RULES>" in claude_md_text, "Bloc MUNINN_RULES non ferme"


def test_bottom_block_closes(claude_md_text):
    """Le bloc bottom doit etre referme avec </MUNINN_SANDWICH_RECENCY>."""
    assert "</MUNINN_SANDWICH_RECENCY>" in claude_md_text, (
        "Bloc MUNINN_SANDWICH_RECENCY non ferme"
    )


def test_at_least_5_rules(claude_md_text):
    """Doit y avoir au moins 5 <RULE id="N"> blocks."""
    rule_pattern = re.compile(r'<RULE\s+id="(\d+)"\s+name="([^"]+)">')
    matches = rule_pattern.findall(claude_md_text)
    assert len(matches) >= 5, (
        f"Au moins 5 RULE blocks attendus, trouve {len(matches)}"
    )


def test_each_rule_has_directive_reflex_correction(claude_md_text):
    """Chaque RULE doit contenir Directive: + Bad reflex: + Correction:"""
    # Match le contenu de chaque RULE block
    rule_blocks = re.findall(
        r'<RULE\s+id="(\d+)"[^>]*>(.*?)</RULE>',
        claude_md_text,
        re.DOTALL,
    )
    assert rule_blocks, "Aucun RULE block parse"

    for rule_id, body in rule_blocks:
        assert "Directive:" in body, (
            f"RULE id={rule_id} manque 'Directive:'"
        )
        assert "Bad reflex:" in body, (
            f"RULE id={rule_id} manque 'Bad reflex:' (negative example)"
        )
        assert "Correction:" in body, (
            f"RULE id={rule_id} manque 'Correction:'"
        )


def test_rule_ids_unique(claude_md_text):
    """Les id RULE doivent etre uniques."""
    ids = re.findall(r'<RULE\s+id="(\d+)"', claude_md_text)
    assert len(ids) == len(set(ids)), f"RULE ids dupliques : {ids}"


def test_no_repo_hardcode_in_rules(claude_md_text):
    """RULE 5 dit zero hardcode — donc le bloc rules lui-meme ne doit pas
    contenir de chemin Windows en dur autre qu'en exemple negatif."""
    # On extrait juste le bloc MUNINN_RULES
    m = re.search(
        r'<MUNINN_RULES[^>]*>(.*?)</MUNINN_RULES>',
        claude_md_text,
        re.DOTALL,
    )
    assert m, "MUNINN_RULES introuvable"
    rules_body = m.group(1)
    # Le path d'exemple dans RULE 5 est OK car c'est explicitement marque
    # comme "bad reflex". On checke juste qu'on n'a pas de path en dehors
    # des sections "Bad reflex" ou commentaires.
    # Test simple : si "C:/Users/ludov" apparait, doit etre dans une ligne
    # qui contient "Bad reflex" ou "Correction" ou exemple.
    for line in rules_body.splitlines():
        if "C:/Users/ludov" in line or "C:\\Users\\ludov" in line:
            assert any(
                marker in line
                for marker in ("Bad reflex", "Correction", "exemple", "example", "baked")
            ), f"Hardcoded path hors zone d'exemple : {line.strip()}"


def test_under_recommended_line_cap(claude_md_text):
    """
    Soft warning : Anthropic recommande sub 200 lignes pour adherence max.
    Ce test ne fail pas, mais affiche un warning si on depasse.
    """
    line_count = len(claude_md_text.splitlines())
    if line_count > RECOMMENDED_MAX_LINES:
        warnings.warn(
            f"CLAUDE.md fait {line_count} lignes > {RECOMMENDED_MAX_LINES} "
            f"recommandees par Anthropic. Adherence reduite possible.",
            UserWarning,
            stacklevel=2,
        )
    # On n'assert pas — c'est un soft cap


def test_html_comments_present_for_maintainer_notes(claude_md_text):
    """Block-level HTML comments sont strippes a l'injection (Anthropic doc).
    On en utilise pour des notes mainteneur sans coute tokens."""
    assert "<!--" in claude_md_text and "-->" in claude_md_text, (
        "Aucun commentaire HTML — on perd l'opportunite de notes "
        "mainteneur gratuites en tokens"
    )

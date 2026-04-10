"""
CHUNK 6 — Mesure exhaustive : que se passe-t-il si on compresse CLAUDE.md avec Muninn ?

Pourquoi : CLAUDE.md fait 239 lignes, au-dessus du cap 200 recommande par
Anthropic. On a un moteur de compression memoire (Muninn). Question naturelle :
peut-on compresser CLAUDE.md et gagner de la place pour rajouter des regles ?

Risque : CLAUDE.md est un prompt INSTRUCTIONNEL. Chaque mot compte pour la
normativite. Les balises XML des RULES doivent etre intactes, sinon le gain
chunk 2 est perdu. Muninn est concu pour preserver les facts, pas la
normativite. On doit mesurer avant de trancher.

Ce chunk NE MODIFIE PAS CLAUDE.md. Il fait seulement de la mesure sur des
copies temporaires pour permettre une decision a froid.

Tests :
1. Baseline : taille CLAUDE.md actuel (lignes, chars, tokens tiktoken)
2. compress_file complet (L1-L7 + L10 + L11, L9 skip) : mesure reduction
3. Structure XML preservee apres compress_file ?
   - <MUNINN_RULES> present ?
   - 8 <RULE id="N"> presents ?
   - Directive/Bad reflex/Correction presents dans chaque RULE ?
   - <MUNINN_SANDWICH_RECENCY> present ?
4. compress_line sur une RULE isolee : la compression line-level casse-t-elle ?
5. extract_facts sur le memo cousin : les facts ressortent-ils proprement ?
6. Test de sections : ne compresser QUE le memo cousin
7. Token count final vs baseline

Decision : les tests ne FAIL jamais sur des assertions strictes de ratio.
Ils AFFICHENT les mesures et verifient seulement des invariants structurels.
Le verdict (go/no-go pour chunk 7 d'application) sort des mesures imprimees.
"""
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
ENGINE_CORE = REPO_ROOT / "engine" / "core"

if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def _count_tokens(text: str) -> int:
    """Try tiktoken first, fall back to len//4."""
    try:
        from tokenizer import token_count
        return token_count(text)
    except Exception:
        return len(text) // 4


def _structural_report(text: str) -> dict:
    """Return a dict of invariants to check after any transform."""
    return {
        "has_muninn_rules_open": "<MUNINN_RULES" in text,
        "has_muninn_rules_close": "</MUNINN_RULES>" in text,
        "has_sandwich_open": "<MUNINN_SANDWICH_RECENCY>" in text,
        "has_sandwich_close": "</MUNINN_SANDWICH_RECENCY>" in text,
        "rule_count": len(re.findall(r'<RULE\s+id="\d+"', text)),
        "directive_count": text.count("Directive:"),
        "bad_reflex_count": text.count("Bad reflex:"),
        "correction_count": text.count("Correction:"),
        "has_memo_cousin": "Memo pour mon cousin" in text or "cousin" in text.lower(),
        "lines": len(text.splitlines()),
        "chars": len(text),
        "tokens": _count_tokens(text),
    }


def _print_report(label: str, report: dict):
    """Emit a readable block (captured by pytest -s)."""
    print(f"\n--- {label} ---")
    for k, v in report.items():
        print(f"  {k:30s}: {v}")


@pytest.fixture(scope="module")
def muninn_module():
    import muninn
    # Disable L9 (Haiku API) — no credits, deterministic tests
    muninn._SKIP_L9 = True
    return muninn


@pytest.fixture(scope="module")
def claude_md_text():
    assert CLAUDE_MD.exists(), f"CLAUDE.md missing at {CLAUDE_MD}"
    return CLAUDE_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def baseline_report(claude_md_text):
    rep = _structural_report(claude_md_text)
    _print_report("BASELINE (CLAUDE.md current)", rep)
    return rep


# ── Baseline sanity ──────────────────────────────────────────────


def test_baseline_structure_valid(baseline_report):
    """CLAUDE.md current state must pass its own chunk 2 invariants."""
    r = baseline_report
    assert r["has_muninn_rules_open"] and r["has_muninn_rules_close"]
    assert r["has_sandwich_open"] and r["has_sandwich_close"]
    assert r["rule_count"] >= 5
    assert r["directive_count"] >= 5
    assert r["bad_reflex_count"] >= 5
    assert r["correction_count"] >= 5
    assert r["lines"] > 0
    assert r["tokens"] > 0


# ── Full compress_file pipeline ──────────────────────────────────


def test_compress_file_full_pipeline(muninn_module, claude_md_text, baseline_report, tmp_path):
    """
    Run full compress_file() pipeline on a copy of CLAUDE.md.
    Mesure ratio and structural preservation.
    This is the primary decision signal for chunk 7.
    """
    # Copy to isolated tmp dir (compress_file reads from disk)
    tmp_copy = tmp_path / "CLAUDE.md"
    tmp_copy.write_text(claude_md_text, encoding="utf-8")

    compressed = muninn_module.compress_file(tmp_copy)
    assert isinstance(compressed, str)
    assert len(compressed) > 0, "compress_file returned empty — aborted run"

    rep = _structural_report(compressed)
    _print_report("AFTER compress_file (full pipeline, L9 skip)", rep)

    # Ratio report
    ratio_tokens = baseline_report["tokens"] / max(rep["tokens"], 1)
    ratio_lines = baseline_report["lines"] / max(rep["lines"], 1)
    ratio_chars = baseline_report["chars"] / max(rep["chars"], 1)
    print(f"\n  COMPRESSION RATIOS:")
    print(f"    tokens : x{ratio_tokens:.2f} ({baseline_report['tokens']} -> {rep['tokens']})")
    print(f"    lines  : x{ratio_lines:.2f} ({baseline_report['lines']} -> {rep['lines']})")
    print(f"    chars  : x{ratio_chars:.2f} ({baseline_report['chars']} -> {rep['chars']})")

    # Structural preservation verdict (printed, not asserted yet)
    xml_preserved = (
        rep["has_muninn_rules_open"]
        and rep["has_muninn_rules_close"]
        and rep["rule_count"] == baseline_report["rule_count"]
        and rep["directive_count"] == baseline_report["directive_count"]
        and rep["bad_reflex_count"] == baseline_report["bad_reflex_count"]
        and rep["correction_count"] == baseline_report["correction_count"]
        and rep["has_sandwich_open"]
        and rep["has_sandwich_close"]
    )
    print(f"\n  STRUCTURE PRESERVED: {xml_preserved}")
    if not xml_preserved:
        missing = []
        if not rep["has_muninn_rules_open"]:
            missing.append("<MUNINN_RULES open>")
        if not rep["has_muninn_rules_close"]:
            missing.append("</MUNINN_RULES close>")
        if rep["rule_count"] != baseline_report["rule_count"]:
            missing.append(f"RULE count {rep['rule_count']}/{baseline_report['rule_count']}")
        if rep["directive_count"] != baseline_report["directive_count"]:
            missing.append(f"Directive count {rep['directive_count']}/{baseline_report['directive_count']}")
        if rep["bad_reflex_count"] != baseline_report["bad_reflex_count"]:
            missing.append(f"Bad reflex count {rep['bad_reflex_count']}/{baseline_report['bad_reflex_count']}")
        if rep["correction_count"] != baseline_report["correction_count"]:
            missing.append(f"Correction count {rep['correction_count']}/{baseline_report['correction_count']}")
        if not rep["has_sandwich_open"]:
            missing.append("<MUNINN_SANDWICH_RECENCY open>")
        if not rep["has_sandwich_close"]:
            missing.append("</MUNINN_SANDWICH_RECENCY close>")
        print(f"  LOST: {', '.join(missing)}")

    # Also dump the first 400 chars of compressed for visual inspection
    print(f"\n  COMPRESSED HEAD (first 400 chars):\n    {compressed[:400]!r}")
    print(f"\n  COMPRESSED TAIL (last 300 chars):\n    {compressed[-300:]!r}")

    # Save full compressed output for post-mortem reading
    debug_out = REPO_ROOT / ".muninn" / "chunk6_compressed_claude_md.txt"
    debug_out.parent.mkdir(parents=True, exist_ok=True)
    debug_out.write_text(compressed, encoding="utf-8")
    print(f"\n  Full compressed text saved to: {debug_out}")

    # This test does not assert structure preservation — it reports.
    # The chunk 7 go/no-go decision uses these printed measurements.
    assert compressed is not None


# ── compress_line on a single RULE ──────────────────────────────


def test_compress_line_on_rule(muninn_module):
    """
    Take RULE 1 verbatim and pass it through compress_line.
    Does the line-level compression kill the normative wording?
    """
    rule_1 = (
        '<RULE id="1" name="No lazy mode">'
    )
    rule_dir = "  Directive: Re-read Sky's request word by word. Address each point individually."
    rule_bad = "  Bad reflex: Skim, latch onto first bit, answer with vague summary."
    rule_cor = "  Correction: 3 points asked = 3 points answered. Code asked = code shipped."

    print("\n--- compress_line on RULE 1 components ---")
    for label, line in [
        ("opening tag", rule_1),
        ("Directive",   rule_dir),
        ("Bad reflex",  rule_bad),
        ("Correction",  rule_cor),
    ]:
        compressed = muninn_module.compress_line(line)
        ratio_chars = len(line) / max(len(compressed), 1)
        print(f"\n  [{label}]")
        print(f"    IN  ({len(line):3d} chars): {line!r}")
        print(f"    OUT ({len(compressed):3d} chars): {compressed!r}")
        print(f"    ratio: x{ratio_chars:.2f}")


# ── Section-level: what if we only compress the memo cousin? ─────


def test_memo_cousin_section_isolated(muninn_module, claude_md_text, baseline_report):
    """
    The 'Memo pour mon cousin' section is ~70 lines of narrative prose.
    Muninn was designed for this kind of content. Test compressing ONLY
    this section and see if we can drop CLAUDE.md under 200 lines.
    """
    # Extract memo cousin section
    lines = claude_md_text.splitlines()
    memo_start = None
    memo_end = None
    for i, line in enumerate(lines):
        if "Memo pour mon cousin" in line and memo_start is None:
            memo_start = i
        elif memo_start is not None and line.startswith("## ") and "Memo pour mon cousin" not in line:
            memo_end = i
            break
    if memo_end is None:
        memo_end = len(lines)

    assert memo_start is not None, "Memo section not found"
    memo_lines = lines[memo_start:memo_end]
    memo_text = "\n".join(memo_lines)
    print(f"\n--- MEMO COUSIN section ---")
    print(f"  Found: lines {memo_start+1}-{memo_end} ({len(memo_lines)} lines)")
    print(f"  Tokens: {_count_tokens(memo_text)}")

    # Try compress_section on memo
    memo_header = memo_lines[0] if memo_lines else "## Memo pour mon cousin"
    memo_body = memo_lines[1:] if len(memo_lines) > 1 else []
    compressed_memo = muninn_module.compress_section(memo_header, memo_body)

    print(f"\n  compress_section output:")
    print(f"    tokens: {_count_tokens(compressed_memo)}")
    print(f"    lines:  {len(compressed_memo.splitlines())}")
    print(f"    chars:  {len(compressed_memo)}")
    ratio = _count_tokens(memo_text) / max(_count_tokens(compressed_memo), 1)
    print(f"    ratio:  x{ratio:.2f}")
    print(f"\n  Compressed memo head (first 400):\n    {compressed_memo[:400]!r}")

    # What if we replaced the memo with the compressed version?
    new_total_lines = (
        baseline_report["lines"]
        - len(memo_lines)
        + len(compressed_memo.splitlines())
    )
    new_total_tokens = (
        baseline_report["tokens"]
        - _count_tokens(memo_text)
        + _count_tokens(compressed_memo)
    )
    print(f"\n  PROJECTED (if memo replaced):")
    print(f"    lines : {baseline_report['lines']} -> {new_total_lines}")
    print(f"    tokens: {baseline_report['tokens']} -> {new_total_tokens}")
    under_cap = new_total_lines <= 200
    print(f"    under 200 lines cap: {under_cap}")


# ── extract_facts on memo ───────────────────────────────────────


def test_extract_facts_on_memo(muninn_module, claude_md_text):
    """What facts does extract_facts pull from the memo cousin section?"""
    lines = claude_md_text.splitlines()
    memo_start = None
    for i, line in enumerate(lines):
        if "Memo pour mon cousin" in line:
            memo_start = i
            break
    if memo_start is None:
        pytest.skip("Memo section not found")

    memo_text = "\n".join(lines[memo_start:])
    facts = muninn_module.extract_facts(memo_text)
    print(f"\n--- extract_facts on memo ---")
    print(f"  Found {len(facts) if isinstance(facts, (list, dict)) else '-'} facts")
    if isinstance(facts, list):
        for f in facts[:20]:
            print(f"    {f!r}")
    elif isinstance(facts, dict):
        for k, v in list(facts.items())[:20]:
            print(f"    {k}: {v!r}")
    else:
        print(f"    {facts!r}")


# ── Hybrid approach: compress memo only, preserve RULES + sandwich ──


def test_hybrid_compress_memo_only(muninn_module, claude_md_text, baseline_report):
    """
    Hybrid strategy for potential chunk 7:
      - Preserve <MUNINN_RULES>...</MUNINN_RULES> verbatim (normativity critical)
      - Preserve <MUNINN_SANDWICH_RECENCY>...</MUNINN_SANDWICH_RECENCY> verbatim
      - Preserve all prose about Muninn engine (non-instructional facts)
      - Compress ONLY the 'Memo pour mon cousin' section via compress_section

    Reconstructs a proposed new CLAUDE.md and measures it.
    """
    lines = claude_md_text.splitlines()

    # Locate memo cousin section
    memo_start = None
    memo_end = None
    for i, line in enumerate(lines):
        if "Memo pour mon cousin" in line and memo_start is None:
            memo_start = i
        elif memo_start is not None and line.startswith("## ") and "Memo pour mon cousin" not in line:
            memo_end = i
            break
    if memo_end is None:
        memo_end = len(lines)

    # Sanity: the memo block must not overlap with RULES or sandwich
    before_memo = "\n".join(lines[:memo_start])
    memo_block = "\n".join(lines[memo_start:memo_end])
    after_memo = "\n".join(lines[memo_end:])

    assert "<MUNINN_RULES" in before_memo, "RULES must be before memo"
    assert "<MUNINN_SANDWICH_RECENCY>" in after_memo, "sandwich must be after memo"
    assert "<MUNINN_RULES" not in memo_block
    assert "<MUNINN_SANDWICH_RECENCY>" not in memo_block

    # Compress only the memo
    memo_lines = lines[memo_start:memo_end]
    memo_header = memo_lines[0]
    memo_body = memo_lines[1:]
    compressed_memo = muninn_module.compress_section(memo_header, memo_body)

    # Rebuild CLAUDE.md candidate
    new_claude_md = (
        before_memo
        + "\n\n"
        + compressed_memo
        + "\n\n"
        + after_memo
    )

    rep = _structural_report(new_claude_md)
    print("\n--- HYBRID: memo-only compression ---")
    _print_report("AFTER hybrid compress", rep)

    # Ratio
    print(f"\n  HYBRID RATIOS vs baseline:")
    print(f"    lines : {baseline_report['lines']} -> {rep['lines']} "
          f"(saved {baseline_report['lines'] - rep['lines']})")
    print(f"    tokens: {baseline_report['tokens']} -> {rep['tokens']} "
          f"(saved {baseline_report['tokens'] - rep['tokens']})")

    # Strict structural assertions — this IS the chunk 7 gate
    assert rep["has_muninn_rules_open"], "hybrid: RULES open tag lost"
    assert rep["has_muninn_rules_close"], "hybrid: RULES close tag lost"
    assert rep["has_sandwich_open"], "hybrid: sandwich open lost"
    assert rep["has_sandwich_close"], "hybrid: sandwich close lost"
    assert rep["rule_count"] == baseline_report["rule_count"], (
        f"hybrid: RULE count {rep['rule_count']}/{baseline_report['rule_count']}"
    )
    assert rep["directive_count"] == baseline_report["directive_count"], (
        f"hybrid: Directive count {rep['directive_count']}/{baseline_report['directive_count']}"
    )
    assert rep["bad_reflex_count"] == baseline_report["bad_reflex_count"], (
        f"hybrid: Bad reflex count {rep['bad_reflex_count']}/{baseline_report['bad_reflex_count']}"
    )
    assert rep["correction_count"] == baseline_report["correction_count"], (
        f"hybrid: Correction count {rep['correction_count']}/{baseline_report['correction_count']}"
    )

    # Save the candidate for post-mortem reading
    debug_out = REPO_ROOT / ".muninn" / "chunk6_hybrid_candidate.md"
    debug_out.parent.mkdir(parents=True, exist_ok=True)
    debug_out.write_text(new_claude_md, encoding="utf-8")
    print(f"\n  Candidate saved to: {debug_out}")
    print(f"  UNDER 200 LINES: {rep['lines'] <= 200}")


# ── Hybrid with markdown post-fix ────────────────────────────────


def _postfix_muninn_output(compressed: str, original_header: str) -> str:
    """Convert Muninn's `?Section:` artefact back to `## Section` markdown.

    compress_section prepends a state marker (? = unknown) to the header
    because Muninn output is meant for .mn files, not markdown files.
    For CLAUDE.md we want the original H2 header restored.
    """
    lines = compressed.splitlines()
    if not lines:
        return compressed
    # First line is the Muninn-formatted header
    # Replace it with the original markdown H2 header
    clean_header = original_header.strip()
    if not clean_header.startswith("#"):
        clean_header = f"## {clean_header}"
    return "\n".join([clean_header] + lines[1:])


def test_hybrid_with_markdown_postfix(muninn_module, claude_md_text, baseline_report):
    """
    Same as hybrid, but post-fix the Muninn `?Section:` marker back to
    a clean `## Section` markdown header so Claude Code's markdown parser
    still recognizes section boundaries.
    """
    lines = claude_md_text.splitlines()

    memo_start = None
    memo_end = None
    for i, line in enumerate(lines):
        if "Memo pour mon cousin" in line and memo_start is None:
            memo_start = i
        elif memo_start is not None and line.startswith("## ") and "Memo pour mon cousin" not in line:
            memo_end = i
            break
    if memo_end is None:
        memo_end = len(lines)

    before_memo = "\n".join(lines[:memo_start])
    memo_header = lines[memo_start]
    memo_body = lines[memo_start + 1:memo_end]
    after_memo = "\n".join(lines[memo_end:])

    compressed_memo = muninn_module.compress_section(memo_header, memo_body)
    fixed_memo = _postfix_muninn_output(compressed_memo, memo_header)

    # Verify the post-fix actually produces a proper markdown header
    fixed_first_line = fixed_memo.splitlines()[0] if fixed_memo else ""
    assert fixed_first_line.startswith("## "), (
        f"post-fix failed to restore H2: {fixed_first_line!r}"
    )

    new_claude_md = (
        before_memo + "\n\n" + fixed_memo + "\n\n" + after_memo
    )

    rep = _structural_report(new_claude_md)
    print("\n--- HYBRID + markdown post-fix ---")
    _print_report("FINAL candidate for chunk 7", rep)
    print(f"\n  FINAL RATIOS vs baseline:")
    print(f"    lines : {baseline_report['lines']} -> {rep['lines']} "
          f"(saved {baseline_report['lines'] - rep['lines']})")
    print(f"    tokens: {baseline_report['tokens']} -> {rep['tokens']} "
          f"(saved {baseline_report['tokens'] - rep['tokens']})")
    print(f"    UNDER 200 LINES: {rep['lines'] <= 200}")

    # Strict assertions (chunk 7 gate)
    assert rep["has_muninn_rules_open"] and rep["has_muninn_rules_close"]
    assert rep["has_sandwich_open"] and rep["has_sandwich_close"]
    assert rep["rule_count"] == baseline_report["rule_count"]
    assert rep["directive_count"] == baseline_report["directive_count"]
    assert rep["bad_reflex_count"] == baseline_report["bad_reflex_count"]
    assert rep["correction_count"] == baseline_report["correction_count"]

    # Count proper markdown H2 headers
    h2_count = sum(1 for l in new_claude_md.splitlines() if l.startswith("## "))
    baseline_h2 = sum(1 for l in claude_md_text.splitlines() if l.startswith("## "))
    print(f"\n  H2 headers: {baseline_h2} -> {h2_count}")
    assert h2_count == baseline_h2, (
        f"H2 header count changed: {h2_count}/{baseline_h2} — "
        "memo cousin section might have lost its header"
    )

    # Save final candidate for chunk 7 application
    debug_out = REPO_ROOT / ".muninn" / "chunk6_final_candidate.md"
    debug_out.parent.mkdir(parents=True, exist_ok=True)
    debug_out.write_text(new_claude_md, encoding="utf-8")
    print(f"\n  Final candidate saved to: {debug_out}")


# ── Final summary (not an assertion, a summary for Sky) ──────────


def test_print_final_summary(muninn_module, claude_md_text, baseline_report, tmp_path):
    """Synthese finale pour decision chunk 7."""
    tmp_copy = tmp_path / "CLAUDE.md"
    tmp_copy.write_text(claude_md_text, encoding="utf-8")
    compressed = muninn_module.compress_file(tmp_copy)
    rep = _structural_report(compressed)

    xml_preserved = (
        rep["has_muninn_rules_open"]
        and rep["has_muninn_rules_close"]
        and rep["rule_count"] == baseline_report["rule_count"]
        and rep["directive_count"] == baseline_report["directive_count"]
        and rep["bad_reflex_count"] == baseline_report["bad_reflex_count"]
        and rep["correction_count"] == baseline_report["correction_count"]
        and rep["has_sandwich_open"]
        and rep["has_sandwich_close"]
    )

    print("\n" + "=" * 60)
    print("CHUNK 6 FINAL SUMMARY — compress CLAUDE.md?")
    print("=" * 60)
    print(f"  baseline lines : {baseline_report['lines']}")
    print(f"  baseline tokens: {baseline_report['tokens']}")
    print(f"  after lines    : {rep['lines']}")
    print(f"  after tokens   : {rep['tokens']}")
    print(f"  ratio tokens   : x{baseline_report['tokens']/max(rep['tokens'],1):.2f}")
    print(f"  structure OK   : {xml_preserved}")

    if xml_preserved:
        verdict = "GO — full compress_file preserves structure"
    elif rep["rule_count"] == baseline_report["rule_count"]:
        verdict = "PARTIAL — RULE blocks intact but fields damaged"
    else:
        verdict = "NO-GO full compress. Fallback: compress memo cousin only"
    print(f"\n  VERDICT: {verdict}")
    print("=" * 60)

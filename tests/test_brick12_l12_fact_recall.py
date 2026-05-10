"""PHASE B BRICK 12 — pin L12 fact-recall behavior.

Two contracts to lock:

1. With a generous budget (>= original file size), L12 must NOT
   regress fact recall vs L12 OFF on the existing benchmark files.

2. With a tight budget (< original / 2), L12 IS expected to drop
   facts. This is documented limitation BUG-104 — the test asserts
   the loss to make sure we never silently "improve" L12 to claim
   it has no trade-off when in fact it does.

If this test fails because BUG-104 was fixed and tight-budget L12
now preserves facts, that is GREAT — update the test thresholds
upward and update PHASE_B_FACT_RECALL.md.
"""
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
BENCH_DIR = REPO_ROOT / "tests" / "benchmark"


@pytest.fixture(scope="module")
def ml():
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    import muninn  # noqa: F401
    import muninn_layers
    importlib.reload(muninn_layers)
    # Disable L9 (no API call, deterministic)
    muninn_layers._llm_compress = lambda text, context="": text
    return muninn_layers


@pytest.fixture(autouse=True)
def _clean_env():
    saved = os.environ.pop("MUNINN_L12_BUDGET", None)
    yield
    os.environ.pop("MUNINN_L12_BUDGET", None)
    if saved is not None:
        os.environ["MUNINN_L12_BUDGET"] = saved


def _run_recall(ml, sample_name, questions_name):
    sample = BENCH_DIR / sample_name
    questions_path = BENCH_DIR / questions_name
    if not sample.exists() or not questions_path.exists():
        pytest.skip(f"benchmark file missing: {sample_name}")
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    compressed = ml.compress_file(sample)
    answered = 0
    for q in questions:
        ans = q["answer"]
        found = ans.lower() in compressed.lower()
        if not found:
            clean = ans.replace(",", "")
            found = clean.lower() in compressed.lower()
        if not found and any(c.isdigit() for c in ans):
            digits = "".join(c for c in ans if c.isdigit() or c == ".")
            if digits and len(digits) >= 2:
                found = digits in compressed
        if found:
            answered += 1
    return answered, len(questions)


# ── Generous-budget contract: ZERO regression ──────────────────


def test_l12_off_baseline_verbose(ml):
    """Document the L12-OFF baseline so future regressions are visible."""
    answered, total = _run_recall(ml, "verbose_memory.md", "questions_verbose.json")
    assert answered == 15 and total == 15, (
        f"verbose_memory L12 OFF baseline drift: {answered}/{total} (was 15/15)"
    )


def test_l12_huge_budget_no_regression_verbose(ml):
    """L12 with huge budget must keep all facts (same as OFF)."""
    os.environ["MUNINN_L12_BUDGET"] = "5000"
    answered, total = _run_recall(ml, "verbose_memory.md", "questions_verbose.json")
    assert answered == 15, (
        f"L12 with huge budget regressed verbose_memory: {answered}/{total}"
    )


def test_l12_off_baseline_session(ml):
    answered, total = _run_recall(ml, "sample_session.md", "questions_session.json")
    assert answered == 12 and total == 15, (
        f"sample_session L12 OFF baseline drift: {answered}/{total} (was 12/15)"
    )


def test_l12_huge_budget_no_regression_session(ml):
    os.environ["MUNINN_L12_BUDGET"] = "5000"
    answered, total = _run_recall(ml, "sample_session.md", "questions_session.json")
    assert answered == 12, (
        f"L12 with huge budget regressed sample_session: {answered}/{total}"
    )


def test_l12_huge_budget_no_regression_compact(ml):
    os.environ["MUNINN_L12_BUDGET"] = "5000"
    answered, total = _run_recall(ml, "sample_compact.md", "questions_compact.json")
    assert answered == 8


# ── Tight-budget contract: BUG-104 documents the loss ──────────


def test_l12_tight_budget_loses_facts_verbose_bug_104(ml):
    """BUG-104 LEGACY-PATH pin (post-fix 2026-05-10):
    quand `_REPO_PATH` est None (ex: pytest sans setup explicite), le spill
    ne fire pas et L12 retombe sur la legacy path qui DROP les chunks
    must-keep oversized. Ce test pin ce comportement legacy.

    Pour vérifier le FIX (spill actif), voir test_bug104_spill_recall_improvement
    ci-dessous : avec `_REPO_PATH = tmp_path` set, recall remonte à >= 13/15
    (vs 6/15 ici en legacy path).
    """
    os.environ["MUNINN_L12_BUDGET"] = "500"
    answered, total = _run_recall(ml, "verbose_memory.md", "questions_verbose.json")
    # Empirically measured 2026-04-10 PRE-fix: 6/15 (40%)
    # Post-fix: same when _REPO_PATH=None (legacy path no-op spill).
    # When _REPO_PATH set, see test_bug104_spill_recall_improvement.
    assert 3 <= answered <= 12, (
        f"verbose_memory at b=500 (legacy path, no _REPO_PATH) returned "
        f"{answered}/15 — outside legacy envelope [3, 12]. Si > 12 alors le "
        f"spill a fire (_REPO_PATH leaked from test isolation). Si < 3 alors "
        f"l'algo legacy a régressé. Cf. BUGS.md BUG-104 FIXED entry."
    )


def test_l12_tight_budget_loses_facts_session_bug_104(ml):
    """BUG-104 LEGACY-PATH pin sur sample_session (post-fix 2026-05-10).
    Voir docstring de test_l12_tight_budget_loses_facts_verbose_bug_104.
    """
    os.environ["MUNINN_L12_BUDGET"] = "500"
    answered, total = _run_recall(ml, "sample_session.md", "questions_session.json")
    # Empirically measured 2026-04-10 PRE-fix: 9/15 (60%)
    # Post-fix: same when _REPO_PATH=None (legacy path no-op spill).
    assert 6 <= answered <= 13, (
        f"sample_session at b=500 returned {answered}/15 — outside legacy "
        f"envelope [6, 13]. Cf. BUGS.md BUG-104 FIXED entry."
    )


def test_phase_b_fact_recall_doc_exists():
    """The benchmark results doc must exist and be non-trivial."""
    doc = BENCH_DIR / "PHASE_B_FACT_RECALL.md"
    assert doc.exists(), "PHASE_B_FACT_RECALL.md missing"
    text = doc.read_text(encoding="utf-8")
    assert "BUG-104" in text
    assert "verbose_memory" in text
    assert "100.0%" in text and "40.0%" in text  # the headline numbers


# ── BUG-104 spill-to-tree fix tests (2026-05-10) ────────────────────────────


@pytest.fixture
def _spill_repo(tmp_path, monkeypatch):
    """Setup a tmp repo with .muninn/tree/ + tree.json for spill tests.

    BUG-104 fix : the spill helper writes new branches to the tree, so we
    need an isolated tmp repo to avoid polluting the real .muninn/.
    """
    tree_dir = tmp_path / ".muninn" / "tree"
    tree_dir.mkdir(parents=True)
    tree_json = tree_dir / "tree.json"
    tree_json.write_text(json.dumps({
        "version": 2,
        "budget": 30000,
        "nodes": {"root": {"file": "root.mn", "lines": 5,
                            "tags": [], "children": []}},
        "updated": "2026-05-10",
    }))
    (tree_dir / "root.mn").write_text("# root\nfact: x\n")

    import muninn
    monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)
    if hasattr(muninn, "_refresh_tree_paths"):
        muninn._refresh_tree_paths()
    return tmp_path


def test_bug104_spill_creates_branches_at_tight_budget(ml, _spill_repo):
    """BUG-104 fix: at b=500 on verbose_memory.md, must-keep chunks that
    don't fit must be SPILLED to .muninn/tree/ as new branches (not lost)."""
    sample = BENCH_DIR / "verbose_memory.md"
    if not sample.exists():
        pytest.skip("benchmark file missing")
    os.environ["MUNINN_L12_BUDGET"] = "500"

    tree_dir = _spill_repo / ".muninn" / "tree"
    branches_before = {p.stem for p in tree_dir.glob("b*.mn")}
    _ = ml.compress_file(sample)
    branches_after = {p.stem for p in tree_dir.glob("b*.mn")}
    new_branches = branches_after - branches_before
    assert new_branches, (
        f"BUG-104 spill did not fire on tight budget — no new branches in "
        f"{tree_dir}. Expected at least 1 spilled branch."
    )


def test_bug104_spill_branch_files_contain_facts(ml, _spill_repo):
    """Spill branch .mn files must contain L12_SPILL header + actual fact content."""
    sample = BENCH_DIR / "verbose_memory.md"
    if not sample.exists():
        pytest.skip("benchmark file missing")
    os.environ["MUNINN_L12_BUDGET"] = "500"
    _ = ml.compress_file(sample)
    tree_dir = _spill_repo / ".muninn" / "tree"
    spill_files = sorted(p for p in tree_dir.glob("b*.mn") if p.name != "root.mn")
    assert spill_files, "No spill files found"
    first = spill_files[0].read_text(encoding="utf-8")
    assert "## L12_SPILL" in first, f"Spill marker missing in {spill_files[0]}"
    # Body must be non-trivial (more than just the header)
    assert len(first.split("\n")) >= 3, f"Spill file {spill_files[0]} too short"


def test_bug104_spill_tree_json_metadata(ml, _spill_repo):
    """Spill branches must be registered in tree.json with valid metadata."""
    sample = BENCH_DIR / "verbose_memory.md"
    if not sample.exists():
        pytest.skip("benchmark file missing")
    os.environ["MUNINN_L12_BUDGET"] = "500"
    _ = ml.compress_file(sample)

    tree_json = _spill_repo / ".muninn" / "tree" / "tree.json"
    tree = json.loads(tree_json.read_text())
    spilled_nodes = {n: d for n, d in tree["nodes"].items()
                     if d.get("spilled_from_l12") is True}
    assert spilled_nodes, "No spilled_from_l12 marker found in tree.json"
    sample_node = next(iter(spilled_nodes.values()))
    # Required keys
    for key in ("file", "lines", "tags", "temperature", "created", "hash"):
        assert key in sample_node, f"Missing key '{key}' in spilled node"
    # Tags should contain at least one extracted concept
    assert isinstance(sample_node["tags"], list)


def test_bug104_spill_recall_improvement(ml, _spill_repo):
    """The reason d'être of BUG-104 fix : combined fact recall (output + spill
    branches) must exceed the pre-fix 6/15 envelope on verbose_memory at b=500."""
    sample = BENCH_DIR / "verbose_memory.md"
    questions_path = BENCH_DIR / "questions_verbose.json"
    if not sample.exists() or not questions_path.exists():
        pytest.skip("benchmark file missing")
    os.environ["MUNINN_L12_BUDGET"] = "500"
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    compressed = ml.compress_file(sample)
    # Combine main output + spill branch contents (boot would do this on query)
    tree_dir = _spill_repo / ".muninn" / "tree"
    spill_text = ""
    for p in tree_dir.glob("b*.mn"):
        if p.name != "root.mn":
            spill_text += "\n" + p.read_text(encoding="utf-8")
    combined = compressed + spill_text

    answered = 0
    for q in questions:
        ans = q["answer"]
        if ans.lower() in combined.lower():
            answered += 1
    # Pre-fix envelope was 3-12. Post-fix with spill should exceed 12.
    assert answered >= 13, (
        f"BUG-104 fix did not improve recall: {answered}/15 (need >= 13). "
        f"Either spill broke or extract_tags doesn't capture the facts. "
        f"Check spill .mn files in {tree_dir}."
    )


def test_bug104_spill_disabled_by_env_var(ml, _spill_repo):
    """MUNINN_L12_NO_SPILL=1 must disable the spill (backward compat / opt-out)."""
    sample = BENCH_DIR / "verbose_memory.md"
    if not sample.exists():
        pytest.skip("benchmark file missing")
    os.environ["MUNINN_L12_BUDGET"] = "500"
    os.environ["MUNINN_L12_NO_SPILL"] = "1"
    try:
        _ = ml.compress_file(sample)
        tree_dir = _spill_repo / ".muninn" / "tree"
        spill_files = [p for p in tree_dir.glob("b*.mn") if p.name != "root.mn"]
        assert not spill_files, (
            f"L12_NO_SPILL=1 should disable spill but found {len(spill_files)} "
            f"branches in {tree_dir}"
        )
    finally:
        os.environ.pop("MUNINN_L12_NO_SPILL", None)

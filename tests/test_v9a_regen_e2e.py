"""V9A+ REGENERATION — End-to-End Tests

Protocole: cycle complet create → die → prune → boot → verify.
Question fondamentale: les faits survivent-ils a la mort d'une branche
ET sont-ils retrouvables par boot() ?

12 bornes strictes. Ref: docs/PROMPT_V9A_REGEN.md
"""
import sys, os, json, tempfile, shutil, time, re
from pathlib import Path

import muninn

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  {name} PASS{': ' + detail if detail else ''}")
    else:
        FAIL += 1
        print(f"  {name} FAIL{': ' + detail if detail else ''}")


def _make_repo(branches_spec):
    """Create a temp repo with tree, branches, and minimal mycelium.

    branches_spec: list of dicts with keys:
        name, content, last_access, access_count, tags, usefulness, temperature
    Returns (tmpdir Path, tree_dir Path)
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_regen_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tmpdir / ".muninn" / "sessions").mkdir(parents=True, exist_ok=True)

    # Root
    root_text = "# root\ntest project for V9A+ regeneration validation\n"
    (tree_dir / "root.mn").write_text(root_text, encoding="utf-8")

    nodes = {
        "root": {
            "type": "root", "file": "root.mn", "lines": 2, "max_lines": 100,
            "children": [b["name"] for b in branches_spec],
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 1,
            "tags": [], "hash": "00000000",
        }
    }

    for b in branches_spec:
        fname = f"{b['name']}.mn"
        (tree_dir / fname).write_text(b["content"], encoding="utf-8")
        nodes[b["name"]] = {
            "type": "branch", "file": fname,
            "lines": b["content"].count("\n") + 1, "max_lines": 150,
            "children": [],
            "last_access": b.get("last_access", "2024-01-01"),
            "access_count": b.get("access_count", 0),
            "tags": b.get("tags", []),
            "temperature": b.get("temperature", 0.0),
            "usefulness": b.get("usefulness", 0.1),
            "hash": "00000000",
        }

    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"),
            "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    return tmpdir, tree_dir


def _run_prune(tmpdir):
    """Run real prune on temp repo, return updated tree dict."""
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()
    try:
        muninn.prune(dry_run=False)
        tree = json.loads(
            (tmpdir / ".muninn" / "tree" / "tree.json").read_text(encoding="utf-8"))
        return tree
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()


def _run_boot(tmpdir, query):
    """Run boot on temp repo with query, return loaded text."""
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()
    try:
        return muninn.boot(query)
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()


# ============================================================
# REGEN.1 — Tagged facts extracted from dying branch
# ============================================================
def test_regen_1_facts_extracted():
    """D>/B>/F>/E> lines are extracted from the dead branch's .mn file."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_l9_api",
            "content": (
                "# L9 API session\n"
                "D> switched to section-chunked R1-Compress for texts >8K\n"
                "B> L9 API: x4.4 avg on 230 files, $0.21 total cost\n"
                "F> L9 prompt: 847 tokens system, 200 tokens user template\n"
                "E> BUG: chunking failed when no ## headers, fixed fallback to line-split\n"
                "A> added retry logic for Haiku rate limits\n"
                "some narrative about debugging the chunking issue\n"
                "more context about testing different prompt lengths\n"
            ),
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["compression", "pipeline"],  # all tags also in survivor -> V9B won't protect
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_pipeline",
            "content": "# Compression pipeline\nactive development on compression layers\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 10,
            "tags": ["compression", "pipeline", "layers"],
            "usefulness": 0.8, "temperature": 0.9,
        },
    ])
    try:
        tree = _run_prune(tmpdir)

        # Dead branch gone
        dead_gone = "dead_l9_api" not in tree["nodes"]

        # Read survivor content
        survivor_text = (tree_dir / "survivor_pipeline.mn").read_text(encoding="utf-8")

        # Check: all 5 tagged facts present in survivor
        has_d = "switched to section-chunked" in survivor_text
        has_b = "x4.4 avg on 230 files" in survivor_text
        has_f = "847 tokens system" in survivor_text
        has_e = "chunking failed when no ## headers" in survivor_text
        has_a = "retry logic for Haiku" in survivor_text

        facts_found = sum([has_d, has_b, has_f, has_e, has_a])
        check("REGEN.1", dead_gone and facts_found == 5,
              f"dead_gone={dead_gone}, facts_found={facts_found}/5")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.2 — Untagged lines NOT copied
# ============================================================
def test_regen_2_untagged_excluded():
    """Narrative lines (no D>/B>/F>/E>/A> tag) must NOT be in survivor."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_debug",
            "content": (
                "# Debug session\n"
                "D> decided to use SQLite instead of JSON\n"
                "lots of back and forth about the decision\n"
                "tried several approaches before settling\n"
                "narrative about the debugging process\n"
            ),
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["sqlite"],
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_storage",
            "content": "# Storage layer\nactive work on data persistence\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 8,
            "tags": ["sqlite", "storage"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        _run_prune(tmpdir)
        survivor_text = (tree_dir / "survivor_storage.mn").read_text(encoding="utf-8")

        has_decision = "decided to use SQLite" in survivor_text
        has_narrative1 = "back and forth" in survivor_text
        has_narrative2 = "several approaches" in survivor_text
        has_narrative3 = "debugging process" in survivor_text

        check("REGEN.2", has_decision and not has_narrative1
              and not has_narrative2 and not has_narrative3,
              f"decision={has_decision}, narrative_leaked={has_narrative1 or has_narrative2 or has_narrative3}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.3 — REGEN header present
# ============================================================
def test_regen_3_header_present():
    """Section '## REGEN: dead_name (date)' is in the survivor after injection."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_metrics",
            "content": "# Metrics\nB> benchmark 37/40 facts 92%\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["benchmark"],
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_bench",
            "content": "# Benchmark results\nactive benchmark tracking\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["benchmark", "metrics"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        _run_prune(tmpdir)
        survivor_text = (tree_dir / "survivor_bench.mn").read_text(encoding="utf-8")

        has_regen_header = bool(re.search(r"## REGEN: dead_metrics \(\d{4}-\d{2}-\d{2}\)", survivor_text))
        check("REGEN.3", has_regen_header,
              f"header_found={has_regen_header}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.4 — Survivor chosen by mycelium proximity
# ============================================================
def test_regen_4_mycelium_proximity():
    """When 2 survivors exist, facts go to the semantically closest one."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_api_cost",
            "content": "# API costs\nB> L9 total cost: $0.21 for 230 files\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["api", "endpoints"],  # all tags also in survivor_api -> V9B won't protect
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_api",
            "content": "# API management\nendpoint configuration and rate limits\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["api", "endpoints"],
            "usefulness": 0.7, "temperature": 0.8,
        },
        {
            "name": "survivor_unrelated",
            "content": "# UI dashboard\nbuttons and layouts\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["ui", "dashboard"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        _run_prune(tmpdir)
        api_text = (tree_dir / "survivor_api.mn").read_text(encoding="utf-8")
        ui_text = (tree_dir / "survivor_unrelated.mn").read_text(encoding="utf-8")

        fact_in_api = "$0.21" in api_text
        fact_in_ui = "$0.21" in ui_text

        # Fact should be in api survivor (tag overlap "api"), not in ui survivor
        # If mycelium doesn't know these concepts, fallback B (tag overlap) should work
        check("REGEN.4", fact_in_api and not fact_in_ui,
              f"in_api={fact_in_api}, in_ui={fact_in_ui}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.5 — Missing .mn file: fallback to tag-only, no crash
# ============================================================
def test_regen_5_missing_mn_no_crash():
    """Dead branch with no .mn file on disk: falls back to V9A tag-only, doesn't crash."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_ghost",
            "content": "# Ghost\nD> some important decision\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["ghost"],
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_active",
            "content": "# Active\nworking on stuff\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["ghost", "active"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        # Delete the .mn file BEFORE prune
        ghost_file = tree_dir / "dead_ghost.mn"
        if ghost_file.exists():
            ghost_file.unlink()

        # Should not crash
        tree = _run_prune(tmpdir)
        no_crash = True
        dead_gone = "dead_ghost" not in tree["nodes"]
        check("REGEN.5", no_crash and dead_gone,
              f"no_crash=True, dead_removed={dead_gone}")
    except Exception as e:
        check("REGEN.5", False, f"crashed: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.6 — No duplication: same fact injected 2x = present 1x
# ============================================================
def test_regen_6_no_duplication():
    """If survivor already has a fact, it's not duplicated."""
    the_fact = "B> compression ratio x4.1 on verbose text"
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_dup",
            "content": f"# Dup test\n{the_fact}\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["compression"],
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_has_fact",
            "content": f"# Survivor\nalready has this fact:\n{the_fact}\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["compression"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        _run_prune(tmpdir)
        survivor_text = (tree_dir / "survivor_has_fact.mn").read_text(encoding="utf-8")
        count = survivor_text.count(the_fact)
        check("REGEN.6", count == 1,
              f"fact_count={count} (expected 1)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.7 — Budget: >200 lines triggers L10+L11 recompression
# ============================================================
def test_regen_7_budget_recompression():
    """Survivor exceeding 200 lines after injection gets recompressed."""
    # Build a survivor with 195 lines already
    survivor_lines = ["# Big survivor"] + [f"F> metric_{i}: value_{i}" for i in range(194)]
    survivor_content = "\n".join(survivor_lines) + "\n"

    # Dead branch adds 10 more tagged facts -> total > 200
    dead_facts = [f"B> measurement_{i}: result_{i}" for i in range(10)]
    dead_content = "# Dead big\n" + "\n".join(dead_facts) + "\n"

    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_big",
            "content": dead_content,
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["metrics"],
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_big",
            "content": survivor_content,
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["metrics"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        _run_prune(tmpdir)
        final_text = (tree_dir / "survivor_big.mn").read_text(encoding="utf-8")
        line_count = final_text.count("\n")

        # After L10+L11, should be <= 200 lines OR at least fewer than 195+10+header
        raw_expected = 195 + 10 + 2  # original + new facts + REGEN header + blank
        was_compressed = line_count < raw_expected

        check("REGEN.7", was_compressed,
              f"final_lines={line_count}, raw_expected={raw_expected}, compressed={was_compressed}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.8 — Idempotent: prune() x2 doesn't duplicate facts
# ============================================================
def test_regen_8_idempotent():
    """Running prune twice doesn't produce duplicate REGEN sections."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_once",
            "content": "# Die once\nD> critical decision about architecture\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["architecture"],
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_arch",
            "content": "# Architecture\nsystem design notes\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 10,
            "tags": ["architecture", "design"],
            "usefulness": 0.8, "temperature": 0.9,
        },
    ])
    try:
        # First prune: dead_once dies, facts migrate
        _run_prune(tmpdir)

        # Second prune: survivor_arch is still alive, no dead branches
        _run_prune(tmpdir)

        survivor_text = (tree_dir / "survivor_arch.mn").read_text(encoding="utf-8")
        regen_count = survivor_text.count("## REGEN:")
        fact_count = survivor_text.count("critical decision about architecture")

        check("REGEN.8", regen_count <= 1 and fact_count <= 1,
              f"regen_headers={regen_count}, fact_copies={fact_count}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.9 — Full cycle: create → die → prune → boot → find
# ============================================================
def test_regen_9_full_cycle_boot_finds_facts():
    """End-to-end: facts from a dead branch are retrievable via boot()."""
    # The key fact we want to survive and be found
    key_fact = "B> L9 API: x4.4 avg on 230 files, $0.21 total cost"

    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_l9_session",
            "content": f"# L9 session\n{key_fact}\nD> use R1-Compress for large texts\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["compression", "pipeline"],  # all tags also in survivor -> V9B won't protect
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_compress",
            "content": "# Compression work\nactive compression pipeline development\nL1-L7 regex layers working\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 10,
            "tags": ["compression", "pipeline", "regex"],
            "usefulness": 0.8, "temperature": 0.9,
        },
    ])
    try:
        # Step 1: prune — dead_l9_session dies, facts migrate
        _run_prune(tmpdir)

        # Step 2: verify migration happened
        survivor_text = (tree_dir / "survivor_compress.mn").read_text(encoding="utf-8")
        fact_migrated = "x4.4 avg" in survivor_text

        # Step 3: boot with query related to the dead content
        boot_output = _run_boot(tmpdir, "L9 API compression cost")
        fact_in_boot = "x4.4" in boot_output or "4.4" in boot_output

        check("REGEN.9", fact_migrated and fact_in_boot,
              f"migrated={fact_migrated}, in_boot={fact_in_boot}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.10 — Dead concept still accessible via boot
# ============================================================
def test_regen_10_dead_concept_accessible():
    """After regen, boot('dead_concept') still finds the facts in the survivor."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "dead_sqlite_migration",
            "content": (
                "# SQLite migration\n"
                "D> migrated from JSON to SQLite for mycelium storage\n"
                "F> mycelium.db: 657MB vs 946MB JSON (-30%)\n"
            ),
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["sqlite", "migration"],
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_storage",
            "content": "# Storage\ndata persistence layer for muninn\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 8,
            "tags": ["storage", "sqlite", "persistence"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        _run_prune(tmpdir)
        boot_output = _run_boot(tmpdir, "sqlite migration")

        has_migration = "JSON to SQLite" in boot_output or "657MB" in boot_output
        check("REGEN.10", has_migration,
              f"migration_fact_found={has_migration}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.11 — Multi-death: 3 branches die, each goes to different survivor
# ============================================================
def test_regen_11_multi_death():
    """3 branches die simultaneously, facts route to separate survivors by tag affinity."""
    tmpdir, tree_dir = _make_repo([
        # 3 dead branches, each with unique topic
        {
            "name": "dead_api",
            "content": "# API\nB> api latency: 230ms p99\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["api", "endpoints"],  # shared with surv_api
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "dead_ui",
            "content": "# UI\nD> switched to dark mode default\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["ui", "frontend"],  # shared with surv_ui
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "dead_db",
            "content": "# Database\nF> postgres connection pool: 20 max\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["database", "queries"],  # shared with surv_db
            "usefulness": 0.1, "temperature": 0.0,
        },
        # 3 survivors, each matching one dead branch
        {
            "name": "surv_api",
            "content": "# API layer\nendpoint management\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["api", "endpoints"],
            "usefulness": 0.7, "temperature": 0.8,
        },
        {
            "name": "surv_ui",
            "content": "# UI work\nfrontend components\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["ui", "frontend"],
            "usefulness": 0.7, "temperature": 0.8,
        },
        {
            "name": "surv_db",
            "content": "# Database ops\nquery optimization\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["database", "queries"],
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        tree = _run_prune(tmpdir)

        api_text = (tree_dir / "surv_api.mn").read_text(encoding="utf-8")
        ui_text = (tree_dir / "surv_ui.mn").read_text(encoding="utf-8")
        db_text = (tree_dir / "surv_db.mn").read_text(encoding="utf-8")

        api_fact = "230ms p99" in api_text
        ui_fact = "dark mode" in ui_text
        db_fact = "connection pool" in db_text

        # Each fact should route to its matching survivor
        check("REGEN.11", api_fact and ui_fact and db_fact,
              f"api={api_fact}, ui={ui_fact}, db={db_fact}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# REGEN.12 — V9B sole-carrier: NOT deleted, NOT regenerated
# ============================================================
def test_regen_12_v9b_sole_carrier_protected():
    """Sole-carrier branch is demoted to cold by V9B, NOT passed to V9A+ regen."""
    tmpdir, tree_dir = _make_repo([
        {
            "name": "sole_carrier",
            "content": "# Sole carrier\nD> unique knowledge about quantum encryption\n",
            "last_access": "2024-01-01", "access_count": 0,
            "tags": ["quantum_encryption"],  # UNIQUE tag, no other branch has it
            "usefulness": 0.1, "temperature": 0.0,
        },
        {
            "name": "survivor_normal",
            "content": "# Normal survivor\nstandard operations\n",
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 5,
            "tags": ["operations"],  # no "quantum_encryption"
            "usefulness": 0.7, "temperature": 0.8,
        },
    ])
    try:
        tree = _run_prune(tmpdir)

        # V9B should protect sole_carrier (demote to cold, not delete)
        sole_survived = "sole_carrier" in tree["nodes"]
        sole_file_exists = (tree_dir / "sole_carrier.mn").exists()

        # Survivor should NOT have REGEN section (sole carrier wasn't killed)
        survivor_text = (tree_dir / "survivor_normal.mn").read_text(encoding="utf-8")
        no_regen = "REGEN" not in survivor_text

        check("REGEN.12", sole_survived and sole_file_exists and no_regen,
              f"sole_alive={sole_survived}, file={sole_file_exists}, no_regen={no_regen}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("V9A+ REGENERATION — End-to-End Tests (12 bornes)")
    print("=" * 60)
    print()

    print("[Extraction & Filtering]")
    test_regen_1_facts_extracted()
    test_regen_2_untagged_excluded()
    test_regen_3_header_present()

    print("\n[Routing & Fallback]")
    test_regen_4_mycelium_proximity()
    test_regen_5_missing_mn_no_crash()

    print("\n[Safety & Integrity]")
    test_regen_6_no_duplication()
    test_regen_7_budget_recompression()
    test_regen_8_idempotent()

    print("\n[End-to-End Cycle]")
    test_regen_9_full_cycle_boot_finds_facts()
    test_regen_10_dead_concept_accessible()

    print("\n[Multi-branch & V9B Interaction]")
    test_regen_11_multi_death()
    test_regen_12_v9b_sole_carrier_protected()

    print()
    print("=" * 60)
    print(f"RESULTAT: {PASS} PASS, {FAIL} FAIL / 12 bornes")
    print("=" * 60)
    if FAIL > 0:
        sys.exit(1)

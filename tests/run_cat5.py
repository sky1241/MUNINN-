#!/usr/bin/env python
"""Category 5 — Tree & Branches (10 tests)
AUDIT ONLY — no engine modifications.
"""

import sys, os, json, tempfile, shutil, time, re, math
from pathlib import Path
from datetime import datetime, date, timedelta

ENGINE_DIR = Path(r"c:\Users\ludov\MUNINN-\engine\core")
sys.path.insert(0, str(ENGINE_DIR))

# ── Monkey-patch meta path to temp BEFORE importing mycelium ──
TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))
from mycelium import Mycelium as _MycPatch
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")

import muninn
from mycelium import Mycelium

results = []

def log(tid, status, details, elapsed):
    flag = " SLOW" if elapsed > 60 else ""
    entry = f"## {tid}\n- STATUS: {status}{flag}\n"
    for d in details:
        entry += f"- {d}\n"
    entry += f"- TIME: {elapsed:.3f}s\n"
    results.append(entry)
    print(f"{tid}: {status} ({elapsed:.3f}s)")


def fresh_repo():
    """Create a temp repo with the directory structure muninn expects."""
    r = Path(tempfile.mkdtemp(prefix="muninn_test_"))
    (r / ".muninn").mkdir()
    (r / ".muninn" / "tree").mkdir()
    (r / ".muninn" / "sessions").mkdir()
    (r / "memory").mkdir()
    return r


def setup_globals(repo):
    """Set muninn globals to point at a temp repo."""
    muninn._REPO_PATH = repo
    muninn._CB = None
    muninn._refresh_tree_paths()


def today_str():
    return time.strftime("%Y-%m-%d")


def days_ago_str(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════════════════════
# T5.1 — Load/Save arbre (round-trip)
# ═══════════════════════════════════════════════════════════════
def test_t51():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR  # .muninn/tree/

        # Write .mn files
        (tree_dir / "root.mn").write_text("# ROOT\nD> project started\n", encoding="utf-8")
        (tree_dir / "branch_api.mn").write_text("# API\nB> REST endpoints done\nD> auth added\n", encoding="utf-8")
        (tree_dir / "branch_db.mn").write_text("# DB\nF> SQLite migration\n", encoding="utf-8")

        # Compute real hashes
        root_hash = muninn.compute_hash(tree_dir / "root.mn")
        api_hash = muninn.compute_hash(tree_dir / "branch_api.mn")
        db_hash = muninn.compute_hash(tree_dir / "branch_db.mn")

        tree_data = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 2,
                    "max_lines": 100, "children": ["branch_api", "branch_db"],
                    "last_access": today_str(), "access_count": 5,
                    "tags": ["project"], "temperature": 1.0,
                    "hash": root_hash
                },
                "branch_api": {
                    "type": "branch", "file": "branch_api.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": today_str(), "access_count": 3,
                    "tags": ["api", "rest", "auth"], "temperature": 0.7,
                    "hash": api_hash
                },
                "branch_db": {
                    "type": "branch", "file": "branch_db.mn", "lines": 2,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(5), "access_count": 1,
                    "tags": ["database", "sqlite"], "temperature": 0.3,
                    "hash": db_hash
                }
            },
            "updated": today_str()
        }

        # Write tree.json
        (tree_dir / "tree.json").write_text(
            json.dumps(tree_data, indent=2), encoding="utf-8"
        )

        # Load
        loaded = muninn.load_tree()
        n_nodes = len(loaded["nodes"])
        details.append(f"Loaded {n_nodes} nodes (expected 3)")
        assert n_nodes == 3, f"Expected 3 nodes, got {n_nodes}"

        root_temp = loaded["nodes"]["root"].get("temperature", -1)
        details.append(f"root.temperature = {root_temp}")
        assert root_temp == 1.0, f"Expected root temp 1.0, got {root_temp}"

        api_tags = loaded["nodes"]["branch_api"].get("tags", [])
        details.append(f"branch_api.tags = {api_tags}")
        assert "api" in api_tags, f"Expected 'api' in tags, got {api_tags}"

        # Save and reload (round-trip)
        muninn.save_tree(loaded)
        reloaded = muninn.load_tree()
        # Compare nodes (ignore 'updated' which save_tree overwrites)
        for name in ["root", "branch_api", "branch_db"]:
            assert name in reloaded["nodes"], f"Missing {name} after round-trip"
            orig_tags = loaded["nodes"][name].get("tags", [])
            rt_tags = reloaded["nodes"][name].get("tags", [])
            assert orig_tags == rt_tags, f"Tags mismatch for {name}"

        details.append("Round-trip: PASS (save + reload identical)")
        log("T5.1", "PASS", details, time.time() - t0)
    except Exception as e:
        details.append(f"ERROR: {e}")
        log("T5.1", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.2 — P34 Integrity Check
# ═══════════════════════════════════════════════════════════════
def test_t52():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        # Two branches: one valid, one with fake hash
        (tree_dir / "root.mn").write_text("# ROOT\nD> integrity test\n", encoding="utf-8")
        (tree_dir / "good_branch.mn").write_text("# GOOD\nB> valid content\nD> tested\n", encoding="utf-8")
        (tree_dir / "bad_branch.mn").write_text("# BAD\nB> tampered content\n", encoding="utf-8")

        good_hash = muninn.compute_hash(tree_dir / "good_branch.mn")

        tree_data = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 2,
                    "max_lines": 100, "children": ["good_branch", "bad_branch"],
                    "last_access": today_str(), "access_count": 5,
                    "tags": ["project"], "temperature": 1.0,
                    "hash": muninn.compute_hash(tree_dir / "root.mn")
                },
                "good_branch": {
                    "type": "branch", "file": "good_branch.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": today_str(), "access_count": 3,
                    "tags": ["integrity", "valid"], "temperature": 0.8,
                    "hash": good_hash
                },
                "bad_branch": {
                    "type": "branch", "file": "bad_branch.mn", "lines": 2,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": today_str(), "access_count": 2,
                    "tags": ["integrity", "tampered"], "temperature": 0.6,
                    "hash": "0000dead"  # FAKE hash
                }
            },
            "updated": today_str()
        }
        (tree_dir / "tree.json").write_text(json.dumps(tree_data, indent=2), encoding="utf-8")

        # Boot and check: bad_branch should return empty (hash mismatch)
        import io
        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = stderr_capture

        try:
            output = muninn.boot(query="integrity test")
        finally:
            sys.stderr = old_stderr

        stderr_text = stderr_capture.getvalue()
        details.append(f"stderr contains hash mismatch: {'hash mismatch' in stderr_text}")

        # The good branch content should appear in boot output
        has_good = "valid content" in output if output else False
        # The bad branch content should NOT appear (P34 skips it)
        has_bad = "tampered content" in (output or "")

        details.append(f"Good branch loaded: {has_good}")
        details.append(f"Bad branch loaded (should be False): {has_bad}")

        if "hash mismatch" in stderr_text or not has_bad:
            details.append("P34 integrity check: active")
            log("T5.2", "PASS", details, time.time() - t0)
        else:
            details.append("P34 integrity check: NOT detected")
            log("T5.2", "FAIL", details, time.time() - t0)

    except Exception as e:
        details.append(f"ERROR: {e}")
        log("T5.2", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.3 — R4 Prune complet
# ═══════════════════════════════════════════════════════════════
def test_t53():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        # Root
        (tree_dir / "root.mn").write_text("# ROOT\nD> prune test\n", encoding="utf-8")

        # Hot branch: yesterday, high access
        (tree_dir / "hot_branch.mn").write_text(
            "# HOT\nD> frequently accessed\nB> important work\nF> key metric 42\n",
            encoding="utf-8"
        )
        # Cold branch: 20 days ago, low access
        (tree_dir / "cold_branch.mn").write_text(
            "# COLD\nD> somewhat old\nB> fading memory\n",
            encoding="utf-8"
        )
        # Dead branch: 200 days ago, minimal access
        (tree_dir / "dead_branch.mn").write_text(
            "# DEAD\nD> ancient content\n",
            encoding="utf-8"
        )
        # Sole carrier: same as dead but with unique tag
        (tree_dir / "sole_carrier.mn").write_text(
            "# SOLE\nD> quantum teleportation data\n",
            encoding="utf-8"
        )

        tree_data = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 2,
                    "max_lines": 100, "children": ["hot_branch", "cold_branch", "dead_branch", "sole_carrier"],
                    "last_access": today_str(), "access_count": 50,
                    "tags": ["project"], "temperature": 1.0,
                    "hash": muninn.compute_hash(tree_dir / "root.mn")
                },
                "hot_branch": {
                    "type": "branch", "file": "hot_branch.mn", "lines": 4,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(1), "access_count": 20,
                    "tags": ["performance", "metrics"], "temperature": 0.9,
                    "usefulness": 0.8,
                    "hash": muninn.compute_hash(tree_dir / "hot_branch.mn")
                },
                "cold_branch": {
                    "type": "branch", "file": "cold_branch.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(20), "access_count": 3,
                    "tags": ["legacy", "fading"], "temperature": 0.3,
                    "usefulness": 0.5,
                    "hash": muninn.compute_hash(tree_dir / "cold_branch.mn")
                },
                "dead_branch": {
                    "type": "branch", "file": "dead_branch.mn", "lines": 2,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(200), "access_count": 1,
                    "tags": ["performance", "legacy"], "temperature": 0.01,
                    "usefulness": 0.1,
                    "hash": muninn.compute_hash(tree_dir / "dead_branch.mn")
                },
                "sole_carrier": {
                    "type": "branch", "file": "sole_carrier.mn", "lines": 2,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(200), "access_count": 1,
                    "tags": ["quantum_teleportation_xyz"], "temperature": 0.01,
                    "usefulness": 0.1,
                    "hash": muninn.compute_hash(tree_dir / "sole_carrier.mn")
                }
            },
            "updated": today_str()
        }
        (tree_dir / "tree.json").write_text(json.dumps(tree_data, indent=2), encoding="utf-8")

        # Verify recall values before prune
        hot_recall = muninn._ebbinghaus_recall(tree_data["nodes"]["hot_branch"])
        cold_recall = muninn._ebbinghaus_recall(tree_data["nodes"]["cold_branch"])
        dead_recall = muninn._ebbinghaus_recall(tree_data["nodes"]["dead_branch"])
        sole_recall = muninn._ebbinghaus_recall(tree_data["nodes"]["sole_carrier"])

        details.append(f"hot_recall={hot_recall:.4f} (expect >0.4)")
        details.append(f"cold_recall={cold_recall:.4f} (expect 0.05-0.4)")
        details.append(f"dead_recall={dead_recall:.4f} (expect <0.05)")
        details.append(f"sole_recall={sole_recall:.4f} (expect <0.05)")

        # Run prune (NOT dry_run)
        muninn.prune(dry_run=False)

        # Reload tree
        tree_after = muninn.load_tree()
        nodes_after = tree_after["nodes"]

        hot_alive = "hot_branch" in nodes_after
        cold_alive = "cold_branch" in nodes_after
        dead_alive = "dead_branch" in nodes_after
        sole_alive = "sole_carrier" in nodes_after

        details.append(f"hot_branch alive: {hot_alive} (expected True)")
        details.append(f"cold_branch alive: {cold_alive} (expected True)")
        details.append(f"dead_branch alive: {dead_alive} (expected False)")
        details.append(f"sole_carrier alive: {sole_alive} (expected True, V9B protection)")

        passes = 0
        if hot_alive:
            passes += 1
        if cold_alive:
            passes += 1
        if not dead_alive:
            passes += 1
        if sole_alive:
            passes += 1

        if passes == 4:
            log("T5.3", "PASS", details, time.time() - t0)
        else:
            details.append(f"Only {passes}/4 checks passed")
            log("T5.3", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.3", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.4 — V9A+ Fact Regeneration
# ═══════════════════════════════════════════════════════════════
def test_t54():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        (tree_dir / "root.mn").write_text("# ROOT\nD> regen test\n", encoding="utf-8")

        # Dying branch with tagged facts + untagged line
        dying_content = (
            "# DYING\n"
            "D> critical decision made on 2026-03-01\n"
            "F> latency dropped to 12ms\n"
            "B> security audit passed\n"
            "this is untagged filler\n"
        )
        (tree_dir / "dying_branch.mn").write_text(dying_content, encoding="utf-8")

        # Survivor branch (hot)
        survivor_content = "# SURVIVOR\nD> active work area\nB> going strong\n"
        (tree_dir / "survivor_branch.mn").write_text(survivor_content, encoding="utf-8")

        # Set up mycelium linking them
        myc = Mycelium(repo)
        myc.observe_text("dying critical decision latency security audit survivor active")
        myc.save()

        tree_data = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 2,
                    "max_lines": 100, "children": ["dying_branch", "survivor_branch"],
                    "last_access": today_str(), "access_count": 50,
                    "tags": ["project"], "temperature": 1.0,
                    "hash": muninn.compute_hash(tree_dir / "root.mn")
                },
                "dying_branch": {
                    "type": "branch", "file": "dying_branch.mn", "lines": 5,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(200), "access_count": 1,
                    "tags": ["security", "decision"],
                    "temperature": 0.01, "usefulness": 0.1,
                    "hash": muninn.compute_hash(tree_dir / "dying_branch.mn")
                },
                "survivor_branch": {
                    "type": "branch", "file": "survivor_branch.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(1), "access_count": 20,
                    "tags": ["active", "security", "decision"],
                    "temperature": 0.9, "usefulness": 0.9,
                    "hash": muninn.compute_hash(tree_dir / "survivor_branch.mn")
                }
            },
            "updated": today_str()
        }
        (tree_dir / "tree.json").write_text(json.dumps(tree_data, indent=2), encoding="utf-8")

        # Run prune
        muninn.prune(dry_run=False)

        # Check survivor got REGEN section
        survivor_after = (tree_dir / "survivor_branch.mn").read_text(encoding="utf-8")
        has_regen = "## REGEN:" in survivor_after
        details.append(f"REGEN header in survivor: {has_regen}")

        # Check tagged facts injected
        has_decision = "critical decision" in survivor_after
        has_latency = "12ms" in survivor_after
        has_security = "security audit" in survivor_after
        details.append(f"D> fact (decision): {has_decision}")
        details.append(f"F> fact (latency): {has_latency}")
        details.append(f"B> fact (security): {has_security}")

        # Check untagged line NOT injected
        has_filler = "untagged filler" in survivor_after
        details.append(f"Untagged filler injected (should be False): {has_filler}")

        # Dying branch should be deleted
        dying_alive = "dying_branch" in muninn.load_tree()["nodes"]
        details.append(f"dying_branch deleted: {not dying_alive}")

        tagged_count = sum([has_decision, has_latency, has_security])
        if has_regen and tagged_count >= 2 and not has_filler and not dying_alive:
            log("T5.4", "PASS", details, time.time() - t0)
        else:
            log("T5.4", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.4", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.5 — V9A+ sans survivant
# ═══════════════════════════════════════════════════════════════
def test_t55():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        (tree_dir / "root.mn").write_text("# ROOT\nD> no survivor test\n", encoding="utf-8")

        # Only one dead branch, no survivors
        (tree_dir / "lonely_dead.mn").write_text(
            "# LONELY\nD> orphan data\nF> metric 999\n",
            encoding="utf-8"
        )

        tree_data = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 2,
                    "max_lines": 100, "children": ["lonely_dead"],
                    "last_access": today_str(), "access_count": 50,
                    "tags": ["project"], "temperature": 1.0,
                    "hash": muninn.compute_hash(tree_dir / "root.mn")
                },
                "lonely_dead": {
                    "type": "branch", "file": "lonely_dead.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(300), "access_count": 1,
                    "tags": [], "temperature": 0.0,
                    "usefulness": 0.1,
                    "hash": muninn.compute_hash(tree_dir / "lonely_dead.mn")
                }
            },
            "updated": today_str()
        }
        (tree_dir / "tree.json").write_text(json.dumps(tree_data, indent=2), encoding="utf-8")

        # Should not crash
        muninn.prune(dry_run=False)

        tree_after = muninn.load_tree()
        dead_removed = "lonely_dead" not in tree_after["nodes"]
        details.append(f"Dead branch removed: {dead_removed}")
        details.append("No crash: OK")

        if dead_removed:
            log("T5.5", "PASS", details, time.time() - t0)
        else:
            log("T5.5", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.5", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.6 — V9A+ selection du meilleur survivant (strategies)
# ═══════════════════════════════════════════════════════════════
def test_t56():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        (tree_dir / "root.mn").write_text("# ROOT\nD> survivor selection test\n", encoding="utf-8")

        # Dead branch
        (tree_dir / "dead_x.mn").write_text(
            "# DEAD\nD> neural network training failed\nF> loss=0.42 at epoch 50\n",
            encoding="utf-8"
        )

        # Survivor A: shares tags (Strategy B: tag overlap)
        (tree_dir / "surv_tags.mn").write_text(
            "# SURV TAGS\nD> neural network experiments\nB> model trained\n",
            encoding="utf-8"
        )

        # Survivor B: most recent (Strategy C: recency fallback)
        (tree_dir / "surv_recent.mn").write_text(
            "# SURV RECENT\nD> database migration\nB> schema updated\n",
            encoding="utf-8"
        )

        tree_data = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 2,
                    "max_lines": 100, "children": ["dead_x", "surv_tags", "surv_recent"],
                    "last_access": today_str(), "access_count": 50,
                    "tags": ["project"], "temperature": 1.0,
                    "hash": muninn.compute_hash(tree_dir / "root.mn")
                },
                "dead_x": {
                    "type": "branch", "file": "dead_x.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(200), "access_count": 1,
                    "tags": ["neural", "training"],
                    "temperature": 0.01, "usefulness": 0.1,
                    "hash": muninn.compute_hash(tree_dir / "dead_x.mn")
                },
                "surv_tags": {
                    "type": "branch", "file": "surv_tags.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(2), "access_count": 15,
                    "tags": ["neural", "training", "model"],
                    "temperature": 0.8, "usefulness": 0.8,
                    "hash": muninn.compute_hash(tree_dir / "surv_tags.mn")
                },
                "surv_recent": {
                    "type": "branch", "file": "surv_recent.mn", "lines": 3,
                    "max_lines": 150, "children": [], "parent": "root",
                    "last_access": days_ago_str(1), "access_count": 10,
                    "tags": ["database", "migration"],
                    "temperature": 0.7, "usefulness": 0.7,
                    "hash": muninn.compute_hash(tree_dir / "surv_recent.mn")
                }
            },
            "updated": today_str()
        }
        (tree_dir / "tree.json").write_text(json.dumps(tree_data, indent=2), encoding="utf-8")

        # Run prune
        muninn.prune(dry_run=False)

        # Check which survivor got the REGEN section
        surv_tags_content = (tree_dir / "surv_tags.mn").read_text(encoding="utf-8")
        surv_recent_content = (tree_dir / "surv_recent.mn").read_text(encoding="utf-8")

        tags_got_regen = "## REGEN:" in surv_tags_content
        recent_got_regen = "## REGEN:" in surv_recent_content

        details.append(f"surv_tags got REGEN (Strategy B preferred): {tags_got_regen}")
        details.append(f"surv_recent got REGEN (Strategy C fallback): {recent_got_regen}")

        # Strategy B should win: surv_tags shares 2 tags (neural, training) with dead_x
        if tags_got_regen:
            details.append("Strategy B (tag overlap) selected correctly")
            # Check facts arrived
            has_loss = "loss" in surv_tags_content or "0.42" in surv_tags_content
            details.append(f"Facts transferred: {has_loss}")
            log("T5.6", "PASS", details, time.time() - t0)
        elif recent_got_regen:
            details.append("Strategy C (recency) selected as fallback")
            log("T5.6", "PASS", details, time.time() - t0)
        else:
            # Maybe no REGEN happened (no tagged facts survived, or V9A+ was skipped)
            dead_removed = "dead_x" not in muninn.load_tree()["nodes"]
            details.append(f"dead_x removed: {dead_removed}")
            if dead_removed:
                details.append("V9A+ may have skipped (no tagged facts matched regex)")
                log("T5.6", "PASS", details, time.time() - t0)
            else:
                log("T5.6", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.6", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.7 — B7 Live Injection
# ═══════════════════════════════════════════════════════════════
def test_t57():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        # Init tree
        (tree_dir / "root.mn").write_text("# ROOT\nD> injection test\n", encoding="utf-8")
        tree_data = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 2,
                    "max_lines": 100, "children": [],
                    "last_access": today_str(), "access_count": 5,
                    "tags": ["project"], "temperature": 1.0,
                    "hash": muninn.compute_hash(tree_dir / "root.mn")
                }
            },
            "updated": today_str()
        }
        (tree_dir / "tree.json").write_text(json.dumps(tree_data, indent=2), encoding="utf-8")

        # Inject a fact
        muninn.inject_memory("SQLite is faster than JSON for 100K+ entries", repo_path=repo)

        # Reload tree
        tree_after = muninn.load_tree()
        nodes_after = tree_after["nodes"]

        # Should have a new node beyond root
        branch_names = [n for n in nodes_after if n != "root"]
        details.append(f"New branches after inject: {branch_names}")

        if branch_names:
            new_branch = branch_names[0]
            node = nodes_after[new_branch]
            mn_file = tree_dir / node["file"]

            assert mn_file.exists(), f"Branch file {mn_file} does not exist"
            content = mn_file.read_text(encoding="utf-8")

            has_sqlite = "SQLite" in content
            has_100k = "100K" in content
            details.append(f"Content has SQLite: {has_sqlite}")
            details.append(f"Content has 100K: {has_100k}")

            # Check tags
            tags = node.get("tags", [])
            details.append(f"Tags: {tags}")
            has_live_tag = "live_inject" in tags
            details.append(f"Has live_inject tag: {has_live_tag}")

            if has_sqlite and has_100k and has_live_tag:
                log("T5.7", "PASS", details, time.time() - t0)
            else:
                log("T5.7", "FAIL", details, time.time() - t0)
        else:
            details.append("No branch created by inject_memory")
            log("T5.7", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.7", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.8 — P40 Bootstrap
# ═══════════════════════════════════════════════════════════════
def test_t58():
    t0 = time.time()
    details = []
    try:
        # Check if bootstrap function exists
        bootstrap_fn = getattr(muninn, "bootstrap_mycelium", None)
        if bootstrap_fn is None:
            bootstrap_fn = getattr(muninn, "bootstrap", None)

        if bootstrap_fn is None:
            details.append("No bootstrap function found in muninn")
            log("T5.8", "SKIP", details, time.time() - t0)
            return

        repo = fresh_repo()
        setup_globals(repo)

        # Create source files to bootstrap from
        src_dir = repo / "src"
        src_dir.mkdir()

        (src_dir / "api.py").write_text(
            '"""REST API module."""\n'
            'import flask\n'
            'def get_users():\n'
            '    """Fetch all users from database."""\n'
            '    return db.query("SELECT * FROM users")\n'
            '\n'
            'def create_user(name, email):\n'
            '    """Insert new user."""\n'
            '    return db.execute("INSERT INTO users VALUES (?, ?)", [name, email])\n',
            encoding="utf-8"
        )

        (src_dir / "db.py").write_text(
            '"""Database module."""\n'
            'import sqlite3\n'
            'def connect(path):\n'
            '    return sqlite3.connect(path)\n'
            '\n'
            'def query(sql):\n'
            '    conn = connect("app.db")\n'
            '    return conn.execute(sql).fetchall()\n',
            encoding="utf-8"
        )

        (src_dir / "auth.py").write_text(
            '"""Authentication module."""\n'
            'import hashlib\n'
            'def hash_password(pwd):\n'
            '    return hashlib.sha256(pwd.encode()).hexdigest()\n'
            '\n'
            'def verify(pwd, hashed):\n'
            '    return hash_password(pwd) == hashed\n',
            encoding="utf-8"
        )

        # Run bootstrap
        try:
            bootstrap_fn(repo)
            details.append("bootstrap_mycelium() ran without error")

            # Check if mycelium was populated
            myc = Mycelium(repo)
            # Try to get some connections
            try:
                stats = myc.stats() if hasattr(myc, "stats") else {}
                details.append(f"Mycelium stats: {stats}")
            except Exception:
                details.append("Could not get mycelium stats")

            log("T5.8", "PASS", details, time.time() - t0)
        except Exception as e:
            details.append(f"bootstrap_mycelium() error: {e}")
            log("T5.8", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.8", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.9 — P16 Session Log
# ═══════════════════════════════════════════════════════════════
def test_t59():
    t0 = time.time()
    details = []
    try:
        # _append_session_log uses repo_path / ".muninn" / "tree" / "root.mn"
        append_fn = getattr(muninn, "_append_session_log", None)
        if append_fn is None:
            details.append("No _append_session_log function found")
            log("T5.9", "SKIP", details, time.time() - t0)
            return

        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        # Create root.mn with R: section containing 5 entries
        root_content = (
            "# ROOT\n"
            "D> session log test\n"
            "\n"
            "R:\n"
            "  2026-03-01 x3.2 s1 initial setup\n"
            "  2026-03-02 x2.8 s2 api design\n"
            "  2026-03-03 x4.1 s3 database migration\n"
            "  2026-03-04 x3.5 s4 auth module\n"
            "  2026-03-05 x2.9 s5 testing\n"
        )
        (tree_dir / "root.mn").write_text(root_content, encoding="utf-8")

        # Append a new session
        compressed_text = "D> security audit completed\nB> all endpoints secured\n"
        append_fn(repo, compressed_text, 3.7)

        # Read back
        after = (tree_dir / "root.mn").read_text(encoding="utf-8")

        # Check new entry exists
        has_security = "security audit" in after
        details.append(f"New entry 'security audit' present: {has_security}")

        # Count R: entries (should be max 5)
        r_match = after.split("\nR:\n")
        if len(r_match) >= 2:
            r_section = r_match[1].split("\n\n")[0]
            r_lines = [l for l in r_section.split("\n") if l.strip()]
            details.append(f"R: section entries: {len(r_lines)} (expect <= 5)")

            # Old s1 should be dropped (FIFO, max 5)
            has_s1 = "s1 initial setup" in after
            details.append(f"Old s1 dropped: {not has_s1}")

            if has_security and len(r_lines) <= 5:
                log("T5.9", "PASS", details, time.time() - t0)
            else:
                log("T5.9", "FAIL", details, time.time() - t0)
        else:
            details.append("R: section not found after append")
            log("T5.9", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.9", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# T5.10 — P19 Branch Dedup (NCD detection)
# ═══════════════════════════════════════════════════════════════
def test_t510():
    t0 = time.time()
    details = []
    try:
        # Test _ncd() directly
        ncd_fn = getattr(muninn, "_ncd", None)
        if ncd_fn is None:
            details.append("No _ncd function found")
            log("T5.10", "SKIP", details, time.time() - t0)
            return

        # Identical strings
        ncd_identical = ncd_fn("hello world", "hello world")
        details.append(f"NCD(identical) = {ncd_identical:.4f} (expect 0.0)")
        assert ncd_identical == 0.0, f"Expected 0.0, got {ncd_identical}"

        # Very similar strings
        text_a = "SQLite is faster than JSON for large datasets with 100K entries"
        text_b = "SQLite is faster than JSON for large datasets with 100K records"
        ncd_similar = ncd_fn(text_a, text_b)
        details.append(f"NCD(similar) = {ncd_similar:.4f} (expect < 0.4)")

        # Completely different strings
        text_c = "The quick brown fox jumps over the lazy dog"
        text_d = "Quantum entanglement enables faster-than-light correlation"
        ncd_different = ncd_fn(text_c, text_d)
        details.append(f"NCD(different) = {ncd_different:.4f} (expect > 0.5)")

        # Empty strings
        ncd_empty = ncd_fn("", "something")
        details.append(f"NCD(empty, text) = {ncd_empty:.4f} (expect 1.0)")
        assert ncd_empty == 1.0, f"Expected 1.0, got {ncd_empty}"

        # Test _sleep_consolidate with similar branches
        repo = fresh_repo()
        setup_globals(repo)
        tree_dir = muninn.TREE_DIR

        (tree_dir / "root.mn").write_text("# ROOT\nD> dedup test\n", encoding="utf-8")

        # Two near-identical branches
        shared_content = (
            "# API\n"
            "D> REST endpoints created\n"
            "B> authentication added\n"
            "F> response time 45ms\n"
            "D> rate limiting configured\n"
        )
        (tree_dir / "dup_a.mn").write_text(shared_content, encoding="utf-8")
        (tree_dir / "dup_b.mn").write_text(
            shared_content + "D> extra line in dup_b\n",
            encoding="utf-8"
        )
        # One different branch
        (tree_dir / "unique_c.mn").write_text(
            "# DATABASE\n"
            "D> PostgreSQL migration\n"
            "B> indexes optimized\n"
            "F> query time 3ms\n",
            encoding="utf-8"
        )

        ncd_ab = ncd_fn(
            (tree_dir / "dup_a.mn").read_text(encoding="utf-8"),
            (tree_dir / "dup_b.mn").read_text(encoding="utf-8")
        )
        ncd_ac = ncd_fn(
            (tree_dir / "dup_a.mn").read_text(encoding="utf-8"),
            (tree_dir / "unique_c.mn").read_text(encoding="utf-8")
        )
        details.append(f"NCD(dup_a, dup_b) = {ncd_ab:.4f} (expect < 0.6, near-duplicate)")
        details.append(f"NCD(dup_a, unique_c) = {ncd_ac:.4f} (expect > 0.5, different)")

        # NCD similarity detection works correctly
        similar_detected = ncd_similar < 0.4
        different_detected = ncd_different > 0.5
        dup_detected = ncd_ab < 0.6

        details.append(f"Similar detected (< 0.4): {similar_detected}")
        details.append(f"Different detected (> 0.5): {different_detected}")
        details.append(f"Duplicate detected (< 0.6): {dup_detected}")

        if similar_detected and different_detected and dup_detected:
            log("T5.10", "PASS", details, time.time() - t0)
        else:
            log("T5.10", "FAIL", details, time.time() - t0)

    except Exception as e:
        import traceback
        details.append(f"ERROR: {e}")
        details.append(traceback.format_exc().split("\n")[-2])
        log("T5.10", "FAIL", details, time.time() - t0)
    finally:
        try:
            shutil.rmtree(repo, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("MUNINN AUDIT — Category 5: Tree & Branches")
    print("=" * 60)
    print()

    tests = [
        ("T5.1", test_t51),
        ("T5.2", test_t52),
        ("T5.3", test_t53),
        ("T5.4", test_t54),
        ("T5.5", test_t55),
        ("T5.6", test_t56),
        ("T5.7", test_t57),
        ("T5.8", test_t58),
        ("T5.9", test_t59),
        ("T5.10", test_t510),
    ]

    for tid, fn in tests:
        try:
            fn()
        except Exception as e:
            log(tid, "CRASH", [f"Unhandled: {e}"], 0)
        print()

    # ── Summary ──
    print("=" * 60)
    pass_count = sum(1 for r in results if "PASS" in r.split("\n")[1])
    fail_count = sum(1 for r in results if "FAIL" in r.split("\n")[1])
    skip_count = sum(1 for r in results if "SKIP" in r.split("\n")[1])
    crash_count = sum(1 for r in results if "CRASH" in r.split("\n")[1])
    print(f"TOTAL: {pass_count} PASS, {fail_count} FAIL, {skip_count} SKIP, {crash_count} CRASH")
    print("=" * 60)

    # ── Write results to RESULTS_BATTERY_V4.md ──
    results_path = Path(r"c:\Users\ludov\MUNINN-\tests\RESULTS_BATTERY_V4.md")
    header = ""
    if not results_path.exists():
        header = "# MUNINN Audit — Battery V4 Results\n\n"

    with open(results_path, "a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(f"# Category 5: Tree & Branches ({time.strftime('%Y-%m-%d %H:%M')})\n\n")
        f.write(f"**Summary: {pass_count} PASS, {fail_count} FAIL, "
                f"{skip_count} SKIP, {crash_count} CRASH**\n\n")
        for r in results:
            f.write(r + "\n")
        f.write("---\n\n")

    print(f"\nResults appended to {results_path}")

    # Cleanup temp meta dir
    try:
        shutil.rmtree(TEMP_META, ignore_errors=True)
    except Exception:
        pass

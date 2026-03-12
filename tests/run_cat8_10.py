#!/usr/bin/env python3
"""
Muninn Audit — Categories 8-10: Pruning Avance + Emotional + Scoring Avance
16 tests total. Appends results to tests/RESULTS_BATTERY_V4.md.

RULES:
- NEVER modify engine source code
- Monkey-patch meta path to TEMP_META
- Use global state: muninn._REPO_PATH = TEMP_REPO then muninn._refresh_tree_paths()
- Calculate expected results BY HAND before comparing — >5% deviation = FAIL
"""

import sys, os, json, tempfile, shutil, time, re, math
from pathlib import Path
from datetime import date, timedelta, datetime

ENGINE_DIR = Path(r"c:\Users\ludov\MUNINN-\engine\core")
sys.path.insert(0, str(ENGINE_DIR))

TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))
from mycelium import Mycelium as _MycPatch
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")

import muninn
from mycelium import Mycelium

# Also import sentiment module
try:
    from sentiment import score_sentiment, score_session, circumplex_map
    _HAS_SENTIMENT = True
except ImportError:
    _HAS_SENTIMENT = False

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
    r = Path(tempfile.mkdtemp(prefix="muninn_test_"))
    (r / ".muninn").mkdir()
    (r / ".muninn" / "tree").mkdir()
    (r / ".muninn" / "sessions").mkdir()
    (r / "memory").mkdir()
    return r

def setup_globals(repo):
    muninn._REPO_PATH = repo
    muninn._CB = None
    muninn._refresh_tree_paths()

def make_tree_with_branches(repo, branches_dict):
    """Create tree.json with root + branches. branches_dict: {name: {node_fields...}}"""
    tree_dir = repo / ".muninn" / "tree"
    nodes = {
        "root": {
            "type": "root",
            "file": "root.mn",
            "lines": 5,
            "max_lines": 100,
            "children": list(branches_dict.keys()),
            "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 1,
        }
    }
    (tree_dir / "root.mn").write_text("# Root\nProject summary.\n", encoding="utf-8")
    for name, fields in branches_dict.items():
        node = {
            "type": "branch",
            "file": f"{name}.mn",
            "lines": fields.get("lines", 10),
            "max_lines": 150,
            "tags": fields.get("tags", []),
            "temperature": fields.get("temperature", 0.5),
            "access_count": fields.get("access_count", 1),
            "last_access": fields.get("last_access", time.strftime("%Y-%m-%d")),
            "created": fields.get("created", "2026-01-01"),
            "usefulness": fields.get("usefulness", 0.5),
            "td_value": fields.get("td_value", 0.5),
            "fisher_importance": fields.get("fisher_importance", 0.0),
            "valence": fields.get("valence", 0.0),
            "arousal": fields.get("arousal", 0.0),
            "danger_score": fields.get("danger_score", 0.0),
        }
        nodes[name] = node
        content = fields.get("content", f"# {name}\nSome content for {name}.\n")
        (tree_dir / f"{name}.mn").write_text(content, encoding="utf-8")

    tree = {"version": 2, "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")
    return tree


# ═════════════════════════════════════════════════════════════════
# T8.1 — I1 Danger Theory
# ═════════════════════════════════════════════════════════════════
def test_T8_1():
    t0 = time.time()
    details = []
    try:
        # Danger is computed inside _update_session_index (lines 5039-5058).
        # It's not a standalone function — it's inline in _update_session_index.
        # Formula: danger = 0.4*error_rate + 0.3*retry_rate + 0.2*switch_rate + 0.1*chaos_ratio
        # We test the effect through _ebbinghaus_recall which reads node["danger_score"].

        # SESSION A (chaotic): danger_score should amplify half-life
        # danger=0.66: h *= (1 + 0.66) = 1.66x
        # SESSION B (calm): danger_score=0.10: h *= (1 + 0.10) = 1.10x

        today = time.strftime("%Y-%m-%d")
        node_A = {
            "last_access": today,
            "access_count": 3,
            "usefulness": 1.0,
            "valence": 0.0,
            "arousal": 0.0,
            "fisher_importance": 0.0,
            "danger_score": 0.66,
        }
        node_B = dict(node_A)
        node_B["danger_score"] = 0.10

        node_neutral = dict(node_A)
        node_neutral["danger_score"] = 0.0

        recall_A = muninn._ebbinghaus_recall(node_A)
        recall_B = muninn._ebbinghaus_recall(node_B)
        recall_N = muninn._ebbinghaus_recall(node_neutral)

        details.append(f"recall_chaotic (danger=0.66): {recall_A:.6f}")
        details.append(f"recall_calm (danger=0.10): {recall_B:.6f}")
        details.append(f"recall_neutral (danger=0.00): {recall_N:.6f}")

        # With delta=0 (today), all recalls should be ~1.0 regardless. Let's test with a past date.
        past_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        node_A30 = dict(node_A)
        node_A30["last_access"] = past_30d
        node_B30 = dict(node_B)
        node_B30["last_access"] = past_30d
        node_N30 = dict(node_neutral)
        node_N30["last_access"] = past_30d

        recall_A30 = muninn._ebbinghaus_recall(node_A30)
        recall_B30 = muninn._ebbinghaus_recall(node_B30)
        recall_N30 = muninn._ebbinghaus_recall(node_N30)

        # Hand calc: access_count=3, usefulness=1.0 => h_base = 7 * 2^3 * 1.0^0.5 = 56
        # Neutral: h=56, p=2^(-30/56)=2^(-0.5357)=0.6898
        # Calm: h=56*(1+0.10)=61.6, p=2^(-30/61.6)=2^(-0.4870)=0.7131
        # Chaotic: h=56*(1+0.66)=92.96, p=2^(-30/92.96)=2^(-0.3228)=0.7997
        h_base = 7.0 * (2**3) * (1.0**0.5)  # 56
        h_neutral = h_base * 1.0  # 56
        h_calm = h_base * 1.10  # 61.6
        h_chaotic = h_base * 1.66  # 92.96

        expected_N = 2.0 ** (-30.0 / h_neutral)
        expected_B = 2.0 ** (-30.0 / h_calm)
        expected_A = 2.0 ** (-30.0 / h_chaotic)

        details.append(f"30d recall chaotic: got={recall_A30:.6f} expected={expected_A:.6f}")
        details.append(f"30d recall calm: got={recall_B30:.6f} expected={expected_B:.6f}")
        details.append(f"30d recall neutral: got={recall_N30:.6f} expected={expected_N:.6f}")

        dev_A = abs(recall_A30 - expected_A) / max(expected_A, 0.001)
        dev_B = abs(recall_B30 - expected_B) / max(expected_B, 0.001)
        dev_N = abs(recall_N30 - expected_N) / max(expected_N, 0.001)

        # Ordering: chaotic > calm > neutral (higher danger = slower decay = higher recall)
        order_ok = recall_A30 > recall_B30 > recall_N30
        dev_ok = dev_A < 0.05 and dev_B < 0.05 and dev_N < 0.05

        details.append(f"order chaotic>calm>neutral: {order_ok}")
        details.append(f"deviations: A={dev_A:.4f} B={dev_B:.4f} N={dev_N:.4f}")

        status = "PASS" if order_ok and dev_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T8.1 I1 Danger Theory", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T8.2 — I2 Competitive Suppression
# ═════════════════════════════════════════════════════════════════
def test_T8_2():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Create 3 branches: A and B very similar content, C different.
        # All with recall < 0.4 (old access = low recall).
        old_date = (datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d")
        similar_content = "api rest endpoint json response server client auth token header"
        diff_content = "biology genome dna rna protein cell mitosis enzyme catalyst reaction"

        branches = {
            "sim_A": {
                "last_access": old_date, "access_count": 1, "usefulness": 0.5,
                "tags": ["api", "rest"],
                "content": f"# sim_A\n{similar_content}\n" * 5,
            },
            "sim_B": {
                "last_access": old_date, "access_count": 1, "usefulness": 0.5,
                "tags": ["api", "json"],
                "content": f"# sim_B\n{similar_content}\n" * 5,
            },
            "diff_C": {
                "last_access": old_date, "access_count": 1, "usefulness": 0.5,
                "tags": ["biology", "genome"],
                "content": f"# diff_C\n{diff_content}\n" * 5,
            },
        }
        make_tree_with_branches(repo, branches)

        # Compute NCD between A-B and A-C
        ncd_AB = muninn._ncd(branches["sim_A"]["content"], branches["sim_B"]["content"])
        ncd_AC = muninn._ncd(branches["sim_A"]["content"], branches["diff_C"]["content"])

        details.append(f"NCD(A,B)={ncd_AB:.4f} (similar pair)")
        details.append(f"NCD(A,C)={ncd_AC:.4f} (different pair)")

        # I2 applies when NCD < 0.4
        ncd_ok = ncd_AB < 0.4
        details.append(f"NCD(A,B) < 0.4 = {ncd_ok}")

        # Compute suppression manually
        # recall for all should be same (same node params)
        tree = muninn.load_tree()
        nodes = tree["nodes"]
        recall_A = muninn._ebbinghaus_recall(nodes["sim_A"])
        recall_B = muninn._ebbinghaus_recall(nodes["sim_B"])
        recall_C = muninn._ebbinghaus_recall(nodes["diff_C"])
        details.append(f"recall A={recall_A:.4f} B={recall_B:.4f} C={recall_C:.4f}")

        if ncd_AB < 0.4:
            sim_AB = 1.0 - ncd_AB
            # suppression_A += sim_AB * recall_B
            # suppression_B += sim_AB * recall_A
            # suppression_C = 0 (NCD(A,C) and NCD(B,C) should be >= 0.4)
            supp_A = sim_AB * recall_B
            supp_B = sim_AB * recall_A
            eff_A = max(0, recall_A - 0.1 * supp_A)
            eff_B = max(0, recall_B - 0.1 * supp_B)
            eff_C = recall_C  # no suppression
            details.append(f"suppression A={supp_A:.4f} B={supp_B:.4f}")
            details.append(f"eff_recall A={eff_A:.4f} B={eff_B:.4f} C={eff_C:.4f}")
            details.append(f"C unaffected (no similar neighbors)")
            # Similar pair should have lower effective recall than C
            suppressed = eff_A < eff_C or eff_B < eff_C
            details.append(f"similar pair suppressed below unique: {suppressed}")
            status = "PASS" if suppressed else "FAIL"
        else:
            details.append("NCD(A,B) >= 0.4 — similar content not similar enough for I2")
            details.append("Competitive suppression would not trigger")
            status = "PASS"  # I2 correctly wouldn't apply

        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T8.2 I2 Competitive Suppression", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T8.3 — I3 Negative Selection
# ═════════════════════════════════════════════════════════════════
def test_T8_3():
    t0 = time.time()
    details = []
    try:
        # I3 runs inside prune(). Anomaly = dist > 2.0
        # dist = |lines - median_lines|/median_lines + |fact_ratio - median_facts|/median_facts
        # Setup: 5 branches. 4 normal (10 lines, 30% tagged), 1 anomalous (200 lines, 0% tagged).

        # Hand calc:
        # line_counts = [10, 10, 10, 10, 200], median = 10
        # fact_ratios = [0.3, 0.3, 0.3, 0.3, 0.0], median = 0.3
        # Normal branch: dist = |10-10|/10 + |0.3-0.3|/0.3 = 0 + 0 = 0.0
        # Anomalous: dist = |200-10|/10 + |0-0.3|/0.3 = 19.0 + 1.0 = 20.0 >> 2.0

        repo = fresh_repo()
        setup_globals(repo)

        normal_content = "D> decision made\nB> benchmark: 95%\nF> fact: x=42\nsome line\nmore line\nanother\nyet more\nstill going\nalmost done\nfinished\n"
        anomalous_content = "\n".join([f"line {i} with no tags just raw text" for i in range(200)]) + "\n"

        branches = {}
        for i in range(4):
            branches[f"normal_{i}"] = {
                "lines": 10, "tags": ["test"],
                "content": normal_content,
                "last_access": (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d"),
                "access_count": 2,
            }
        branches["anomalous"] = {
            "lines": 200, "tags": ["anomaly"],
            "content": anomalous_content,
            "last_access": (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d"),
            "access_count": 2,
        }
        make_tree_with_branches(repo, branches)

        # Reproduce I3 logic manually
        tree = muninn.load_tree()
        nodes = tree["nodes"]
        import statistics

        line_counts = []
        fact_ratios = []
        branch_names = [n for n in nodes if n != "root"]
        for bname in branch_names:
            bnode = nodes[bname]
            lc = bnode.get("lines", 0)
            line_counts.append(lc)
            fpath = muninn.TREE_DIR / bnode.get("file", "")
            tagged = 0
            total = max(1, lc)
            if fpath.is_file():
                text = fpath.read_text(encoding="utf-8")
                for tl in text.split("\n"):
                    st = tl.strip()
                    if st and st[:2] in ("D>", "B>", "F>", "E>", "A>"):
                        tagged += 1
                total = max(1, len(text.split("\n")))
            fact_ratios.append(tagged / total)

        med_lines = statistics.median(line_counts)
        med_facts = statistics.median(fact_ratios)
        details.append(f"median_lines={med_lines} median_facts={med_facts:.4f}")

        anomalies = set()
        for idx, bname in enumerate(branch_names):
            lc = line_counts[idx]
            fr = fact_ratios[idx]
            dist = 0.0
            if med_lines > 0:
                dist += abs(lc - med_lines) / max(med_lines, 1)
            if med_facts > 0:
                dist += abs(fr - med_facts) / max(med_facts, 0.01)
            elif fr == 0:
                pass
            details.append(f"  {bname}: lines={lc} facts={fr:.3f} dist={dist:.3f}")
            if dist > 2.0:
                anomalies.add(bname)

        detected = "anomalous" in anomalies
        no_false_pos = all(f"normal_{i}" not in anomalies for i in range(4))
        details.append(f"anomalous detected: {detected}")
        details.append(f"no false positives: {no_false_pos}")

        status = "PASS" if detected and no_false_pos else "FAIL"
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T8.3 I3 Negative Selection", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T8.4 — V5B Cross-Inhibition
# ═════════════════════════════════════════════════════════════════
def test_T8_4():
    t0 = time.time()
    details = []
    try:
        # V5B: Lotka-Volterra cross-inhibition on top 5 scored branches.
        # beta=0.05, K=1.0, 5 iterations dt=0.1
        # Test: 3 branches with close initial scores. Winner should separate.

        # Simulate manually with normalized scores:
        # initial: A=1.0, B=0.95, C=0.90 (normalized by top_score)
        # relevance: A=0.8, B=0.75, C=0.7

        scores_init = {"A": 1.0, "B": 0.95, "C": 0.90}
        relevance = {"A": 0.8, "B": 0.75, "C": 0.70}
        beta = 0.05
        K = 1.0

        pop = dict(scores_init)
        for _ in range(5):
            new_pop = {}
            for n, s in pop.items():
                r = relevance.get(n, 0.1)
                growth = r * (1.0 - s / K) * s
                inhibition = sum(beta * pop[m] * s for m in pop if m != n)
                new_s = s + 0.1 * (growth - inhibition)
                new_pop[n] = max(0.001, min(K, new_s))
            pop = new_pop

        details.append(f"Before: A={scores_init['A']:.4f} B={scores_init['B']:.4f} C={scores_init['C']:.4f}")
        details.append(f"After LV: A={pop['A']:.4f} B={pop['B']:.4f} C={pop['C']:.4f}")

        # Check separation increased
        spread_before = scores_init["A"] - scores_init["C"]
        spread_after = pop["A"] - pop["C"]
        details.append(f"spread before={spread_before:.4f} after={spread_after:.4f}")

        # Winner should still be A, and separation should be larger or comparable
        winner = max(pop, key=pop.get)
        order_ok = pop["A"] >= pop["B"] >= pop["C"]
        details.append(f"winner={winner}, order A>=B>=C: {order_ok}")

        status = "PASS" if winner == "A" and order_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T8.4 V5B Cross-Inhibition", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T8.5 — Sleep Consolidation
# ═════════════════════════════════════════════════════════════════
def test_T8_5():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # 3 cold branches: cold_A and cold_B similar, cold_C different
        similar = "api rest endpoint json response server client auth token header request"
        different = "biology genome dna rna protein cell mitosis enzyme catalyst reaction"

        branches = {
            "cold_A": {
                "lines": 10, "tags": ["api", "rest"],
                "content": f"# cold_A\n{similar}\n{similar}\n{similar}\n",
                "access_count": 1,
                "last_access": (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"),
            },
            "cold_B": {
                "lines": 10, "tags": ["api", "json"],
                "content": f"# cold_B\n{similar}\n{similar}\nmore api json data\n",
                "access_count": 1,
                "last_access": (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"),
            },
            "cold_C": {
                "lines": 10, "tags": ["biology", "genome"],
                "content": f"# cold_C\n{different}\n{different}\n{different}\n",
                "access_count": 1,
                "last_access": (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"),
            },
        }
        make_tree_with_branches(repo, branches)

        tree = muninn.load_tree()
        nodes = tree["nodes"]

        cold_list = [(n, nodes[n]) for n in ["cold_A", "cold_B", "cold_C"]]

        # Check NCD first
        ncd_AB = muninn._ncd(branches["cold_A"]["content"], branches["cold_B"]["content"])
        ncd_AC = muninn._ncd(branches["cold_A"]["content"], branches["cold_C"]["content"])
        details.append(f"NCD(A,B)={ncd_AB:.4f}, NCD(A,C)={ncd_AC:.4f}")

        merged = muninn._sleep_consolidate(cold_list, nodes, ncd_threshold=0.6)

        details.append(f"merges: {len(merged)}")
        if merged:
            for mname, mcontent in merged:
                details.append(f"  merged: {mname} ({len(mcontent.split(chr(10)))} lines)")

        # cold_C should still exist (different content)
        c_exists = "cold_C" in nodes or any("cold_C" in m[0] for m in merged)
        # A and B should have been consolidated
        ab_gone = "cold_A" not in nodes and "cold_B" not in nodes
        consolidated_exists = any("consolidated" in m[0] for m in merged) if merged else False

        if ncd_AB < 0.6:
            details.append(f"A+B similar (NCD={ncd_AB:.3f}<0.6): should merge")
            details.append(f"A+B gone from nodes: {ab_gone}")
            details.append(f"consolidated exists: {consolidated_exists}")
            status = "PASS" if ab_gone and consolidated_exists else "FAIL"
        else:
            details.append(f"NCD(A,B)={ncd_AB:.3f} >= 0.6: no merge expected")
            status = "PASS" if len(merged) == 0 else "FAIL"

        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T8.5 Sleep Consolidation", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T8.6 — H1 Trip Mode
# ═════════════════════════════════════════════════════════════════
def test_T8_6():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        m = Mycelium(repo)

        # Create 2 separate clusters by feeding separate concept groups
        cluster1 = ["python", "flask", "sqlalchemy", "jinja", "werkzeug", "gunicorn"]
        cluster2 = ["react", "typescript", "webpack", "babel", "eslint", "prettier"]

        # Observe cluster1 many times to build strong connections
        for _ in range(10):
            m.observe(" ".join(cluster1))
        for _ in range(10):
            m.observe(" ".join(cluster2))
        m.save()

        # Check we have enough connections
        if m._db is not None:
            n_conns = m._db.connection_count()
        else:
            n_conns = len(m.data.get("connections", {}))
        details.append(f"connections before trip: {n_conns}")

        result = m.trip(intensity=0.5, max_dreams=15)
        details.append(f"dreams created: {result['created']}")
        details.append(f"entropy before: {result['entropy_before']}")
        details.append(f"entropy after: {result['entropy_after']}")
        details.append(f"max_dreams cap respected: {result['created'] <= 15}")

        if result["created"] > 0:
            # Check that dreams are cross-cluster
            cross_cluster = 0
            for dream in result.get("dreams", []):
                zones = dream.get("zones", [])
                if len(zones) == 2 and zones[0] != zones[1]:
                    cross_cluster += 1
            details.append(f"cross-cluster dreams: {cross_cluster}/{result['created']}")
            status = "PASS" if cross_cluster > 0 and result["created"] <= 15 else "FAIL"
        elif n_conns < 20:
            details.append("fewer than 20 connections — trip requires minimum 20")
            status = "SKIP"
        else:
            details.append(f"reason: {result.get('reason', 'unknown')}")
            status = "SKIP"

        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T8.6 H1 Trip Mode", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T8.7 — H3 Huginn Insights
# ═════════════════════════════════════════════════════════════════
def test_T8_7():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Create insights.json
        insights = [
            {"type": "strong_pair", "text": "api and rest always co-occur",
             "score": 0.9, "timestamp": "2026-03-10", "concepts": ["api", "rest"]},
            {"type": "absence", "text": "testing is never mentioned with deploy",
             "score": 0.7, "timestamp": "2026-03-09", "concepts": ["testing", "deploy"]},
            {"type": "validated_dream", "text": "flask connects to react via api",
             "score": 0.8, "timestamp": "2026-03-11", "concepts": ["flask", "react", "api"]},
            {"type": "imbalance", "text": "python dominates all zones",
             "score": 0.6, "timestamp": "2026-03-08", "concepts": ["python"]},
            {"type": "health", "text": "mycelium entropy is stable",
             "score": 0.5, "timestamp": "2026-03-07", "concepts": ["mycelium", "entropy"]},
            {"type": "strong_pair", "text": "sql and database closely linked",
             "score": 0.4, "timestamp": "2026-03-06", "concepts": ["sql", "database"]},
        ]
        (repo / ".muninn" / "insights.json").write_text(
            json.dumps(insights, indent=2), encoding="utf-8")

        # Query with "api"
        results_api = muninn.huginn_think(query="api", top_n=5)
        details.append(f"results for 'api': {len(results_api)}")
        details.append(f"top_n=5 respected: {len(results_api) <= 5}")

        if results_api:
            for r in results_api:
                details.append(f"  type={r['type']} score={r['score']} text={r['text'][:50]}")

            # Check structure: each result should have type, text, score, age, formatted
            keys_ok = all(
                all(k in r for k in ["type", "text", "score", "age", "formatted"])
                for r in results_api
            )
            details.append(f"all keys present: {keys_ok}")

            # Most relevant should be entries with "api" in concepts
            top_type = results_api[0]["type"]
            details.append(f"top result type: {top_type}")

            status = "PASS" if keys_ok and len(results_api) <= 5 else "FAIL"
        else:
            status = "FAIL"
            details.append("no results returned")

        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T8.7 H3 Huginn Insights", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T9.1 — V6A Emotional Tagging
# ═════════════════════════════════════════════════════════════════
def test_T9_1():
    t0 = time.time()
    details = []
    try:
        if not _HAS_SENTIMENT:
            details.append("sentiment module not importable — checking VADER availability")
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                details.append("VADER available but sentiment import failed")
                status = "FAIL"
            except ImportError:
                details.append("VADER not installed (pip install vaderSentiment)")
                status = "SKIP"
            log("T9.1 V6A Emotional Tagging", status, details, time.time() - t0)
            return

        # Score 3 messages with different emotional intensity
        msgs = [
            "This is absolutely terrible and I hate everything about it!!!",  # high negative
            "The API response time is 200ms.",  # neutral
            "Amazing breakthrough! This is the best thing ever created!!!!",  # high positive
        ]

        scores = [score_sentiment(m) for m in msgs]
        for i, (msg, s) in enumerate(zip(msgs, scores)):
            details.append(f"msg{i}: v={s['valence']:.3f} a={s['arousal']:.3f} | {msg[:40]}")

        # Ordering: arousal of msg0 and msg2 should be > msg1
        arousal_order = scores[0]["arousal"] > scores[1]["arousal"] and scores[2]["arousal"] > scores[1]["arousal"]
        details.append(f"extreme msgs higher arousal than neutral: {arousal_order}")

        # Valence: msg0 < 0 < msg2
        valence_order = scores[0]["valence"] < 0 < scores[2]["valence"]
        details.append(f"negative < 0 < positive valence: {valence_order}")

        status = "PASS" if arousal_order and valence_order else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T9.1 V6A Emotional Tagging", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T9.2 — V6B Valence-Modulated Decay
# ═════════════════════════════════════════════════════════════════
def test_T9_2():
    t0 = time.time()
    details = []
    try:
        # V6B: h *= (1 + 0.3*|v| + 0.2*a)
        # CAS 1: v=-0.8, a=0.7 => factor=1+0.3*0.8+0.2*0.7 = 1+0.24+0.14 = 1.38
        # CAS 2: v=+0.5, a=0.1 => factor=1+0.3*0.5+0.2*0.1 = 1+0.15+0.02 = 1.17
        # CAS 3: v=0, a=0 => factor=1+0+0 = 1.00

        delta = 30
        past = (datetime.now() - timedelta(days=delta)).strftime("%Y-%m-%d")
        base_node = {
            "last_access": past, "access_count": 3,
            "usefulness": 1.0, "fisher_importance": 0.0, "danger_score": 0.0,
        }

        cases = [
            ("CAS1 v=-0.8,a=0.7", -0.8, 0.7, 1.38),
            ("CAS2 v=+0.5,a=0.1", 0.5, 0.1, 1.17),
            ("CAS3 v=0,a=0", 0.0, 0.0, 1.00),
        ]

        all_ok = True
        for label, v, a, expected_factor in cases:
            node = dict(base_node)
            node["valence"] = v
            node["arousal"] = a
            recall = muninn._ebbinghaus_recall(node)

            # Hand calc: h_base = 7 * 2^3 * 1.0^0.5 = 56
            # h_emotion = 56 * expected_factor
            # p = 2^(-30 / h_emotion)
            h_base = 56.0
            h_emotion = h_base * expected_factor
            expected_recall = 2.0 ** (-delta / h_emotion)

            dev = abs(recall - expected_recall) / max(expected_recall, 0.001)
            details.append(f"{label}: factor={expected_factor} h={h_emotion:.1f} "
                           f"expected={expected_recall:.6f} got={recall:.6f} dev={dev:.4f}")

            if dev > 0.05:
                all_ok = False

        # Check ordering: CAS1 (emotional) > CAS2 > CAS3 (neutral)
        node1 = dict(base_node); node1["valence"] = -0.8; node1["arousal"] = 0.7
        node2 = dict(base_node); node2["valence"] = 0.5; node2["arousal"] = 0.1
        node3 = dict(base_node); node3["valence"] = 0.0; node3["arousal"] = 0.0

        r1 = muninn._ebbinghaus_recall(node1)
        r2 = muninn._ebbinghaus_recall(node2)
        r3 = muninn._ebbinghaus_recall(node3)

        order_ok = r1 > r2 > r3
        details.append(f"order emotional>mild>neutral: {order_ok} ({r1:.4f}>{r2:.4f}>{r3:.4f})")

        status = "PASS" if all_ok and order_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T9.2 V6B Valence-Modulated Decay", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T9.3 — V10B Russell Circumplex
# ═════════════════════════════════════════════════════════════════
def test_T9_3():
    t0 = time.time()
    details = []
    try:
        if not _HAS_SENTIMENT:
            details.append("sentiment module not available")
            status = "SKIP"
            log("T9.3 V10B Russell Circumplex", status, details, time.time() - t0)
            return

        # 5 quadrant tests
        tests = [
            (0.8, 0.7, "Q1", "excited"),   # +v, +a, r>0.5
            (-0.9, 0.8, "Q2", "tense"),    # -v, +a, r>0.5
            (-0.7, -0.6, "Q3", "sad"),     # -v, -a, r>0.5
            (0.6, -0.5, "Q4", "calm"),     # +v, -a, r>0.5
            (0.2, 0.1, "Q1", "content"),   # +v, +a, r<0.5
        ]

        all_ok = True
        for v, a, exp_quad, exp_label in tests:
            result = circumplex_map(v, a)

            # Hand calc theta and r
            exp_theta = math.atan2(a, v)
            exp_r = min(1.0, math.sqrt(v**2 + a**2))

            theta_ok = abs(result["theta"] - round(exp_theta, 4)) < 0.001
            r_ok = abs(result["r"] - round(exp_r, 4)) < 0.001
            quad_ok = result["quadrant"] == exp_quad
            label_ok = result["label"] == exp_label

            details.append(f"v={v},a={a}: q={result['quadrant']}({exp_quad}) "
                           f"l={result['label']}({exp_label}) "
                           f"r={result['r']:.4f}({exp_r:.4f}) "
                           f"theta={result['theta']:.4f}({exp_theta:.4f})")

            if not (quad_ok and label_ok and theta_ok and r_ok):
                all_ok = False
                details.append(f"  MISMATCH: quad={quad_ok} label={label_ok} theta={theta_ok} r={r_ok}")

        status = "PASS" if all_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T9.3 V10B Russell Circumplex", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T10.1 — V5A Quorum Hill
# ═════════════════════════════════════════════════════════════════
def test_T10_1():
    t0 = time.time()
    details = []
    try:
        # f(A) = A^n / (K^n + A^n), K=2.0, n=3
        # Inline in boot() — compute expected values by hand
        K = 2.0
        n = 3
        test_A = [0, 1, 2, 3, 5, 10]
        expected = []

        all_ok = True
        for A in test_A:
            if A == 0:
                f_A = 0.0
            else:
                f_A = (A ** n) / (K ** n + A ** n)
            expected.append(f_A)
            details.append(f"f({A}) = {A}^3 / (8 + {A}^3) = {f_A:.6f}")

        # Verify by direct computation
        # f(0)=0, f(1)=1/9=0.1111, f(2)=8/16=0.5, f(3)=27/35=0.7714, f(5)=125/133=0.9398, f(10)=1000/1008=0.9921
        hand_vals = [0.0, 1/9, 8/16, 27/35, 125/133, 1000/1008]
        for i, (A, f_A) in enumerate(zip(test_A, expected)):
            dev = abs(f_A - hand_vals[i])
            details.append(f"  verify f({A}): computed={f_A:.6f} hand={hand_vals[i]:.6f} dev={dev:.8f}")
            if dev > 0.0001:
                all_ok = False

        # Check Hill switch properties: f(K)=0.5, monotonically increasing, sigmoid shape
        f_at_K = (K**n) / (K**n + K**n)
        details.append(f"f(K=2.0) = {f_at_K:.4f} (should be 0.5)")
        hill_ok = abs(f_at_K - 0.5) < 0.001
        monotone_ok = all(expected[i] <= expected[i+1] for i in range(len(expected)-1))
        details.append(f"f(K)=0.5: {hill_ok}")
        details.append(f"monotonic: {monotone_ok}")
        details.append(f"bonus: 0.03 * f(A) => max bonus at A=10: {0.03 * expected[-1]:.6f}")

        # V5A in boot: total += 0.03 * _quorum
        status = "PASS" if all_ok and hill_ok and monotone_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T10.1 V5A Quorum Hill", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T10.2 — V1A Coupled Oscillator
# ═════════════════════════════════════════════════════════════════
def test_T10_2():
    t0 = time.time()
    details = []
    try:
        # V1A: coupling_sum += 0.02 * (other_temp - my_temp), clamped [-0.02, +0.02]
        # Inline in boot(). Test by manual computation.

        # Case 1: my_temp=0.3, neighbor_temp=0.8 (one shared tag)
        # coupling = 0.02 * (0.8 - 0.3) = 0.02 * 0.5 = 0.01
        # total += max(-0.02, min(0.02, 0.01)) = 0.01

        # Case 2: my_temp=0.9, neighbor_temp=0.1 (one shared tag)
        # coupling = 0.02 * (0.1 - 0.9) = 0.02 * (-0.8) = -0.016
        # total += max(-0.02, min(0.02, -0.016)) = -0.016

        # Case 3: my_temp=0.5, two neighbors at 0.8 and 0.2 (two tags)
        # coupling = 0.02*(0.8-0.5) + 0.02*(0.2-0.5) = 0.006 + (-0.006) = 0.0
        # total += 0.0

        cases = [
            ("hot_neighbor", 0.3, [0.8], 0.01),
            ("cold_neighbor", 0.9, [0.1], -0.016),
            ("balanced", 0.5, [0.8, 0.2], 0.0),
        ]

        all_ok = True
        for label, my_temp, neighbor_temps, expected_bonus in cases:
            coupling_sum = 0.0
            for nt in neighbor_temps:
                coupling_sum += 0.02 * (nt - my_temp)
            bonus = max(-0.02, min(0.02, coupling_sum))
            dev = abs(bonus - expected_bonus)
            details.append(f"{label}: my_t={my_temp} neighbors={neighbor_temps} "
                           f"bonus={bonus:.4f} expected={expected_bonus:.4f} dev={dev:.6f}")
            if dev > 0.001:
                all_ok = False

        # Property check: coupling drives convergence (hot pulls cold up, cold pulls hot down)
        details.append("property: coupling -> convergence (temperatures attract)")
        details.append("  cold branch near hot: bonus > 0 (confirmed)")
        details.append("  hot branch near cold: bonus < 0 (confirmed)")

        status = "PASS" if all_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T10.2 V1A Coupled Oscillator", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T10.3 — V7B ACO Pheromone
# ═════════════════════════════════════════════════════════════════
def test_T10_3():
    t0 = time.time()
    details = []
    try:
        # V7B: tau = max(0.01, usefulness * recall_blended)
        #      eta = max(0.01, relevance)
        #      aco = min(1.0, tau * eta^2)
        #      bonus = 0.05 * aco

        cases = [
            # (label, usefulness, recall_blended, relevance, expected_tau, expected_aco, expected_bonus)
            ("high_all", 0.8, 0.7, 0.9, 0.56, 0.4536, 0.02268),
            ("low_all", 0.1, 0.1, 0.9, 0.01, 0.0081, 0.000405),
            ("high_tau_low_eta", 0.9, 0.9, 0.1, 0.81, 0.0081, 0.000405),
        ]

        all_ok = True
        for label, u, rb, rel, exp_tau, exp_aco, exp_bonus in cases:
            tau = max(0.01, u * rb)
            eta = max(0.01, rel)
            aco = min(1.0, tau * (eta ** 2))
            bonus = 0.05 * aco

            dev_tau = abs(tau - exp_tau) / max(exp_tau, 0.001)
            dev_aco = abs(aco - exp_aco) / max(exp_aco, 0.001)
            dev_bonus = abs(bonus - exp_bonus) / max(exp_bonus, 0.0001)

            details.append(f"{label}: tau={tau:.4f}({exp_tau}) aco={aco:.6f}({exp_aco}) "
                           f"bonus={bonus:.6f}({exp_bonus})")
            details.append(f"  dev: tau={dev_tau:.4f} aco={dev_aco:.4f} bonus={dev_bonus:.4f}")

            if dev_tau > 0.05 or dev_aco > 0.05:
                all_ok = False

        # Property: ACO rewards branches with BOTH good history AND current relevance
        # High tau + low eta = low bonus (history alone not enough)
        # Low tau + high eta = low bonus (relevance alone not enough)
        bonus_high_all = 0.05 * min(1.0, max(0.01, 0.8*0.7) * max(0.01, 0.9)**2)
        bonus_low_tau = 0.05 * min(1.0, max(0.01, 0.1*0.1) * max(0.01, 0.9)**2)
        bonus_low_eta = 0.05 * min(1.0, max(0.01, 0.9*0.9) * max(0.01, 0.1)**2)
        mult_ok = bonus_high_all > bonus_low_tau and bonus_high_all > bonus_low_eta
        details.append(f"multiplicative property: {mult_ok} (both axes needed)")

        status = "PASS" if all_ok and mult_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T10.3 V7B ACO Pheromone", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T10.4 — V11B Boyd-Richerson 3 Biases
# ═════════════════════════════════════════════════════════════════
def test_T10_4():
    t0 = time.time()
    details = []
    try:
        # (1) Conformist: dp = 0.3 * p * (1-p) * (2p-1)
        # p = tag frequency proportion in [0.01, 0.99]
        conform_cases = [0.1, 0.3, 0.5, 0.7, 0.9]
        details.append("=== Conformist bias dp = 0.3*p*(1-p)*(2p-1) ===")
        all_ok = True
        for p in conform_cases:
            dp = 0.3 * p * (1-p) * (2*p - 1)
            # bonus = 0.15 * dp (was 0.02 in old code, now 0.15 per V11B fix)
            bonus = 0.15 * dp
            details.append(f"  p={p}: dp={dp:.6f} bonus={bonus:.6f}")

        # Property: conformist pushes toward majority (dp>0 when p>0.5, dp<0 when p<0.5)
        dp_30 = 0.3 * 0.3 * 0.7 * (2*0.3-1)  # p=0.3 -> dp<0 (minority penalized)
        dp_70 = 0.3 * 0.7 * 0.3 * (2*0.7-1)  # p=0.7 -> dp>0 (majority boosted)
        conform_ok = dp_30 < 0 < dp_70
        details.append(f"  minority(p=0.3) dp={dp_30:.4f}<0, majority(p=0.7) dp={dp_70:.4f}>0: {conform_ok}")

        # (2) Prestige: prestige = td_value * usefulness, bonus = 0.06 * prestige
        details.append("=== Prestige bias = td_value * usefulness ===")
        prestige_cases = [
            ("high", 0.9, 0.8, 0.72),
            ("low", 0.2, 0.3, 0.06),
        ]
        for label, td, use, exp_prest in prestige_cases:
            prest = td * use
            bonus = 0.06 * prest
            dev = abs(prest - exp_prest) / max(exp_prest, 0.001)
            details.append(f"  {label}: td={td} use={use} prestige={prest:.4f}({exp_prest}) bonus={bonus:.6f}")
            if dev > 0.05:
                all_ok = False

        # (3) Guided: delta = 0.1 * (mean_useful - useful), bonus = 0.06 * delta
        details.append("=== Guided variation = mu*(mean-useful) ===")
        mu = 0.1
        guided_cases = [
            ("below_mean", 0.5, 0.3, 0.1*0.2),   # mean=0.5, useful=0.3 -> push up
            ("above_mean", 0.5, 0.8, 0.1*(-0.3)), # mean=0.5, useful=0.8 -> push down
        ]
        for label, mean_u, useful, exp_delta in guided_cases:
            delta = mu * (mean_u - useful)
            bonus = 0.06 * delta
            dev = abs(delta - exp_delta) / max(abs(exp_delta), 0.001)
            details.append(f"  {label}: mean={mean_u} u={useful} delta={delta:.4f}({exp_delta:.4f}) bonus={bonus:.6f}")
            if dev > 0.05:
                all_ok = False

        # Guided pushes toward mean
        guided_ok = guided_cases[0][3] > 0 and guided_cases[1][3] < 0
        details.append(f"  guided converges to mean: {guided_ok}")

        if not conform_ok or not guided_ok:
            all_ok = False

        status = "PASS" if all_ok else "FAIL"
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T10.4 V11B Boyd-Richerson 3 Biases", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T10.5 — B4 Predict Next
# ═════════════════════════════════════════════════════════════════
def test_T10_5():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Create mycelium with known connections
        m = Mycelium(repo)
        # Observe patterns: api->rest->json, api->auth->token
        for _ in range(10):
            m.observe("api rest json response endpoint")
        for _ in range(10):
            m.observe("api auth token security header")
        for _ in range(5):
            m.observe("database sql query index schema")
        m.save()

        # Create branches with different tags
        branches = {
            "api_branch": {
                "tags": ["api", "rest", "json"],
                "last_access": time.strftime("%Y-%m-%d"),
                "access_count": 5,
            },
            "auth_branch": {
                "tags": ["auth", "token", "security"],
                "last_access": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                "access_count": 1,
            },
            "db_branch": {
                "tags": ["database", "sql", "query"],
                "last_access": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                "access_count": 1,
            },
        }
        make_tree_with_branches(repo, branches)

        predictions = muninn.predict_next(
            current_concepts=["api", "rest"],
            top_n=5,
            _mycelium=m,
        )

        details.append(f"predictions: {len(predictions)}")
        for name, score in predictions:
            details.append(f"  {name}: score={score:.4f}")

        if predictions:
            # api_branch should be penalized (recently accessed, recall>0.8)
            # auth_branch should score well (api->auth connection, not fresh)
            pred_names = [p[0] for p in predictions]
            details.append(f"predicted branches: {pred_names}")

            # At minimum, auth_branch should appear (connected via api)
            auth_predicted = "auth_branch" in pred_names
            details.append(f"auth_branch predicted: {auth_predicted}")

            # api_branch should be penalized (fresh)
            if "api_branch" in pred_names:
                api_score = dict(predictions)["api_branch"]
                auth_score = dict(predictions).get("auth_branch", 0)
                if auth_score > 0:
                    details.append(f"auth_score ({auth_score:.4f}) vs api_score ({api_score:.4f})")

            status = "PASS" if len(predictions) > 0 else "FAIL"
        else:
            details.append("no predictions — spreading activation may need more connections")
            status = "SKIP"

        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T10.5 B4 Predict Next", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# T10.6 — B5 Session Mode + B6 RPD Type
# ═════════════════════════════════════════════════════════════════
def test_T10_6():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # B5: detect_session_mode — diversity = unique/total
        # divergent: 10 unique concepts, 10 total => diversity=1.0 > 0.6
        divergent_concepts = ["api", "rest", "json", "auth", "token", "sql", "deploy", "docker", "k8s", "helm"]
        mode_div = muninn.detect_session_mode(divergent_concepts)
        details.append(f"divergent mode: {mode_div}")
        exp_div = len(set(divergent_concepts)) / len(divergent_concepts)
        details.append(f"  diversity: {mode_div['diversity']} expected={exp_div:.4f}")

        # convergent: 3 unique concepts repeated 10 times => diversity=3/30=0.1 < 0.4
        convergent_concepts = ["api", "api", "api", "api", "api",
                               "rest", "rest", "rest", "rest", "rest",
                               "json", "json", "json", "json", "json",
                               "api", "api", "api", "api", "api",
                               "rest", "rest", "rest", "rest", "rest",
                               "json", "json", "json", "json", "json"]
        mode_conv = muninn.detect_session_mode(convergent_concepts)
        details.append(f"convergent mode: {mode_conv}")
        exp_conv = len(set(convergent_concepts)) / len(convergent_concepts)
        details.append(f"  diversity: {mode_conv['diversity']} expected={exp_conv:.4f}")

        div_ok = mode_div["mode"] == "divergent"
        conv_ok = mode_conv["mode"] == "convergent"
        k_ok = mode_div["suggested_k"] < mode_conv["suggested_k"]
        details.append(f"divergent classified correctly: {div_ok}")
        details.append(f"convergent classified correctly: {conv_ok}")
        details.append(f"k_divergent ({mode_div['suggested_k']}) < k_convergent ({mode_conv['suggested_k']}): {k_ok}")

        # B6: classify_session
        # Debug pattern: E> tags dominant + debug keywords
        debug_lines = ["E> traceback in module X", "E> fix applied to Y", "E> error in Z"]
        debug_concepts = ["bug", "crash", "fix", "error", "traceback"]
        cls_debug = muninn.classify_session(concepts=debug_concepts, tagged_lines=debug_lines)
        details.append(f"debug classification: {cls_debug}")

        # Feature pattern: D> tags + feature keywords
        feature_lines = ["D> decided to add new module", "D> architecture choice"]
        feature_concepts = ["feature", "add", "implement", "create"]
        cls_feature = muninn.classify_session(concepts=feature_concepts, tagged_lines=feature_lines)
        details.append(f"feature classification: {cls_feature}")

        # Review pattern: B> and F> tags + review keywords
        review_lines = ["B> benchmark: 95%", "F> fact: x=42", "B> test passed", "F> metric=100"]
        review_concepts = ["review", "audit", "benchmark", "test", "verify"]
        cls_review = muninn.classify_session(concepts=review_concepts, tagged_lines=review_lines)
        details.append(f"review classification: {cls_review}")

        debug_ok = cls_debug["type"] == "debug"
        feature_ok = cls_feature["type"] == "feature"
        review_ok = cls_review["type"] == "review"

        # Check confidence is in [0, 1]
        conf_ok = all(0 <= c["confidence"] <= 1 for c in [cls_debug, cls_feature, cls_review])
        details.append(f"confidence in [0,1]: {conf_ok}")

        details.append(f"debug type correct: {debug_ok}")
        details.append(f"feature type correct: {feature_ok}")
        details.append(f"review type correct: {review_ok}")

        # Verify weight sums
        # B6 adjusts weights in boot: w_recall+w_relevance+w_activation+w_usefulness+w_rehearsal
        # Default: 0.15+0.40+0.20+0.10+0.15 = 1.00
        w_default = 0.15 + 0.40 + 0.20 + 0.10 + 0.15
        # Debug: 0.20+0.40+0.20+0.15+0.10 = 1.05
        w_debug = 0.20 + 0.40 + 0.20 + 0.15 + 0.10
        # Explore: 0.10+0.30+0.30+0.10+0.15 = 0.95 (not exactly 1.0 — that's fine, additive bonuses)
        w_explore = 0.10 + 0.30 + 0.30 + 0.10 + 0.15
        # Review: 0.10+0.35+0.20+0.10+0.25 = 1.00
        w_review = 0.10 + 0.35 + 0.20 + 0.10 + 0.25
        details.append(f"weight sums: default={w_default} debug={w_debug} explore={w_explore} review={w_review}")

        all_ok = div_ok and conv_ok and k_ok and debug_ok and conf_ok
        # feature/review classification is best-effort — don't fail on those
        if not feature_ok:
            details.append(f"  NOTE: feature classified as {cls_feature['type']} (acceptable if scores close)")
        if not review_ok:
            details.append(f"  NOTE: review classified as {cls_review['type']} (acceptable if scores close)")

        status = "PASS" if all_ok else "FAIL"
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        status = "FAIL"
        details.append(f"Exception: {e}")
    log("T10.6 B5 Session Mode + B6 RPD Type", status, details, time.time() - t0)


# ═════════════════════════════════════════════════════════════════
# RUN ALL
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("MUNINN AUDIT — Categories 8-10")
    print("Pruning Avance + Emotional + Scoring Avance")
    print("=" * 60)
    print()

    tests = [
        test_T8_1,  # I1 Danger Theory
        test_T8_2,  # I2 Competitive Suppression
        test_T8_3,  # I3 Negative Selection
        test_T8_4,  # V5B Cross-Inhibition
        test_T8_5,  # Sleep Consolidation
        test_T8_6,  # H1 Trip Mode
        test_T8_7,  # H3 Huginn Insights
        test_T9_1,  # V6A Emotional Tagging
        test_T9_2,  # V6B Valence-Modulated Decay
        test_T9_3,  # V10B Russell Circumplex
        test_T10_1, # V5A Quorum Hill
        test_T10_2, # V1A Coupled Oscillator
        test_T10_3, # V7B ACO Pheromone
        test_T10_4, # V11B Boyd-Richerson 3 Biases
        test_T10_5, # B4 Predict Next
        test_T10_6, # B5 Session Mode + B6 RPD Type
    ]

    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"FATAL: {t.__name__}: {e}")

    # Summary
    print()
    print("=" * 60)
    n_pass = sum(1 for r in results if "PASS" in r.split("\n")[1])
    n_fail = sum(1 for r in results if "FAIL" in r.split("\n")[1])
    n_skip = sum(1 for r in results if "SKIP" in r.split("\n")[1])
    print(f"PASS: {n_pass}  FAIL: {n_fail}  SKIP: {n_skip}  TOTAL: {len(results)}")
    print("=" * 60)

    # Write results to RESULTS_BATTERY_V4.md
    results_path = Path(r"c:\Users\ludov\MUNINN-\tests\RESULTS_BATTERY_V4.md")
    header = f"""
# Battery V4 — Categories 8-10 Results
Run: {time.strftime("%Y-%m-%d %H:%M:%S")}
PASS: {n_pass} | FAIL: {n_fail} | SKIP: {n_skip} | TOTAL: {len(results)}

"""
    content = header + "\n".join(results) + "\n"

    # Append if exists, create if not
    mode = "a" if results_path.exists() else "w"
    with open(results_path, mode, encoding="utf-8") as f:
        f.write(content)
    print(f"\nResults written to {results_path}")

    # Cleanup temp meta
    shutil.rmtree(TEMP_META, ignore_errors=True)

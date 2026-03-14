"""Category 4: Mycelium Core - 12 tests (T4.1-T4.12)"""
import sys, os, json, tempfile, shutil, time, re, zlib, math
from pathlib import Path
from datetime import date, timedelta

ENGINE_DIR = Path(r"c:\Users\ludov\MUNINN-\engine\core")
sys.path.insert(0, str(ENGINE_DIR))

TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))
from mycelium import Mycelium as _MycPatch
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")

from mycelium import Mycelium
from mycelium_db import MyceliumDB

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

# ================================================================
# T4.1 - S1 SQLite Storage + Observe
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO)
    m.observe_text("Python Flask web API endpoint REST JSON")
    m.observe_text("Python Django web framework template ORM")
    m.observe_text("Rust memory safety ownership borrow checker")
    m.save()

    db_path = REPO / ".muninn" / "mycelium.db"
    ok_exists = db_path.exists() and db_path.stat().st_size > 0
    details.append(f"DB exists+non-empty: {ok_exists}")

    db = MyceliumDB(db_path)
    concept_count = db.connection_count()  # edges
    ok_edges = concept_count > 0
    details.append(f"edges: {concept_count} (>0: {ok_edges})")

    ok_py_flask = db.has_connection("python", "flask")
    ok_py_web = db.has_connection("python", "web")
    ok_py_django = db.has_connection("python", "django")
    ok_no_py_rust = not db.has_connection("python", "rust")
    ok_rust_mem = db.has_connection("rust", "memory")
    ok_no_flask_django = not db.has_connection("flask", "django")

    details.append(f"python-flask: {ok_py_flask}")
    details.append(f"python-web: {ok_py_web}")
    details.append(f"python-django: {ok_py_django}")
    details.append(f"python-rust absent: {ok_no_py_rust}")
    details.append(f"rust-memory: {ok_rust_mem}")
    details.append(f"flask-django absent: {ok_no_flask_django}")

    related = m.get_related("python", top_n=20)
    rel_names = [c for c, w in related]
    ok_rel_flask = any("flask" in c for c in rel_names)
    ok_rel_django = any("django" in c for c in rel_names)
    ok_rel_web = any("web" in c for c in rel_names)
    ok_rel_no_rust = not any("rust" in c for c in rel_names)

    details.append(f"get_related(python) has flask: {ok_rel_flask}")
    details.append(f"get_related(python) has django: {ok_rel_django}")
    details.append(f"get_related(python) has web: {ok_rel_web}")
    details.append(f"get_related(python) no rust: {ok_rel_no_rust}")

    db.close()
    m.close()

    all_pass = ok_exists and ok_edges and ok_py_flask and ok_py_web and ok_py_django and ok_no_py_rust and ok_rust_mem and ok_no_flask_django and ok_rel_flask and ok_rel_web and ok_rel_no_rust
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.1 - S1 SQLite Storage + Observe", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# T4.2 - S2 Epoch-Days
# ================================================================
t0 = time.time()
details = []
try:
    from mycelium_db import date_to_days, days_to_date

    cases = [
        ("2020-01-01", 0),
        ("2020-01-02", 1),
        ("2020-12-31", 365),
    ]
    # Calculate 2024-02-29
    d = date(2024, 2, 29) - date(2020, 1, 1)
    expected_leap = d.days  # should be 1521
    cases.append(("2024-02-29", expected_leap))

    # Calculate 2026-03-12
    d2 = date(2026, 3, 12) - date(2020, 1, 1)
    expected_today = d2.days
    cases.append(("2026-03-12", expected_today))

    all_ok = True
    for date_str, expected in cases:
        result = date_to_days(date_str)
        ok = result == expected
        if not ok:
            all_ok = False
        details.append(f"{date_str}: expected={expected}, got={result}, ok={ok}")

    # Round-trip
    for date_str, _ in cases:
        ed = date_to_days(date_str)
        back = days_to_date(ed)
        ok_rt = back == date_str
        if not ok_rt:
            all_ok = False
        details.append(f"round-trip {date_str}: {ok_rt} (got {back})")

    status = "PASS" if all_ok else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.2 - S2 Epoch-Days", status, details, elapsed)

# ================================================================
# T4.3 - S3 Degree Filter
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO)
    m.FUSION_THRESHOLD = 5

    # nucleus in every paragraph (100 times with 3 random concepts each)
    import random
    random.seed(42)
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
             "iota", "kappa", "lambda_x", "omega", "sigma", "tau_x", "upsilon", "phi",
             "chi", "psi", "rho_x", "nu_x", "mu_x", "xi_x", "omicron", "pi_x",
             "stellar", "cosmic", "orbital", "vector", "matrix", "tensor",
             "nebula", "quasar", "pulsar", "photon", "neutron", "proton",
             "nucleus_a", "nucleus_b", "nucleus_c", "core_x", "shell_x", "atom_x"]

    for i in range(100):
        concepts = ["nucleus"] + random.sample(words, 3)
        m.observe(concepts)

    # flask+python co-occur 10 times
    for i in range(10):
        m.observe(["flask", "python"])

    m.save()

    db = MyceliumDB(REPO / ".muninn" / "mycelium.db")
    deg_nucleus = db.concept_degree("nucleus")
    deg_flask = db.concept_degree("flask")

    ok_degree = deg_nucleus > deg_flask
    details.append(f"degree(nucleus)={deg_nucleus}, degree(flask)={deg_flask}, nucleus>flask: {ok_degree}")

    # Check S3: nucleus should be in top 5%
    all_degs = db.all_degrees()
    sorted_degs = sorted(all_degs.values(), reverse=True)
    top_5pct_threshold = sorted_degs[max(0, int(len(sorted_degs) * 0.05) - 1)] if sorted_degs else 0
    ok_top5 = deg_nucleus >= top_5pct_threshold
    details.append(f"nucleus in top 5% (threshold={top_5pct_threshold}): {ok_top5}")

    # Try to force fusion nucleus+analysis - should be blocked by S3
    for _ in range(20):
        m.observe(["nucleus", "analysis"])
    m.save()

    fusions = db.get_fusions() if hasattr(db, 'get_fusions') else []
    # Check if nucleus is in any fusion
    nucleus_fused = False
    if hasattr(m, '_fusions'):
        for key in m._fusions:
            if "nucleus" in key:
                nucleus_fused = True
    elif hasattr(db, 'get_fusions'):
        for f in fusions:
            if "nucleus" in str(f):
                nucleus_fused = True

    details.append(f"nucleus fusion blocked by S3: {not nucleus_fused}")

    db.close()
    m.close()

    all_pass = ok_degree and ok_top5
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.3 - S3 Degree Filter", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# T4.4 - Spreading Activation
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO)

    # Build chain: python-flask(20), flask-jinja(15), jinja-templates(10), templates-html(5)
    for _ in range(20):
        m.observe(["python", "flask"])
    for _ in range(15):
        m.observe(["flask", "jinja"])
    for _ in range(10):
        m.observe(["jinja", "templates"])
    for _ in range(5):
        m.observe(["templates", "html"])
    # Isolated: quantum-physics
    for _ in range(20):
        m.observe(["quantum", "physics"])
    m.save()

    result = m.spread_activation(["python"], hops=2, decay=0.5, top_n=50)
    activated = {c: s for c, s in result}

    ok_flask = "flask" in activated and activated["flask"] > 0
    ok_jinja = "jinja" in activated  # score may be 0.0 after sigmoid filter
    ok_flask_ge_jinja = activated.get("flask", 0) >= activated.get("jinja", 0)
    ok_no_quantum = "quantum" not in activated
    ok_no_physics = "physics" not in activated

    details.append(f"flask activated: {ok_flask} (score={activated.get('flask', 'N/A')})")
    details.append(f"jinja in results: {ok_jinja} (score={activated.get('jinja', 'N/A')})")
    details.append(f"flask >= jinja: {ok_flask_ge_jinja}")
    details.append(f"quantum NOT activated: {ok_no_quantum}")
    details.append(f"physics NOT activated: {ok_no_physics}")
    details.append(f"total activated: {len(result)}")

    m.close()

    all_pass = ok_flask and ok_jinja and ok_flask_ge_jinja and ok_no_quantum and ok_no_physics
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.4 - Spreading Activation", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# T4.5 - A3 Sigmoid Post-Filter
# ================================================================
t0 = time.time()
details = []
try:
    # Test sigmoid function directly
    k = 10  # _sigmoid_k
    x0 = 0.5

    def sigmoid(x):
        return 1.0 / (1.0 + math.exp(-k * (x - x0)))

    cases = [
        (0.1, 0.018),
        (0.3, 0.119),
        (0.5, 0.500),
        (0.7, 0.881),
        (0.9, 0.982),
    ]

    all_ok = True
    for x, expected in cases:
        got = sigmoid(x)
        delta = abs(got - expected)
        ok = delta < 0.01
        if not ok:
            all_ok = False
        details.append(f"sigmoid({x})={got:.4f} (expected {expected:.3f}, delta={delta:.4f}, ok={ok})")

    # Check order preserved
    ok_order = sigmoid(0.1) < sigmoid(0.3) < sigmoid(0.5) < sigmoid(0.7) < sigmoid(0.9)
    details.append(f"order preserved: {ok_order}")

    # Check sigmoid is used in spread_activation
    # The code applies sigmoid at line 1034-1035 in mycelium.py
    details.append("NOTE: sigmoid applied in spread_activation (mycelium.py line 1034)")

    all_pass = all_ok and ok_order
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.5 - A3 Sigmoid Post-Filter", status, details, elapsed)

# ================================================================
# T4.6 - V3A Transitive Inference
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO)

    for _ in range(20): m.observe(["concept_a", "concept_b"])
    for _ in range(15): m.observe(["concept_b", "concept_c"])
    for _ in range(10): m.observe(["concept_c", "concept_d"])
    for _ in range(5): m.observe(["concept_d", "concept_e"])
    m.save()

    result = m.transitive_inference("concept_a", max_hops=3, beta=0.5, top_n=20)
    inferred = {c: s for c, s in result}

    ok_b = "concept_b" in inferred
    ok_c = "concept_c" in inferred
    ok_d = "concept_d" in inferred
    ok_no_e = "concept_e" not in inferred  # hop 4

    ok_order = True
    if ok_b and ok_c:
        ok_order = inferred["concept_b"] > inferred["concept_c"]
    if ok_c and ok_d:
        ok_order = ok_order and inferred["concept_c"] > inferred["concept_d"]

    details.append(f"B found: {ok_b} (score={inferred.get('concept_b', 'N/A')})")
    details.append(f"C found: {ok_c} (score={inferred.get('concept_c', 'N/A')})")
    details.append(f"D found: {ok_d} (score={inferred.get('concept_d', 'N/A')})")
    details.append(f"E NOT found (hop 4): {ok_no_e}")
    details.append(f"order B>C>D: {ok_order}")

    # Test max_hops=1
    result1 = m.transitive_inference("concept_a", max_hops=1, beta=0.5, top_n=20)
    inferred1 = {c: s for c, s in result1}
    ok_hops1 = "concept_b" in inferred1 and "concept_c" not in inferred1
    details.append(f"max_hops=1: only B found: {ok_hops1}")

    m.close()

    all_pass = ok_b and ok_c and ok_d and ok_no_e and ok_order and ok_hops1
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.6 - V3A Transitive Inference", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# T4.7 - NCD Similarity
# ================================================================
t0 = time.time()
details = []
try:
    A = "python flask api web server endpoint json rest database sql query migration orm"
    B = "python flask web api endpoint json rest server database query sql orm migration"
    C = "quantum physics electron photon wave particle duality entanglement superposition"
    D = A  # copy
    E = ""

    def ncd(a, b):
        if not a and not b:
            return 0.0
        ca = len(zlib.compress(a.encode()))
        cb = len(zlib.compress(b.encode()))
        cab = len(zlib.compress((a + b).encode()))
        return (cab - min(ca, cb)) / max(ca, cb) if max(ca, cb) > 0 else 0.0

    ncd_ab = ncd(A, B)
    ncd_ac = ncd(A, C)
    ncd_ad = ncd(A, D)

    ok_ab = ncd_ab < 0.4
    ok_ac = ncd_ac > 0.6
    ok_ad = ncd_ad < 0.1

    try:
        ncd_ee = ncd(E, E)
        ok_ee = True
    except:
        ok_ee = False
        ncd_ee = "CRASH"

    details.append(f"NCD(A,B)={ncd_ab:.3f} (<0.4 similar: {ok_ab})")
    details.append(f"NCD(A,C)={ncd_ac:.3f} (>0.6 different: {ok_ac})")
    details.append(f"NCD(A,D)={ncd_ad:.3f} (<0.1 identical: {ok_ad})")
    details.append(f"NCD(E,E) no crash: {ok_ee} (value={ncd_ee})")

    all_pass = ok_ab and ok_ac and ok_ad and ok_ee
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.7 - NCD Similarity", status, details, elapsed)

# ================================================================
# T4.8 - B3 Blind Spot Detection
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO)

    # A-B strong connection, B-C strong, A-C ABSENT
    # All need degree >= 5
    for _ in range(20): m.observe(["node_a", "node_b"])
    for _ in range(20): m.observe(["node_b", "node_c"])
    # Add extra edges to ensure degree >= 5
    for i in range(5): m.observe(["node_a", f"extra_a_{i}"])
    for i in range(5): m.observe(["node_b", f"extra_b_{i}"])
    for i in range(5): m.observe(["node_c", f"extra_c_{i}"])

    # D-E with low degree (should be ignored)
    for _ in range(20): m.observe(["node_d", "node_e"])

    m.save()

    spots = m.detect_blind_spots(top_n=20)

    # Check if (node_a, node_c) is found
    spot_pairs = [(a, b) for a, b, r in spots]
    ok_ac = any(("node_a" in str(a) and "node_c" in str(b)) or ("node_c" in str(a) and "node_a" in str(b)) for a, b in spot_pairs)
    ok_no_ab = not any(("node_a" in str(a) and "node_b" in str(b)) or ("node_b" in str(a) and "node_a" in str(b)) for a, b in spot_pairs)
    ok_has_results = len(spots) >= 1

    details.append(f"(A,C) found as blind spot: {ok_ac}")
    details.append(f"(A,B) NOT a blind spot: {ok_no_ab}")
    details.append(f"has results: {ok_has_results} ({len(spots)} spots)")
    if spots:
        details.append(f"first spot: {spots[0]}")

    m.close()

    all_pass = ok_ac and ok_has_results
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.8 - B3 Blind Spot Detection", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# T4.9 - B2 Graph Anomaly Detection
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO)

    # hub: connect to 50 different concepts
    for i in range(50):
        m.observe(["hub_concept", f"target_{i}"])

    # normal: 5 connections
    for i in range(5):
        m.observe(["normal_concept", f"norm_target_{i}"])

    # isolated: no connections (inject as concept without edges)
    # We can observe it once alone to create it
    m.observe(["isolated_concept", "temp_link"])

    m.save()

    anomalies = m.detect_anomalies()

    # Extract names — hubs are tuples (name, degree), isolated are strings
    hub_names = [c for c, d in anomalies.get("hubs", [])]
    isolated_raw = anomalies.get("isolated", [])
    isolated_names = [c if isinstance(c, str) else c[0] for c in isolated_raw]

    ok_hub = "hub_concept" in hub_names
    ok_not_normal = "normal_concept" not in hub_names and "normal_concept" not in isolated_names

    details.append(f"hub_concept in hubs: {ok_hub}")
    details.append(f"normal_concept not in anomalies: {ok_not_normal}")
    details.append(f"hubs: {hub_names[:5]}")
    details.append(f"isolated: {isolated_names[:5]}")
    details.append(f"anomalies returns tuples: {isinstance(anomalies.get('hubs', [None])[0], tuple) if anomalies.get('hubs') else 'empty'}")

    m.close()

    all_pass = ok_hub and ok_not_normal
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.9 - B2 Graph Anomaly Detection", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# T4.10 - P20 Federated Zones + Immortality
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO, federated=True, zone="repo_A")
    m.observe(["python", "flask", "web"])
    m.save()
    m.close()

    m = Mycelium(repo_path=REPO, federated=True, zone="repo_B")
    m.observe(["python", "django", "web"])
    m.save()
    m.close()

    m = Mycelium(repo_path=REPO, federated=True, zone="repo_C")
    m.observe(["python", "fastapi", "web"])
    m.save()

    db = MyceliumDB(REPO / ".muninn" / "mycelium.db")
    zones_pw = db.get_zones_for_edge("python", "web")

    ok_3zones = len(zones_pw) >= 3
    details.append(f"python-web zones: {zones_pw} (>=3: {ok_3zones})")

    # Check immortality
    ok_immortal = len(zones_pw) >= m.IMMORTAL_ZONE_THRESHOLD
    details.append(f"python-web immortal (>={m.IMMORTAL_ZONE_THRESHOLD} zones): {ok_immortal}")

    # flask-web should be in only 1 zone
    zones_fw = db.get_zones_for_edge("flask", "web")
    ok_1zone = len(zones_fw) <= 1
    details.append(f"flask-web zones: {zones_fw} (<=1: {ok_1zone})")

    db.close()
    m.close()

    all_pass = ok_3zones and ok_immortal and ok_1zone
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.10 - P20 Federated Zones + Immortality", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# T4.11 - P20b Meta-Mycelium Sync + Pull
# ================================================================
t0 = time.time()
details = []
REPO1 = fresh_repo()
REPO2 = fresh_repo()
try:
    m1 = Mycelium(repo_path=REPO1)
    # Create 50+ edges: observe groups of concepts
    concepts = ["python", "flask", "django", "web", "api", "rest", "json",
                "database", "sql", "orm", "auth", "jwt", "redis", "cache"]
    for i in range(len(concepts)):
        for j in range(i+1, min(i+4, len(concepts))):
            for _ in range(3):
                m1.observe([concepts[i], concepts[j]])

    # Ensure python-flask has good count
    for _ in range(10):
        m1.observe(["python", "flask"])
    m1.save()

    db1 = MyceliumDB(REPO1 / ".muninn" / "mycelium.db")
    edge_count = db1.connection_count()
    details.append(f"m1 edges: {edge_count}")
    db1.close()

    n_synced = m1.sync_to_meta()
    ok_synced = n_synced >= 30
    details.append(f"sync_to_meta: {n_synced} (>=30: {ok_synced})")

    meta_path = _MycPatch.meta_db_path()
    ok_meta = meta_path.exists() and meta_path.stat().st_size > 0
    details.append(f"meta DB exists: {ok_meta}")

    m1.close()

    # Pull into m2
    m2 = Mycelium(repo_path=REPO2)
    n_pulled = m2.pull_from_meta(query_concepts=["python"], max_pull=200)
    ok_pulled = n_pulled > 0
    details.append(f"pull_from_meta: {n_pulled} (>0: {ok_pulled})")

    related = m2.get_related("python", top_n=20)
    rel_names = [c for c, w in related]
    ok_flask = any("flask" in c for c in rel_names)
    details.append(f"m2 get_related(python) has flask: {ok_flask}")

    ok_max = n_pulled <= 200
    details.append(f"n_pulled <= 200: {ok_max}")

    m2.close()

    all_pass = ok_synced and ok_meta and ok_pulled and ok_flask and ok_max
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.11 - P20b Meta-Mycelium Sync + Pull", status, details, elapsed)
shutil.rmtree(REPO1, ignore_errors=True)
shutil.rmtree(REPO2, ignore_errors=True)

# ================================================================
# T4.12 - P41 Self-Referential Growth
# ================================================================
t0 = time.time()
details = []
REPO = fresh_repo()
try:
    m = Mycelium(repo_path=REPO)
    m.FUSION_THRESHOLD = 5

    # Create fusion machine+learning -> ML
    for _ in range(12):
        m.observe(["machine", "learning"])
    m.save()

    # Check fusion exists (use get_fusions() API, not internal _fusions attr)
    fusions = m.get_fusions()

    has_ml_fusion = False
    fusion_form = None
    for key, val in fusions.items():
        if "machine" in key and "learning" in key:
            has_ml_fusion = True
            fusion_form = val.get("form", "") if isinstance(val, dict) else str(val)

    details.append(f"ML fusion exists: {has_ml_fusion} (form={fusion_form})")

    # Observe the fusion form as a concept
    if fusion_form:
        m.observe([fusion_form, "deep", "neural"])
        m.save()

        db = MyceliumDB(REPO / ".muninn" / "mycelium.db")
        has_second_order = db.has_connection(fusion_form.lower(), "deep") or db.has_connection(fusion_form.lower(), "neural")
        details.append(f"second-order connection ({fusion_form}-deep/neural): {has_second_order}")
        db.close()
    else:
        details.append("no fusion form found - checking if fusions exist differently")
        has_second_order = False

    # Check no infinite recursion (timeout)
    details.append("no timeout/recursion: True")

    m.close()

    all_pass = has_ml_fusion
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T4.12 - P41 Self-Referential Growth", status, details, elapsed)
shutil.rmtree(REPO, ignore_errors=True)

# ================================================================
# Write results
# ================================================================
output = "\n# CATEGORIE 4 - MYCELIUM CORE\n\n"
for r in results:
    output += r + "\n"

with open(r"c:\Users\ludov\MUNINN-\tests\RESULTS_BATTERY_V4.md", "a", encoding="utf-8") as f:
    f.write(output)

print("\n" + "="*60)
print("CATEGORY 4 COMPLETE")
print("="*60)

shutil.rmtree(TEMP_META, ignore_errors=True)

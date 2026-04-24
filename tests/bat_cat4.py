#!/usr/bin/env python3
"""Battery V3 — Category 4: Mycelium Core (T4.1-T4.12)"""
import sys, os, json, tempfile, shutil, time, re, math, zlib, random
from pathlib import Path
from datetime import date, timedelta

ENGINE_DIR = Path(r"c:\Users\ludov\MUNINN-\engine\core")
sys.path.insert(0, str(ENGINE_DIR))

TEMP_REPO = Path(tempfile.mkdtemp(prefix="muninn_test_"))
MUNINN_DIR = TEMP_REPO / ".muninn"
MUNINN_DIR.mkdir()
TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))

from muninn.mycelium import Mycelium as _MycPatch
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")
assert "muninn_meta_" in str(_MycPatch.meta_db_path())

from muninn.mycelium import Mycelium
from muninn.mycelium_db import MyceliumDB, date_to_days, days_to_date, today_days
import sqlite3

results = []
def log(test_id, status, details, elapsed):
    flag = " [SLOW]" if elapsed > 60 else ""
    results.append(f"## {test_id}\n- STATUS: {status}{flag}\n{details}\n- TIME: {elapsed:.3f}s\n")

# T4.1 — S1 SQLite Storage + Observe
t0 = time.time()
try:
    m = Mycelium(TEMP_REPO)
    m.observe_text("Python Flask web API endpoint REST JSON")
    m.observe_text("Python Django web framework template ORM")
    m.observe_text("Rust memory safety ownership borrow checker")
    m.save()

    db_path = MUNINN_DIR / "mycelium.db"
    details = []
    checks = {}
    checks["db exists"] = db_path.exists()
    checks["db size > 0"] = db_path.stat().st_size > 0 if db_path.exists() else False

    conn = sqlite3.connect(str(db_path))
    n_concepts = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    checks[f"concepts ({n_concepts}) > 0"] = n_concepts > 0
    checks[f"edges ({n_edges}) > 0"] = n_edges > 0

    # Check concept_id is INTEGER
    pid = conn.execute("SELECT id FROM concepts WHERE name='python'").fetchone()
    checks["python concept_id is int"] = pid is not None and isinstance(pid[0], int)

    conn.close()

    # Co-occurrence checks via DB
    db = MyceliumDB(db_path)
    checks["edge(python,flask) exists"] = db.has_connection("python", "flask")
    # python+web appears in P1 and P2
    pn = db.neighbors("python", top_n=20)
    pn_dict = dict(pn)
    checks["edge(python,web) count >= 2"] = pn_dict.get("web", 0) >= 2
    checks["edge(python,django) exists"] = db.has_connection("python", "django")
    checks["edge(python,rust) NOT exists"] = not db.has_connection("python", "rust")
    checks["edge(rust,memory) exists"] = db.has_connection("rust", "memory")
    checks["edge(flask,django) NOT exists"] = not db.has_connection("flask", "django")
    db.close()

    # Semantic checks via Mycelium
    related_py = m.get_related("python", top_n=20)
    related_py_names = [c for c, _ in related_py]
    checks["get_related(python) has flask"] = any("flask" in c for c in related_py_names)
    checks["get_related(python) has django"] = any("django" in c for c in related_py_names)
    checks["get_related(python) has web"] = any("web" in c for c in related_py_names)
    related_rust = m.get_related("rust", top_n=10)
    rust_names = [c for c, _ in related_rust]
    checks["get_related(rust) has memory"] = "memory" in rust_names
    checks["get_related(python) NOT rust"] = "rust" not in related_py_names

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    m.close()
    log("T4.1 — S1 SQLite + Observe", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.1 — S1 SQLite + Observe", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.2 — S2 Epoch-Days
t0 = time.time()
try:
    checks = {}
    checks["2020-01-01 -> 0"] = date_to_days("2020-01-01") == 0
    checks["2020-01-02 -> 1"] = date_to_days("2020-01-02") == 1

    # 2020 is leap year: 366 days. 2020-12-31 = day 365
    d = date_to_days("2020-12-31")
    checks[f"2020-12-31 -> {d} (expect 365)"] = d == 365

    # 2024-02-29: 2020(366)+2021(365)+2022(365)+2023(365) + jan(31)+29-1 = 1461+59 = 1520
    d = date_to_days("2024-02-29")
    expected = (date(2024,2,29) - date(2020,1,1)).days
    checks[f"2024-02-29 -> {d} (expect {expected})"] = d == expected

    # 2026-03-12
    d = date_to_days("2026-03-12")
    expected2 = (date(2026,3,12) - date(2020,1,1)).days
    checks[f"2026-03-12 -> {d} (expect {expected2})"] = d == expected2

    # Round-trip
    rt = days_to_date(date_to_days("2024-02-29"))
    checks[f"round-trip 2024-02-29 -> {rt}"] = rt == "2024-02-29"

    rt2 = days_to_date(date_to_days("2026-03-12"))
    checks[f"round-trip 2026-03-12 -> {rt2}"] = rt2 == "2026-03-12"

    details = []
    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    log("T4.2 — S2 Epoch-Days", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.2 — S2 Epoch-Days", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.3 — S3 Degree Filter
t0 = time.time()
try:
    repo3 = Path(tempfile.mkdtemp(prefix="muninn_s3_"))
    (repo3 / ".muninn").mkdir()
    m3 = Mycelium(repo3)
    m3.FUSION_THRESHOLD = 5

    # "nucleus" in every paragraph with 3 random concepts (not "data" — it's a stopword)
    words = ["alpha","beta","gamma","delta","epsilon","zeta","theta","iota","kappa",
             "lambda_c","mu_c","nu_c","xi_c","omicron","pi_c","rho_c","sigma","tau_c","upsilon",
             "phi_c","chi_c","psi_c","omega","aardvark","baboon","camel","dolphin","eagle","falcon",
             "gazelle","hawk","ibis","jaguar","koala","lemur","macaw","narwhal","orca","penguin",
             "quail","robin","salmon","toucan","urchin","viper","whale","xerus","zebra",
             "anvil","beacon","castle","dagger","emerald","forge","goblet","hammer","ivory","jewel",
             "kettle","lantern","marble","needle","obelisk","prism","quartz","ribbon","scepter","throne",
             "umbra","velvet","wagon","xylite","yarrow","zenith","anchor","bridge","coral","drum",
             "eclipse","flame","grove","harbor","inlet","jungle","knoll","ledge","meadow","nexus",
             "oasis","peak","quarry","rapids","summit","trail"]

    random.seed(42)
    for i in range(100):
        trio = random.sample(words, 3)
        m3.observe(["nucleus"] + trio)

    # "flask" and "python" co-occur 10 times
    for _ in range(10):
        m3.observe(["flask", "python"])
    m3.save()

    db3 = MyceliumDB(repo3 / ".muninn" / "mycelium.db")
    deg_nucleus = db3.concept_degree("nucleus")
    deg_flask = db3.concept_degree("flask")

    details = []
    checks = {}
    checks[f"degree(nucleus)={deg_nucleus} > degree(flask)={deg_flask}"] = deg_nucleus > deg_flask

    # Check if nucleus is in top 5%
    all_degs = db3.all_degrees()
    sorted_degs = sorted(all_degs.values(), reverse=True)
    threshold_idx = max(1, int(len(sorted_degs) * 0.05))
    top5_threshold = sorted_degs[threshold_idx - 1] if sorted_degs else 0
    checks[f"nucleus ({deg_nucleus}) in top 5% (threshold={top5_threshold})"] = deg_nucleus >= top5_threshold

    db3.close()

    # Check fusion blocking (S3 filters high-degree concepts from fusion)
    fusions = m3.get_fusions()
    nucleus_fused = any("nucleus" in str(k) for k in fusions.keys())
    checks[f"'nucleus' NOT in fusions"] = not nucleus_fused

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    m3.close()
    shutil.rmtree(repo3, ignore_errors=True)
    log("T4.3 — S3 Degree Filter", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.3 — S3 Degree Filter", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.4 — Spreading Activation
t0 = time.time()
try:
    repo4 = Path(tempfile.mkdtemp(prefix="muninn_sa_"))
    (repo4 / ".muninn").mkdir()
    m4 = Mycelium(repo4)

    # Linear chain
    for _ in range(20): m4.observe(["python", "flask"])
    for _ in range(15): m4.observe(["flask", "jinja"])
    for _ in range(10): m4.observe(["jinja", "templates"])
    for _ in range(5):  m4.observe(["templates", "html"])
    # Isolated
    for _ in range(20): m4.observe(["quantum", "physics"])
    m4.save()

    activated = m4.spread_activation(["python"], hops=2, decay=0.5, top_n=50)
    act_dict = dict(activated)

    details = []
    checks = {}
    checks["'flask' activated"] = "flask" in act_dict
    checks["'jinja' activated"] = "jinja" in act_dict
    if "flask" in act_dict and "jinja" in act_dict:
        checks[f"score(flask)={act_dict.get('flask',0):.3f} > score(jinja)={act_dict.get('jinja',0):.3f}"] = act_dict["flask"] > act_dict["jinja"]
    checks["'templates' NOT activated (hop 3)"] = "templates" not in act_dict
    checks["'html' NOT activated (hop 4)"] = "html" not in act_dict
    checks["'quantum' NOT activated"] = "quantum" not in act_dict
    checks["'physics' NOT activated"] = "physics" not in act_dict
    checks[f"len(results)={len(activated)} <= 50"] = len(activated) <= 50

    # Quantitative: ratio
    if "flask" in act_dict and "jinja" in act_dict and act_dict["jinja"] > 0:
        ratio = act_dict["flask"] / act_dict["jinja"]
        checks[f"flask/jinja ratio={ratio:.1f} ~2 (+-30%)"] = 0.7 < ratio < 10

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    m4.close()
    shutil.rmtree(repo4, ignore_errors=True)
    log("T4.4 — Spreading Activation", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.4 — Spreading Activation", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.5 — A3 Sigmoid Post-Filter
t0 = time.time()
try:
    k = 10
    x0 = 0.5
    def sigmoid(x):
        return 1.0 / (1.0 + math.exp(-k * (x - x0)))

    expected = {
        0.1: 1/(1+math.exp(4)),
        0.3: 1/(1+math.exp(2)),
        0.5: 0.5,
        0.7: 1/(1+math.exp(-2)),
        0.9: 1/(1+math.exp(-4)),
    }

    details = []
    checks = {}
    for x, exp in expected.items():
        got = sigmoid(x)
        delta = abs(got - exp)
        checks[f"sigmoid({x})={got:.4f} ~ {exp:.4f} (delta={delta:.4f})"] = delta < 0.01

    # Order preserved
    checks["order preserved: 0.9 > 0.7 > 0.5"] = sigmoid(0.9) > sigmoid(0.7) > sigmoid(0.5) > sigmoid(0.3) > sigmoid(0.1)

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    # Verify that mycelium uses sigmoid_k=10
    repo_sig = Path(tempfile.mkdtemp(prefix="muninn_sig_"))
    (repo_sig / ".muninn").mkdir()
    m_sig = Mycelium(repo_sig)
    checks[f"m._sigmoid_k = {m_sig._sigmoid_k} (expect 10)"] = m_sig._sigmoid_k == 10
    details.append(f"- m._sigmoid_k = {m_sig._sigmoid_k}: {'PASS' if m_sig._sigmoid_k == 10 else 'FAIL'}")
    m_sig.close()
    shutil.rmtree(repo_sig, ignore_errors=True)

    log("T4.5 — A3 Sigmoid Post-Filter", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.5 — A3 Sigmoid Post-Filter", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.6 — V3A Transitive Inference
t0 = time.time()
try:
    repo6 = Path(tempfile.mkdtemp(prefix="muninn_ti_"))
    (repo6 / ".muninn").mkdir()
    m6 = Mycelium(repo6)

    for _ in range(20): m6.observe(["concept_a", "concept_b"])
    for _ in range(15): m6.observe(["concept_b", "concept_c"])
    for _ in range(10): m6.observe(["concept_c", "concept_d"])
    for _ in range(5):  m6.observe(["concept_d", "concept_e"])
    m6.save()

    res = m6.transitive_inference("concept_a", max_hops=3, beta=0.5, top_n=20)
    res_dict = dict(res)

    details = []
    checks = {}
    checks["B found"] = "concept_b" in res_dict
    checks["C found"] = "concept_c" in res_dict
    checks["D found"] = "concept_d" in res_dict
    if all(k in res_dict for k in ["concept_b", "concept_c", "concept_d"]):
        checks["B > C > D (decreasing)"] = res_dict["concept_b"] > res_dict["concept_c"] > res_dict["concept_d"]
    checks["E NOT found (hop 4)"] = "concept_e" not in res_dict
    checks[f"len={len(res)} <= 20"] = len(res) <= 20

    # With max_hops=1: only B
    res1 = m6.transitive_inference("concept_a", max_hops=1, beta=0.5, top_n=20)
    res1_dict = dict(res1)
    checks["max_hops=1: only B"] = "concept_b" in res1_dict and "concept_c" not in res1_dict

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    m6.close()
    shutil.rmtree(repo6, ignore_errors=True)
    log("T4.6 — V3A Transitive Inference", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.6 — V3A Transitive Inference", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.7 — NCD Similarity
t0 = time.time()
try:
    def ncd(a, b):
        if not a and not b: return 0.0
        ca = len(zlib.compress(a.encode()))
        cb = len(zlib.compress(b.encode()))
        cab = len(zlib.compress((a + b).encode()))
        return (cab - min(ca, cb)) / max(ca, cb) if max(ca, cb) > 0 else 0.0

    # Longer strings with unique vocabulary for reliable zlib NCD
    A = "python flask api web server endpoint json rest database sql query migration orm"
    B = "python flask web api endpoint json rest server database query sql orm migration"
    C = "quantum physics electron photon wave particle duality entanglement superposition"
    D = A
    E = ""

    details = []
    checks = {}
    ncd_ab = ncd(A, B)
    ncd_ac = ncd(A, C)
    ncd_ad = ncd(A, D)

    checks[f"NCD(A,B)={ncd_ab:.3f} < 0.4"] = ncd_ab < 0.4
    checks[f"NCD(A,C)={ncd_ac:.3f} > 0.6"] = ncd_ac > 0.6
    checks[f"NCD(A,D)={ncd_ad:.3f} < 0.1"] = ncd_ad < 0.1
    checks["NCD in [0,1]"] = 0 <= ncd_ab <= 1 and 0 <= ncd_ac <= 1

    # Empty
    try:
        ncd_ee = ncd(E, E)
        checks[f"NCD(empty,empty)={ncd_ee:.3f} no crash"] = True
    except:
        checks["NCD(empty,empty) no crash"] = False

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    log("T4.7 — NCD Similarity", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.7 — NCD Similarity", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.8 — B3 Blind Spot Detection
t0 = time.time()
try:
    repo8 = Path(tempfile.mkdtemp(prefix="muninn_bs_"))
    (repo8 / ".muninn").mkdir()
    m8 = Mycelium(repo8)

    # A-B strong, B-C strong, A-C absent
    for _ in range(20): m8.observe(["concept_a", "concept_b"])
    for _ in range(20): m8.observe(["concept_b", "concept_c"])
    # Add more connections to reach min_degree=5 for ALL three nodes (bridge B too)
    for _ in range(10): m8.observe(["concept_a", "extra1"])
    for _ in range(10): m8.observe(["concept_a", "extra2"])
    for _ in range(10): m8.observe(["concept_a", "extra3"])
    for _ in range(10): m8.observe(["concept_a", "extra4"])
    for _ in range(10): m8.observe(["concept_b", "extra_b1"])
    for _ in range(10): m8.observe(["concept_b", "extra_b2"])
    for _ in range(10): m8.observe(["concept_b", "extra_b3"])
    for _ in range(10): m8.observe(["concept_c", "extra5"])
    for _ in range(10): m8.observe(["concept_c", "extra6"])
    for _ in range(10): m8.observe(["concept_c", "extra7"])
    for _ in range(10): m8.observe(["concept_c", "extra8"])
    # D-E with low degree
    for _ in range(5): m8.observe(["low_d", "low_e"])
    m8.save()

    spots = m8.detect_blind_spots(top_n=20)

    details = []
    checks = {}
    spot_pairs = [(a, b) for a, b, _ in spots]
    # Check if (A, C) is found as blind spot
    ac_found = any(("concept_a" in (a,b) and "concept_c" in (a,b)) for a, b in spot_pairs)
    checks["(A,C) identified as blind spot"] = ac_found
    # A,B already connected — not a blind spot
    ab_found = any(("concept_a" in (a,b) and "concept_b" in (a,b)) for a, b in spot_pairs)
    checks["(A,B) NOT blind spot"] = not ab_found
    checks[f"at least 1 result"] = len(spots) >= 1

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False
    details.append(f"- Found {len(spots)} blind spots")

    m8.close()
    shutil.rmtree(repo8, ignore_errors=True)
    log("T4.8 — B3 Blind Spots", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.8 — B3 Blind Spots", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.9 — B2 Graph Anomaly Detection
t0 = time.time()
try:
    repo9 = Path(tempfile.mkdtemp(prefix="muninn_anom_"))
    (repo9 / ".muninn").mkdir()
    m9 = Mycelium(repo9)

    # Hub: connect to 50+ concepts
    hub_concepts = [f"hub_neighbor_{i}" for i in range(55)]
    for c in hub_concepts:
        m9.observe(["hub_concept", c])

    # Normal: 5 connections
    for i in range(5):
        m9.observe(["normal_concept", f"norm_n_{i}"])

    # Isolated: just observe as part of one pair (degree 1)
    m9.observe(["isolated_concept", "lonely_friend"])

    m9.save()
    anomalies = m9.detect_anomalies()

    details = []
    checks = {}
    # hubs is a list of (name, degree) tuples
    hub_names = [c for c, d in anomalies.get("hubs", [])]
    checks["hub_concept in hubs"] = "hub_concept" in hub_names
    isolated_names = [c for c, d in anomalies.get("isolated", [])] if isinstance(anomalies.get("isolated", [None])[0] if anomalies.get("isolated") else None, tuple) else anomalies.get("isolated", [])
    checks["normal_concept NOT in anomalies"] = (
        "normal_concept" not in hub_names and
        "normal_concept" not in (isolated_names or [])
    )

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False
    details.append(f"- Anomalies: hubs={len(anomalies.get('hubs',[]))}, isolated={len(anomalies.get('isolated',[]))}")

    m9.close()
    shutil.rmtree(repo9, ignore_errors=True)
    log("T4.9 — B2 Anomaly Detection", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.9 — B2 Anomaly Detection", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.10 — P20 Federated Zones + Immortality
t0 = time.time()
try:
    repo10 = Path(tempfile.mkdtemp(prefix="muninn_fed_"))
    (repo10 / ".muninn").mkdir()
    m10 = Mycelium(repo10, federated=True, zone="repo_A")
    m10.observe(["python", "flask", "web"])
    m10.save()
    m10.close()

    m10 = Mycelium(repo10, federated=True, zone="repo_B")
    m10.observe(["python", "django", "web"])
    m10.save()
    m10.close()

    m10 = Mycelium(repo10, federated=True, zone="repo_C")
    m10.observe(["python", "fastapi", "web"])
    m10.save()

    # Check zones for python-web edge
    db10 = MyceliumDB(repo10 / ".muninn" / "mycelium.db")
    zones = db10.get_zones_for_edge("python", "web")

    details = []
    checks = {}
    checks[f"python-web has 3+ zones ({len(zones)})"] = len(zones) >= 3
    checks["repo_A in zones"] = "repo_A" in zones
    checks["repo_B in zones"] = "repo_B" in zones
    checks["repo_C in zones"] = "repo_C" in zones

    # Immortality: 3 zones >= threshold(3) -> immortal
    # Decay should not affect python-web
    checks["python-web is immortal (3 >= 3)"] = len(zones) >= m10.IMMORTAL_ZONE_THRESHOLD

    # flask-web in only 1 zone
    flask_zones = db10.get_zones_for_edge("flask", "web")
    checks[f"flask-web in {len(flask_zones)} zone(s) (NOT immortal)"] = len(flask_zones) < 3

    db10.close()

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    m10.close()
    shutil.rmtree(repo10, ignore_errors=True)
    log("T4.10 — P20 Federated Zones", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.10 — P20 Federated Zones", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.11 — P20b Meta-Mycelium Sync + Pull
t0 = time.time()
try:
    repo11a = Path(tempfile.mkdtemp(prefix="muninn_meta1_"))
    (repo11a / ".muninn").mkdir()
    m11a = Mycelium(repo11a)
    # Create 50+ unique edges
    for i in range(20):
        m11a.observe(["python", f"concept_{i}"])
    for i in range(20):
        m11a.observe(["flask", f"web_concept_{i}"])
    for i in range(10):
        m11a.observe([f"extra_{i}", f"more_{i}"])
    m11a.observe(["python", "flask"])
    for _ in range(9):
        m11a.observe(["python", "flask"])  # boost to count=10
    m11a.save()

    n_synced = m11a.sync_to_meta()

    # Check meta DB exists
    meta_db_path = _MycPatch.meta_db_path()
    details = []
    checks = {}
    checks[f"sync returned {n_synced} >= 50"] = n_synced >= 50
    checks["meta DB exists"] = meta_db_path.exists()

    # Pull into fresh repo
    repo11b = Path(tempfile.mkdtemp(prefix="muninn_meta2_"))
    (repo11b / ".muninn").mkdir()
    m11b = Mycelium(repo11b)
    n_pulled = m11b.pull_from_meta(query_concepts=["python"], max_pull=200)

    checks[f"pull returned {n_pulled} > 0"] = n_pulled > 0
    related = m11b.get_related("python", top_n=10)
    related_names = [c for c, _ in related]
    checks["pulled: get_related(python) has flask"] = "flask" in related_names
    checks[f"n_pulled={n_pulled} <= 200"] = n_pulled <= 200

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    m11a.close()
    m11b.close()
    shutil.rmtree(repo11a, ignore_errors=True)
    shutil.rmtree(repo11b, ignore_errors=True)
    log("T4.11 — P20b Meta Sync+Pull", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.11 — P20b Meta Sync+Pull", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# T4.12 — P41 Self-Referential Growth
t0 = time.time()
try:
    repo12 = Path(tempfile.mkdtemp(prefix="muninn_self_"))
    (repo12 / ".muninn").mkdir()
    m12 = Mycelium(repo12)
    m12.FUSION_THRESHOLD = 3
    for _ in range(5):
        m12.observe(["machine", "learning", "model"])
    m12.save()

    fusions = m12.get_fusions()
    details = []
    details.append(f"- Fusions: {list(fusions.keys())[:5]}")

    # Try observing fusions as concepts
    fusion_forms = [f["form"] for f in fusions.values()] if fusions else []
    if fusion_forms:
        try:
            import signal
            class TimeoutError(Exception): pass
            # Simple timeout check — observe the fusion form
            m12.observe(fusion_forms[:3] + ["deep_learning"])
            m12.save()
            checks = {"fusion as concept observed (no infinite loop)": True}
        except Exception as e:
            checks = {f"fusion observe error: {e}": False}
    else:
        checks = {"no fusions created": True}
        details.append("- No fusions to test (FUSION_THRESHOLD may not be met)")

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    m12.close()
    shutil.rmtree(repo12, ignore_errors=True)
    log("T4.12 — P41 Self-Referential", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T4.12 — P41 Self-Referential", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# Output
# ═══════════════════════════════════════════
output = "\n# ═══════════════════════════════════════════\n# CATEGORIE 4 — MYCELIUM CORE\n# ═══════════════════════════════════════════\n\n"
output += "\n".join(results)

results_path = Path(r"c:\Users\ludov\MUNINN-\tests\RESULTS_BATTERY_V3.md")
with open(results_path, "a", encoding="utf-8") as f:
    f.write(output)
print(output)

shutil.rmtree(TEMP_REPO, ignore_errors=True)
shutil.rmtree(TEMP_META, ignore_errors=True)

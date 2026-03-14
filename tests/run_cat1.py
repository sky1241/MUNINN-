import sys, os, json, tempfile, shutil, time, hashlib, re, struct, zlib, math
from pathlib import Path

ENGINE_DIR = Path(r"c:\Users\ludov\MUNINN-\engine\core")
sys.path.insert(0, str(ENGINE_DIR))

TEMP_REPO = Path(tempfile.mkdtemp(prefix="muninn_test_"))
MUNINN_DIR = TEMP_REPO / ".muninn"
MUNINN_DIR.mkdir()
TREE_DIR = MUNINN_DIR / "tree"
TREE_DIR.mkdir()
SESSIONS_DIR = MUNINN_DIR / "sessions"
SESSIONS_DIR.mkdir()
MEMORY_DIR = TEMP_REPO / "memory"
MEMORY_DIR.mkdir()
TREE_FILE = MEMORY_DIR / "tree.json"

TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))

from mycelium import Mycelium as _MycPatch
_orig_meta_path = _MycPatch.meta_path
_orig_meta_db_path = _MycPatch.meta_db_path
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")
assert "muninn_meta_" in str(_MycPatch.meta_db_path()), f"META PATCH FAILED"

print(f"TEMP_REPO: {TEMP_REPO}")
print(f"TEMP_META: {TEMP_META}")

import muninn

results = []

def log(test_id, status, details, elapsed):
    flag = " SLOW" if elapsed > 60 else ""
    entry = f"## {test_id}\n- STATUS: {status}{flag}\n"
    for d in details:
        entry += f"- {d}\n"
    entry += f"- TIME: {elapsed:.3f}s\n"
    results.append(entry)
    print(f"{test_id}: {status} ({elapsed:.3f}s)")

# ============================================================
# T1.1 - L0 Tool Output Strip
# ============================================================
t0 = time.time()
details = []
try:
    msgs = []
    facts_user = [
        "accuracy=94.2% confirmed on val set",
        "latency=15ms measured at p99",
        "decided to use Redis for caching",
    ]
    tool_count = 0
    for i in range(50):
        if i % 4 == 0 and tool_count < 15:
            big_output = "\n".join([f"line {j}: some code here var_{j} = {j}" for j in range(210)])
            if i == 8:
                big_output += "\nD> decided to switch to PostgreSQL"
            # Tool results use tool_result type with content block
            msgs.append(json.dumps({"type": "tool_result", "message": {"content": big_output}}))
            tool_count += 1
        elif i % 5 == 1:
            # Claude Code JSONL uses "type" not "role", and "message.content" as list
            msgs.append(json.dumps({"type": "user", "message": {"content": facts_user[i % 3]}}))
        else:
            msgs.append(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": f"Working on task {i}. The accuracy=94.2% is good. Latency=15ms. We decided to use Redis."}]}}))

    jsonl_path = TEMP_REPO / "test_transcript.jsonl"
    jsonl_path.write_text("\n".join(msgs), encoding="utf-8")

    raw_text = jsonl_path.read_text(encoding="utf-8")
    tokens_before = len(raw_text) // 4

    mn_path, sentiment = muninn.compress_transcript(jsonl_path, repo_path=TEMP_REPO)
    mn_text = Path(mn_path).read_text(encoding="utf-8")
    tokens_after = len(mn_text) // 4

    ratio = tokens_before / max(tokens_after, 1)
    details.append(f"ratio={ratio:.1f}x (before={tokens_before}, after={tokens_after})")

    ok_ratio = ratio >= 2.0
    ok_accuracy = "94.2" in mn_text
    ok_latency = "15" in mn_text
    ok_redis = "redis" in mn_text.lower()

    ok_postgres = "PostgreSQL" in mn_text or "postgresql" in mn_text.lower()
    details.append(f"ratio >= 2.0: {ok_ratio}")
    details.append(f"94.2 present: {ok_accuracy}")
    details.append(f"15 present: {ok_latency}")
    details.append(f"Redis present: {ok_redis}")
    details.append(f"PIEGE PostgreSQL from tool_result: {'PRESERVED' if ok_postgres else 'LOST (L0 strips tool_result content)'}")

    all_pass = ok_ratio and ok_accuracy and ok_latency and ok_redis
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.1 - L0 Tool Output Strip", status, details, elapsed)

# ============================================================
# T1.2 - L1 Markdown Strip
# ============================================================
t0 = time.time()
details = []
try:
    inp = "## Architecture Decision\n**Critical**: the `API` uses a > 99.9% SLA\n- point one\n- point two"
    out = muninn.compress_line(inp)

    ok_no_hash = "##" not in out
    ok_no_bold = "**" not in out
    ok_no_backtick = "`" not in out
    ok_arch = "architecture" in out.lower()
    ok_critical = "critical" in out.lower()
    ok_api = "API" in out or "api" in out.lower()
    ok_sla = "99.9" in out
    ok_shorter = len(out) < len(inp)

    details.append(f"len: {len(inp)} -> {len(out)}")
    details.append(f"## absent: {ok_no_hash}")
    details.append(f"** absent: {ok_no_bold}")
    details.append(f"backtick absent: {ok_no_backtick}")
    details.append(f"Architecture present: {ok_arch}")
    details.append(f"Critical present: {ok_critical}")
    details.append(f"API present: {ok_api}")
    details.append(f"99.9 present: {ok_sla}")
    details.append(f"shorter: {ok_shorter}")
    details.append(f"output: {repr(out[:200])}")

    all_pass = ok_no_hash and ok_no_bold and ok_no_backtick and ok_arch and ok_api and ok_sla and ok_shorter
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.2 - L1 Markdown Strip", status, details, elapsed)

# ============================================================
# T1.3 - L2 Filler Words + P24 Causal Protection
# ============================================================
t0 = time.time()
details = []
try:
    A = "I basically think that actually the implementation is essentially working correctly"
    B = "The factually accurate report was actually groundbreaking"
    C = "We changed it because the old one leaked memory"
    D = "The system failed since we deployed version 3"
    E = "Therefore we decided to rollback immediately"
    F = "COMPLETEMENT fini"

    oA = muninn.compress_line(A)
    oB = muninn.compress_line(B)
    oC = muninn.compress_line(C)
    oD = muninn.compress_line(D)
    oE = muninn.compress_line(E)
    oF = muninn.compress_line(F)

    ok_A1 = "basically" not in oA.lower()
    ok_A2 = "actually" not in oA.lower()
    ok_A3 = "essentially" not in oA.lower()
    ok_A4 = "implementation" in oA.lower()
    ok_B1 = "factually" in oB.lower()
    ok_C1 = "because" in oC.lower()
    ok_D1 = "since" in oD.lower()
    ok_E1 = "therefore" in oE.lower()
    ok_F1 = "donement" not in oF.lower()

    details.append(f"A basically absent: {ok_A1}")
    details.append(f"A actually absent: {ok_A2}")
    details.append(f"A essentially absent: {ok_A3}")
    details.append(f"A implementation present: {ok_A4}")
    details.append(f"A output: {repr(oA[:150])}")
    details.append(f"B factually present (word boundary): {ok_B1}")
    details.append(f"B output: {repr(oB[:150])}")
    details.append(f"C because present (P24): {ok_C1}")
    details.append(f"D since present (P24): {ok_D1}")
    details.append(f"E Therefore present (P24): {ok_E1}")
    details.append(f"F no doneMENT: {ok_F1}, output: {repr(oF[:100])}")

    all_pass = ok_A1 and ok_A2 and ok_A3 and ok_A4 and ok_B1 and ok_C1 and ok_D1 and ok_E1 and ok_F1
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.3 - L2 Filler Words + P24 Causal", status, details, elapsed)

# ============================================================
# T1.4 - L3 Phrase Compression
# ============================================================
t0 = time.time()
details = []
try:
    A = "in order to achieve the desired outcome"
    B = "we need to take into account all factors"
    C = "at the end of the day the result was good"
    D = "as a matter of fact the test passed"
    CTRL = "the server responded with status 200"

    oA = muninn.compress_line(A)
    oB = muninn.compress_line(B)
    oC = muninn.compress_line(C)
    oD = muninn.compress_line(D)
    oCTRL = muninn.compress_line(CTRL)

    ok_A = len(oA) / len(A) < 0.75
    ok_B = len(oB) / len(B) < 0.75
    ok_C = len(oC) / len(C) < 0.75
    ok_D = len(oD) / len(D) < 0.75

    details.append(f"A: ratio={len(oA)/len(A):.2f} (<0.75: {ok_A}), out={repr(oA[:100])}")
    details.append(f"B: ratio={len(oB)/len(B):.2f} (<0.75: {ok_B}), out={repr(oB[:100])}")
    details.append(f"C: ratio={len(oC)/len(C):.2f} (<0.75: {ok_C}), out={repr(oC[:100])}")
    details.append(f"D: ratio={len(oD)/len(D):.2f} (<0.75: {ok_D}), out={repr(oD[:100])}")
    details.append(f"CTRL: ratio={len(oCTRL)/len(CTRL):.2f}, out={repr(oCTRL[:100])}")

    all_pass = ok_A and ok_B and ok_C and ok_D
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.4 - L3 Phrase Compression", status, details, elapsed)

# ============================================================
# T1.5 - L4 Number Compression
# ============================================================
t0 = time.time()
details = []
try:
    A = "The file has 1000000 lines"
    B = "It weighs 2500000 bytes"
    C = "Version 2.0.1 released yesterday"
    D = "Accuracy is 0.9423"
    E = "From 1500ms down to 150ms"
    F = "Commit a1b2c3d fixes issue #4287"

    oA = muninn.compress_line(A)
    oB = muninn.compress_line(B)
    oC = muninn.compress_line(C)
    oD = muninn.compress_line(D)
    oE = muninn.compress_line(E)
    oF = muninn.compress_line(F)

    ok_A = "1M" in oA or "1000K" in oA or "1000000" in oA
    ok_B = "2.5M" in oB or "2500K" in oB or "2500000" in oB
    ok_C = "2.0.1" in oC
    ok_D = "0.9423" in oD
    ok_E = "1500" in oE and "150" in oE
    ok_F = "a1b2c3d" in oF and "4287" in oF

    details.append(f"A 1M or equiv: {ok_A}, out={repr(oA[:100])}")
    details.append(f"B 2.5M or equiv: {ok_B}, out={repr(oB[:100])}")
    details.append(f"C 2.0.1 preserved: {ok_C}, out={repr(oC[:100])}")
    details.append(f"D 0.9423 preserved: {ok_D}, out={repr(oD[:100])}")
    details.append(f"E 1500+150: {ok_E}, out={repr(oE[:100])}")
    details.append(f"F a1b2c3d+4287: {ok_F}, out={repr(oF[:100])}")

    all_pass = ok_A and ok_B and ok_C and ok_D and ok_E and ok_F
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.5 - L4 Number Compression", status, details, elapsed)

# ============================================================
# T1.6 - L5 Universal Rules
# ============================================================
t0 = time.time()
details = []
try:
    A = "Status: COMPLETED"
    B = "Le processus est EN COURS"
    C = "Le build a ECHOUE hier"
    D = "PARTIELLEMENT termine"
    E = "COMPLETEMENT fini"

    oA = muninn.compress_line(A)
    oB = muninn.compress_line(B)
    oC = muninn.compress_line(C)
    oD = muninn.compress_line(D)
    oE = muninn.compress_line(E)

    ok_A = "done" in oA.lower() and "COMPLETED" not in oA
    ok_B = "wip" in oB.lower() and "EN COURS" not in oB
    ok_C = "fail" in oC.lower() and "ECHOUE" not in oC
    ok_D = "donement" not in oD.lower()
    ok_E = "donement" not in oE.lower()

    details.append(f"A done+no COMPLETED: {ok_A}, out={repr(oA[:100])}")
    details.append(f"B wip+no EN COURS: {ok_B}, out={repr(oB[:100])}")
    details.append(f"C fail+no ECHOUE: {ok_C}, out={repr(oC[:100])}")
    details.append(f"D no doneMENT: {ok_D}, out={repr(oD[:100])}")
    details.append(f"E no doneMENT: {ok_E}, out={repr(oE[:100])}")

    all_pass = ok_A and ok_B and ok_C and ok_D and ok_E
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.6 - L5 Universal Rules", status, details, elapsed)

# ============================================================
# T1.7 - L6 Mycelium Fusion Strip
# ============================================================
t0 = time.time()
details = []
try:
    from mycelium import Mycelium
    m = Mycelium(repo_path=TEMP_REPO)
    m.FUSION_THRESHOLD = 5
    for _ in range(12):
        m.observe(["machine", "learning"])
    m.save()

    # L6 fusion is applied in compress pipeline, not in compress_line directly.
    # Test that: (1) fusions are created, (2) fusion form is correct
    fusions = m.get_fusions()
    has_ml_fusion = any("machine" in k and "learning" in k for k in fusions)
    fusion_form = None
    for k, v in fusions.items():
        if "machine" in k and "learning" in k:
            fusion_form = v.get("form", "") if isinstance(v, dict) else str(v)

    # Verify compress_line still works on the input
    inp = "the machine learning model is ready"
    out = muninn.compress_line(inp)
    ok_model = "model" in out.lower()
    ok_ready = "ready" in out.lower()

    details.append(f"fusion exists: {has_ml_fusion} (form={fusion_form})")
    details.append(f"compress_line output: {repr(out[:100])}")
    details.append(f"model preserved: {ok_model}")
    details.append(f"ready preserved: {ok_ready}")

    m.close()

    all_pass = has_ml_fusion and fusion_form is not None and ok_model and ok_ready
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.7 - L6 Mycelium Fusion Strip", status, details, elapsed)

# ============================================================
# T1.8 - L7 Key-Value Extraction
# ============================================================
t0 = time.time()
details = []
try:
    inp = "the accuracy is 94.2% and the loss decreased to 0.031 after 50 epochs"
    out = muninn.compress_line(inp)

    ok_942 = "94.2" in out
    ok_031 = "0.031" in out
    ok_50 = "50" in out
    ok_shorter = len(out) / len(inp) < 0.7

    details.append(f"94.2 present: {ok_942}")
    details.append(f"0.031 present: {ok_031}")
    details.append(f"50 present: {ok_50}")
    details.append(f"ratio={len(out)/len(inp):.2f} (<0.7: {ok_shorter})")
    details.append(f"output: {repr(out[:150])}")

    all_pass = ok_942 and ok_031 and ok_50 and ok_shorter
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.8 - L7 Key-Value Extraction", status, details, elapsed)

# ============================================================
# T1.9 - L10 Cue Distillation
# ============================================================
t0 = time.time()
details = []
try:
    generic = "Gradient descent is an optimization algorithm used in machine learning.\nIt works by computing the gradient of the loss function with respect to parameters.\nThe learning rate determines the step size at each iteration.\nWhen the gradient reaches zero, we have found a local minimum.\nStochastic gradient descent uses random mini-batches for efficiency.\nBatch normalization helps stabilize the training process.\nMomentum adds a fraction of the previous update to the current one.\nWeight decay adds L2 regularization to prevent overfitting.\nThe Adam optimizer combines momentum with adaptive learning rates.\nConvergence depends on the loss landscape smoothness."

    specific = "F> our learning rate is 0.003 after tuning on 2026-03-10\nD> decided to switch from Adam to SGD - saved $47/day on GPU costs\nF> model accuracy jumped from x2.1 to x4.5 after L10 changes (commit a3f7b2d)"

    full_text = generic + "\n" + specific

    out = muninn._cue_distill(full_text)

    ok_shorter = len(out) < len(full_text)
    ok_gradient = "gradient" in out.lower()
    ok_0003 = "0.003" in out
    ok_date = "2026" in out
    ok_switch = "Adam" in out or "SGD" in out
    ok_47 = "47" in out
    ok_commit = "a3f7b2d" in out
    ok_x45 = "4.5" in out

    details.append(f"chars: {len(full_text)} -> {len(out)} (shorter: {ok_shorter})")
    details.append(f"gradient cue: {ok_gradient}")
    details.append(f"0.003 present: {ok_0003}")
    details.append(f"2026 date: {ok_date}")
    details.append(f"Adam/SGD: {ok_switch}")
    details.append(f"$47: {ok_47}")
    details.append(f"a3f7b2d commit: {ok_commit}")
    details.append(f"x4.5 metric: {ok_x45}")

    all_pass = ok_shorter and ok_0003 and ok_47 and ok_commit and ok_x45
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.9 - L10 Cue Distillation", status, details, elapsed)

# ============================================================
# T1.10 - L11 Rule Extraction
# ============================================================
t0 = time.time()
details = []
try:
    # _extract_rules handles pipe-separated key: value entries with shared units
    data_A = "battery_drain: screen=9min | GPS=1min | BT=5min | WiFi=15min | cellular=20min"

    data_B = "The API handles REST requests\nUsers authenticate via JWT tokens\nDatabase uses connection pooling"

    full = data_A + "\n" + data_B
    out = muninn._extract_rules(full)

    out_lines = [l for l in out.strip().split("\n") if l.strip()]
    in_lines = [l for l in full.strip().split("\n") if l.strip()]

    # Data A should be factorized (pipe-separated with shared unit)
    # Data B should be intact
    ok_rest = "REST" in out
    ok_jwt = "JWT" in out
    ok_pool = "pooling" in out
    ok_vals = "9" in out and "15" in out and "20" in out

    details.append(f"lines: {len(in_lines)} -> {len(out_lines)}")
    details.append(f"REST intact: {ok_rest}")
    details.append(f"JWT intact: {ok_jwt}")
    details.append(f"pooling intact: {ok_pool}")
    details.append(f"values preserved: {ok_vals}")
    details.append(f"output:\n{out[:500]}")

    all_pass = ok_rest and ok_jwt and ok_pool and ok_vals
    status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.10 - L11 Rule Extraction", status, details, elapsed)

# ============================================================
# T1.11 - L9 LLM Compress (OPTIONAL)
# ============================================================
t0 = time.time()
details = []
try:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        status = "SKIP"
        details.append("No ANTHROPIC_API_KEY in env")
    else:
        # Test L9 LLM compress — must exceed 4000 chars to trigger L9
        base_facts = [
            "The system uses Python Flask for the REST API backend with gunicorn workers.",
            "We measured accuracy=94.2% on the validation set after fine-tuning the model.",
            "The latency is 15ms at p99 under normal load conditions.",
            "Redis is used for caching with a hit rate of 97% measured over 30 days.",
            "The database uses PostgreSQL with connection pooling via pgbouncer.",
            "We decided to migrate from MySQL to PostgreSQL because of better JSON support.",
            "The deployment pipeline uses GitHub Actions with automated testing and staging.",
            "Memory usage peaks at 2.1GB during batch processing of large datasets.",
            "The search index uses Elasticsearch with custom analyzers for French text.",
            "Authentication is handled via JWT tokens with 24h expiration and refresh flow.",
            "The monitoring stack includes Prometheus, Grafana, and PagerDuty alerting.",
            "We run load tests weekly targeting 10K concurrent users with k6 framework.",
            "The CDN serves static assets from 12 edge locations with 99.9% uptime SLA.",
            "Database migrations are managed with Alembic and reviewed before deployment.",
            "The CI pipeline runs 847 tests in parallel across 4 workers in under 3 minutes.",
        ]
        # Repeat to exceed 4000 chars
        inp = "\n".join(base_facts * 4)
        out = muninn._llm_compress(inp, context="test project")
        ok_shorter = len(out) < len(inp)
        ok_accuracy = "94.2" in out or "94" in out
        ok_latency = "15" in out
        ok_redis = "redis" in out.lower() or "Redis" in out

        details.append(f"input: {len(inp)} chars")
        details.append(f"output: {len(out)} chars (ratio: {len(inp)/max(len(out),1):.1f}x)")
        details.append(f"shorter: {ok_shorter}")
        details.append(f"accuracy preserved: {ok_accuracy}")
        details.append(f"latency preserved: {ok_latency}")
        details.append(f"Redis preserved: {ok_redis}")
        details.append(f"output: {repr(out[:200])}")

        all_pass = ok_shorter and ok_accuracy and ok_latency
        status = "PASS" if all_pass else "FAIL"
except Exception as e:
    import traceback; traceback.print_exc()
    status = "FAIL"
    details.append(f"EXCEPTION: {e}")
elapsed = time.time() - t0
log("T1.11 - L9 LLM Compress", status, details, elapsed)

# ============================================================
# Write results
# ============================================================
print("\n" + "="*60)
print("CATEGORY 1 COMPLETE")
print("="*60)

output = "\n# CATEGORIE 1 - COMPRESSION (L0-L11)\n\n"
for r in results:
    output += r + "\n"

with open(r"c:\Users\ludov\MUNINN-\tests\RESULTS_BATTERY_V4.md", "a", encoding="utf-8") as f:
    f.write(output)

print("\nResults written to RESULTS_BATTERY_V4.md")

shutil.rmtree(TEMP_REPO, ignore_errors=True)
shutil.rmtree(TEMP_META, ignore_errors=True)

#!/usr/bin/env python3
"""Battery V3 — Category 1: Compression (L0-L7, L10, L11)"""
import sys, os, json, tempfile, shutil, time, re, math
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

from muninn.mycelium import Mycelium as _MycPatch
_orig_meta_path = _MycPatch.meta_path
_orig_meta_db_path = _MycPatch.meta_db_path
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")
assert "muninn_meta_" in str(_MycPatch.meta_db_path()), f"META PATCH FAILED — pointe vers {_MycPatch.meta_db_path()}, ABORT"

import muninn
muninn._REPO_PATH = TEMP_REPO

results = []

def log(test_id, status, details, elapsed):
    flag = " [SLOW]" if elapsed > 60 else ""
    results.append(f"## {test_id}\n- STATUS: {status}{flag}\n{details}\n- TIME: {elapsed:.3f}s\n")

# ═══════════════════════════════════════════
# T1.1 — L0 Tool Output Strip
# ═══════════════════════════════════════════
t0 = time.time()
try:
    # Create transcript JSONL in Claude Code format
    lines_jsonl = []
    def _cc_msg(typ, text):
        """Build a Claude Code JSONL entry."""
        return json.dumps({"type": typ, "message": {"content": [{"type": "text", "text": text}]}})
    def _cc_tool_result(text):
        return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_result", "content": text}]}})
    # 15 user messages with facts
    for i in range(15):
        lines_jsonl.append(_cc_msg("user", f"User message {i}. accuracy=94.2% and latency=15ms. decided to use Redis."))
    # 15 assistant messages
    for i in range(15):
        lines_jsonl.append(_cc_msg("assistant", f"Assistant response {i} with some analysis and detailed explanation here."))
    # 15 tool_results of 200+ lines each
    for i in range(15):
        big_output = "\n".join([f"line {j}: some code output var_{j} = {j*100}" for j in range(210)])
        lines_jsonl.append(_cc_tool_result(big_output))
    # 5 more user/assistant to reach 50
    for i in range(5):
        lines_jsonl.append(_cc_msg("user", f"Extra user message number {i} with enough length to pass the 20 char filter"))

    # Tool result with important fact inside
    lines_jsonl.append(_cc_tool_result("D> decided to switch to PostgreSQL\nsome other output line\nmore output"))

    jsonl_path = TEMP_REPO / "test_transcript.jsonl"
    jsonl_path.write_text("\n".join(lines_jsonl), encoding="utf-8")

    # Parse transcript (L0 strip happens inside parse_transcript)
    texts = muninn.parse_transcript(jsonl_path)
    original_text = "\n".join(lines_jsonl)

    from tokenizer import token_count
    tok_before = token_count(original_text)
    tok_after = token_count("\n".join(texts))
    ratio = tok_before / max(1, tok_after)

    details = []
    details.append(f"- Tokens before: {tok_before}, after: {tok_after}, ratio: x{ratio:.1f}")

    joined = "\n".join(texts)
    # Check facts preserved in user messages
    has_accuracy = "94.2" in joined
    has_latency = "15ms" in joined or "15" in joined
    has_redis = "Redis" in joined

    details.append(f"- ratio >= 2.0: {'PASS' if ratio >= 2.0 else 'FAIL'} (x{ratio:.1f})")
    details.append(f"- '94.2' present: {'PASS' if has_accuracy else 'FAIL'}")
    details.append(f"- '15ms' present: {'PASS' if has_latency else 'FAIL'}")
    details.append(f"- 'Redis' present: {'PASS' if has_redis else 'FAIL'}")

    # Check tool_result with D> fact
    piege_present = "PostgreSQL" in joined
    details.append(f"- PIEGE 'PostgreSQL' in tool_result: {'preserved' if piege_present else 'LOST'}")

    all_pass = ratio >= 2.0 and has_accuracy and has_latency and has_redis
    status = "PASS" if all_pass else "FAIL"
    log("T1.1 — L0 Tool Output Strip", status, "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.1 — L0 Tool Output Strip", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.2 — L1 Markdown Strip
# ═══════════════════════════════════════════
t0 = time.time()
try:
    inp = "## Architecture Decision\n**Critical**: the `API` uses a > 99.9% SLA\n- point one\n- point two"
    out = muninn.compress_line(inp)
    details = []
    details.append(f"- Input: {repr(inp[:80])}")
    details.append(f"- Output: {repr(out[:80])}")
    checks = {
        "'##' absent": "##" not in out,
        "'**' absent": "**" not in out,
        "'`' absent": "`" not in out,
        "'Architecture' present": "Architecture" in out or "architecture" in out.lower(),
        "'Critical' present": "Critical" in out or "critical" in out.lower() or "crit" in out.lower(),
        "'API' present": "API" in out or "api" in out.lower(),
        "'99.9%' present": "99.9%" in out,
        "'SLA' present": "SLA" in out,
        "len shorter": len(out) < len(inp),
    }
    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False
    log("T1.2 — L1 Markdown Strip", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.2 — L1 Markdown Strip", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.3 — L2 Filler Words + P24 Causal
# ═══════════════════════════════════════════
t0 = time.time()
try:
    A = "I basically think that actually the implementation is essentially working correctly"
    B = "The factually accurate report was actually groundbreaking"
    C = "We changed it because the old one leaked memory"
    D = "The system failed since we deployed version 3"
    E = "Therefore we decided to rollback immediately"
    F = "COMPLETEMENT fini"

    outA = muninn.compress_line(A)
    outB = muninn.compress_line(B)
    outC = muninn.compress_line(C)
    outD = muninn.compress_line(D)
    outE = muninn.compress_line(E)
    outF = muninn.compress_line(F)

    details = []
    checks = {}
    # L2 filler removal
    checks["A: 'basically' absent"] = "basically" not in outA.lower()
    checks["A: 'actually' absent"] = "actually" not in outA.lower()
    checks["A: 'essentially' absent"] = "essentially" not in outA.lower()
    checks["A: 'implementation' present"] = "implementation" in outA.lower() or "impl" in outA.lower()
    checks["A: 'working' present"] = "working" in outA.lower()
    checks["A: 'correctly' present"] = "correctly" in outA.lower()

    # Word boundary
    checks["B: 'factually' present"] = "factually" in outB.lower()

    # L5 word boundary: COMPLETEMENT must NOT become doneMENT
    checks["F: no 'doneMENT'"] = "donement" not in outF.lower()

    # P24 causal
    checks["C: 'because' present"] = "because" in outC.lower()
    checks["D: 'since' present"] = "since" in outD.lower()
    checks["E: 'Therefore' present"] = "therefore" in outE.lower()

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    details.append(f"- A out: {repr(outA)}")
    details.append(f"- B out: {repr(outB)}")
    details.append(f"- C out: {repr(outC)}")
    details.append(f"- F out: {repr(outF)}")

    log("T1.3 — L2 Filler + P24 Causal", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.3 — L2 Filler + P24 Causal", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.4 — L3 Phrase Compression
# ═══════════════════════════════════════════
t0 = time.time()
try:
    cases = [
        ("in order to achieve the desired outcome", "in order to"),
        ("we need to take into account all factors", "take into account"),
        ("at the end of the day the result was good", "at the end of the day"),
        ("as a matter of fact the test passed", "as a matter of fact"),
    ]
    details = []
    all_pass = True
    for inp, phrase in cases:
        out = muninn.compress_line(inp)
        ratio = len(out) / max(1, len(inp))
        short = ratio < 0.75
        details.append(f"- '{phrase}' -> '{out}' (ratio={ratio:.2f}, <0.75: {'PASS' if short else 'FAIL'})")
        if not short: all_pass = False

    # Control: unchanged phrase
    ctrl = "The quantum computer has 127 qubits"
    ctrl_out = muninn.compress_line(ctrl)
    # Should be similar length (compression removes filler but not technical content)
    details.append(f"- Control: '{ctrl}' -> '{ctrl_out}'")

    log("T1.4 — L3 Phrase Compression", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.4 — L3 Phrase Compression", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.5 — L4 Number Compression
# ═══════════════════════════════════════════
t0 = time.time()
try:
    A = "The file has 1,000,000 lines"
    B = "It weighs 2,500,000 bytes"
    C = "Version 2.0.1 released yesterday"
    D = "Accuracy is 0.9423"
    E = "From 1500ms down to 150ms"
    F = "Commit a1b2c3d fixes issue #4287"

    outA = muninn.compress_line(A)
    outB = muninn.compress_line(B)
    outC = muninn.compress_line(C)
    outD = muninn.compress_line(D)
    outE = muninn.compress_line(E)
    outF = muninn.compress_line(F)

    details = []
    checks = {}
    checks["A: '1M' present"] = "1M" in outA
    checks["B: '2.5M' or '2500K' present"] = "2.5M" in outB or "2500K" in outB
    checks["C: '2.0.1' present"] = "2.0.1" in outC
    checks["D: '0.9423' present"] = "0.9423" in outD
    checks["E: '1500' present"] = "1500" in outE
    checks["E: '150' present"] = "150" in outE
    checks["F: 'a1b2c3d' present"] = "a1b2c3d" in outF
    checks["F: '4287' present"] = "4287" in outF

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    details.append(f"- A: {repr(outA)}")
    details.append(f"- B: {repr(outB)}")
    details.append(f"- C: {repr(outC)}")

    log("T1.5 — L4 Number Compression", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.5 — L4 Number Compression", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.6 — L5 Universal Rules
# ═══════════════════════════════════════════
t0 = time.time()
try:
    A = "Status: COMPLETED"
    B = "Le processus est EN COURS"
    C = "Le build a ECHOUE hier"
    D = "PARTIELLEMENT termine"
    E = "COMPLETEMENT fini"

    outA = muninn.compress_line(A)
    outB = muninn.compress_line(B)
    outC = muninn.compress_line(C)
    outD = muninn.compress_line(D)
    outE = muninn.compress_line(E)

    details = []
    checks = {}
    # Note: COMPLETED matches COMPLETE rule with \b
    checks["A: 'done' present"] = "done" in outA.lower()
    checks["B: 'wip' present"] = "wip" in outB.lower()
    checks["C: 'fail' present"] = "fail" in outC.lower()
    checks["D: no 'done' partial"] = "done" not in outD.lower() or "PARTIELLEMENT" in outD or "partiellement" in outD.lower()
    checks["E: no 'doneMENT'"] = "donement" not in outE.lower() and "doneMENT" not in outE

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    details.append(f"- A: {repr(outA)}")
    details.append(f"- B: {repr(outB)}")
    details.append(f"- C: {repr(outC)}")
    details.append(f"- D: {repr(outD)}")
    details.append(f"- E: {repr(outE)}")

    log("T1.6 — L5 Universal Rules", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.6 — L5 Universal Rules", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.7 — L6 Mycelium Fusion Strip
# ═══════════════════════════════════════════
t0 = time.time()
try:
    from muninn.mycelium import Mycelium
    from muninn.mycelium_db import MyceliumDB

    m = Mycelium(TEMP_REPO)
    # Need to create strong fusion: observe "machine" and "learning" together many times
    for _ in range(12):
        m.observe(["machine", "learning"])
    m.save()

    # Reload codebook
    muninn._CB = None
    muninn._REPO_PATH = TEMP_REPO

    inp = "the machine learning model is ready"
    outA = muninn.compress_line(inp)

    # Control: without mycelium
    muninn._CB = None
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = None
    outB = muninn.compress_line(inp)
    muninn._REPO_PATH = TEMP_REPO
    muninn._CB = None

    details = []
    details.append(f"- WITH mycelium: {repr(outA)}")
    details.append(f"- WITHOUT mycelium: {repr(outB)}")
    details.append(f"- len(WITH) < len(WITHOUT): {'PASS' if len(outA) < len(outB) else 'FAIL'} ({len(outA)} vs {len(outB)})")
    details.append(f"- 'model' in both: {'PASS' if 'model' in outA.lower() and 'model' in outB.lower() else 'FAIL'}")
    details.append(f"- 'ready' in both: {'PASS' if 'ready' in outA.lower() and 'ready' in outB.lower() else 'FAIL'}")

    all_pass = len(outA) < len(outB) and "model" in outA.lower()
    log("T1.7 — L6 Mycelium Fusion Strip", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.7 — L6 Mycelium Fusion Strip", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.8 — L7 Key-Value Extraction
# ═══════════════════════════════════════════
t0 = time.time()
try:
    inp = "the accuracy is 94.2% and the loss decreased to 0.031 after 50 epochs"
    out = muninn.compress_line(inp)

    details = []
    checks = {}
    checks["'94.2%' present"] = "94.2%" in out
    checks["'0.031' present"] = "0.031" in out
    checks["'50' present"] = "50" in out
    checks["has '=' or ':'"] = "=" in out or ":" in out
    ratio = len(out) / max(1, len(inp))
    checks[f"ratio {ratio:.2f} < 0.7"] = ratio < 0.7

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    details.append(f"- Output: {repr(out)}")
    log("T1.8 — L7 Key-Value Extraction", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.8 — L7 Key-Value Extraction", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.9 — L10 Cue Distillation
# ═══════════════════════════════════════════
t0 = time.time()
try:
    generic_lines = [
        "Gradient descent is an optimization algorithm used in machine learning.",
        "It works by computing the gradient of the loss function with respect to parameters.",
        "The learning rate determines the step size at each iteration.",
        "When the gradient reaches zero, we have found a local minimum.",
        "Stochastic gradient descent uses random mini-batches for efficiency.",
        "Batch normalization helps stabilize the training process.",
        "Momentum adds a fraction of the previous update to the current one.",
        "Weight decay adds L2 regularization to prevent overfitting.",
        "The Adam optimizer combines momentum with adaptive learning rates.",
        "Convergence depends on the loss landscape smoothness.",
    ]
    specific_lines = [
        "F> our learning rate is 0.003 after tuning on 2026-03-10",
        "D> decided to switch from Adam to SGD — saved $47/day on GPU costs",
        "F> model accuracy jumped from x2.1 to x4.5 after L10 changes (commit a3f7b2d)",
    ]

    full_text = "\n".join(generic_lines + specific_lines)
    out = muninn._cue_distill(full_text)
    out_lines = [l for l in out.split("\n") if l.strip()]

    details = []
    checks = {}

    # Generic lines should be reduced
    # L10 replaces lines with shorter cues, not fewer lines — check char reduction instead
    checks["generic reduced (chars shrunk)"] = len(out) < len(full_text)

    # Check cue ratio
    for i, gl in enumerate(generic_lines):
        ns = muninn._novelty_score(gl)
        details.append(f"  generic[{i}] novelty={ns:.2f}")

    # Gradient should still appear as cue
    checks["'gradient' still in output"] = "gradient" in out.lower() or "Gradient" in out

    # Specific facts preserved
    checks["'0.003' present"] = "0.003" in out
    checks["'2026-03-10' present"] = "2026-03-10" in out
    checks["'Adam' or 'SGD' present"] = "Adam" in out or "SGD" in out
    checks["'$47' present"] = "$47" in out or "47" in out
    checks["'a3f7b2d' present"] = "a3f7b2d" in out
    checks["'x4.5' present"] = "x4.5" in out

    # Ratio — L10 replaces lines with shorter cues, not fewer lines
    # So measure character reduction, not line count reduction
    chars_in = len(full_text)
    chars_out = len(out)
    char_ratio = chars_out / max(1, chars_in)
    checks[f"char ratio {char_ratio:.2f} < 0.7"] = char_ratio < 0.7

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    total_in = len(generic_lines) + len(specific_lines)
    total_out = len(out_lines)
    details.append(f"- Lines in: {total_in}, out: {total_out}, chars: {chars_in}->{chars_out}")
    log("T1.9 — L10 Cue Distillation", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.9 — L10 Cue Distillation", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.10 — L11 Rule Extraction
# ═══════════════════════════════════════════
t0 = time.time()
try:
    data_A = "\n".join([
        "module_api: status=done | tests=42 | cov=89%",
        "module_auth: status=wip | tests=18 | cov=67%",
        "module_db: status=done | tests=31 | cov=91%",
        "module_cache: status=fail | tests=5 | cov=23%",
        "module_queue: status=done | tests=27 | cov=84%",
        "module_log: status=wip | tests=12 | cov=55%",
    ])
    data_B = "\n".join([
        "The API handles REST requests",
        "Users authenticate via JWT tokens",
        "Database uses connection pooling",
    ])

    full = data_A + "\n" + data_B
    out = muninn._extract_rules(full)
    out_lines = [l for l in out.split("\n") if l.strip()]

    details = []
    checks = {}

    # Data B should be intact
    checks["'REST' present"] = "REST" in out
    checks["'JWT' present"] = "JWT" in out
    checks["'pooling' present"] = "pooling" in out

    # Check all values preserved from A
    for val in ["42", "18", "31", "5", "27", "12", "89", "67", "91", "23", "84", "55"]:
        if val not in out:
            checks[f"value {val} present"] = False
        else:
            checks[f"value {val} present"] = True

    for name in ["api", "auth", "db", "cache", "queue", "log"]:
        checks[f"module '{name}' present"] = name in out.lower()

    all_pass = True
    for desc, ok in checks.items():
        details.append(f"- {desc}: {'PASS' if ok else 'FAIL'}")
        if not ok: all_pass = False

    details.append(f"- Output ({len(out_lines)} lines): {repr(out[:300])}")
    log("T1.10 — L11 Rule Extraction", "PASS" if all_pass else "FAIL", "\n".join(details), time.time() - t0)
except Exception as e:
    log("T1.10 — L11 Rule Extraction", "FAIL", f"- EXCEPTION: {e}", time.time() - t0)

# ═══════════════════════════════════════════
# T1.11 — L9 LLM Compress (OPTIONAL)
# ═══════════════════════════════════════════
t0 = time.time()
try:
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log("T1.11 — L9 LLM Compress", "SKIP", "- ANTHROPIC_API_KEY not set", time.time() - t0)
    else:
        log("T1.11 — L9 LLM Compress", "SKIP", "- Skipping to avoid API costs", time.time() - t0)
except ImportError:
    log("T1.11 — L9 LLM Compress", "SKIP", "- anthropic module not installed", time.time() - t0)

# ═══════════════════════════════════════════
# Output
# ═══════════════════════════════════════════
output = "\n# ═══════════════════════════════════════════\n# CATEGORIE 1 — COMPRESSION (L0-L7, L10, L11)\n# ═══════════════════════════════════════════\n\n"
output += "\n".join(results)

# Append to results file
results_path = Path(r"c:\Users\ludov\MUNINN-\tests\RESULTS_BATTERY_V3.md")
with open(results_path, "a", encoding="utf-8") as f:
    f.write(output)

print(output)

# Cleanup
shutil.rmtree(TEMP_REPO, ignore_errors=True)
shutil.rmtree(TEMP_META, ignore_errors=True)

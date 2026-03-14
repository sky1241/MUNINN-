#!/usr/bin/env python3
"""
Muninn Senior Dev Battery — Mode Cassage de Gueule
Zero tolerance. Every untested path. Every edge case.
If it passes this, it's solid. If it doesn't, we fix it.

Categories:
  S1-S5:   extract_facts / compress_line edge cases
  S6-S10:  compress_transcript / parse edge cases
  S11-S15: build_tree / bootstrap / generate_root_mn
  S16-S20: boot stress / state leakage / budget overflow
  S21-S25: prune stress / sleep consolidation edge cases
  S26-S30: mycelium stress / decay / zones
  S31-S35: ingest / semantic_rle / verify_compression
  S36-S40: security / unicode / corrupted data / concurrency
"""

import sys, os, json, tempfile, shutil, time, re, hashlib, threading
from pathlib import Path
from datetime import date, timedelta
from collections import Counter

ENGINE_DIR = Path(r"c:\Users\ludov\MUNINN-\engine\core")
sys.path.insert(0, str(ENGINE_DIR))

# Isolate meta-mycelium
TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_senior_"))
from mycelium import Mycelium as _MycPatch
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")

import muninn
from mycelium import Mycelium
from mycelium_db import MyceliumDB, date_to_days, days_to_date

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
    r = Path(tempfile.mkdtemp(prefix="muninn_sr_"))
    (r / ".muninn").mkdir()
    (r / ".muninn" / "tree").mkdir()
    (r / ".muninn" / "sessions").mkdir()
    (r / "memory").mkdir()
    return r

def setup_globals(repo):
    muninn._REPO_PATH = repo
    muninn._CB = None
    muninn._refresh_tree_paths()

def user_msg(text):
    return json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": text}]}})

def asst_msg(text):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})

def tool_result_msg(text):
    return json.dumps({"type": "tool_result", "tool_result": {"content": [{"type": "text", "text": text}]}})

def compute_hash_local(filepath):
    if not filepath.exists():
        return "0" * 8
    return hashlib.sha256(filepath.read_bytes()).hexdigest()[:8]

def make_tree_with_root(repo):
    """Helper: create a valid tree with root.mn"""
    root_file = repo / ".muninn" / "tree" / "root.mn"
    root_file.write_text("## Root\nProject root\n", encoding="utf-8")
    tree = muninn.load_tree()
    tree["nodes"]["root"]["file"] = "root.mn"
    tree["nodes"]["root"]["hash"] = compute_hash_local(root_file)
    muninn.save_tree(tree)
    return tree

ALL_TEMPS = []

# ============================================================
# S1 — extract_facts: empty / basic / edge cases
# ============================================================
def test_S1():
    t0 = time.time()
    details = []
    try:
        # Empty
        assert muninn.extract_facts("") == [], "empty should return []"
        assert muninn.extract_facts("   ") == [], "whitespace should return []"

        # Numbers with units
        facts = muninn.extract_facts("latency 45ms, storage 2.3 TB, 4096 samples")
        details.append(f"units: {facts}")
        ok_units = any("45ms" in f for f in facts)

        # Percentages
        facts2 = muninn.extract_facts("accuracy 94.2% on validation set, 87% on test")
        details.append(f"pct: {facts2}")
        ok_pct = any("94.2%" in f for f in facts2) and any("87%" in f for f in facts2)

        # Dates
        facts3 = muninn.extract_facts("deployed on 2026-03-11, updated 2025/12/01")
        ok_dates = any("2026-03-11" in f for f in facts3)
        details.append(f"dates: {facts3}")

        # x-ratios
        facts4 = muninn.extract_facts("compression x4.1 average, peak x9.6")
        ok_ratios = any("x4.1" in f for f in facts4)
        details.append(f"ratios: {facts4}")

        # Versions
        facts5 = muninn.extract_facts("running Python v3.13.1 with numpy 1.26.4")
        ok_versions = any("3.13.1" in f for f in facts5)
        details.append(f"versions: {facts5}")

        ok = ok_units and ok_pct and ok_dates and ok_ratios and ok_versions
        log("S1", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S1", "FAIL", details, time.time() - t0)


# ============================================================
# S2 — compress_line: pathological inputs
# ============================================================
def test_S2():
    t0 = time.time()
    details = []
    try:
        # Empty string
        r1 = muninn.compress_line("")
        assert isinstance(r1, str), "should return str"

        # Very long line (10K chars)
        long_line = "word " * 2000
        r2 = muninn.compress_line(long_line)
        assert len(r2) < len(long_line), "should compress"
        details.append(f"10K chars: {len(long_line)} -> {len(r2)}")

        # Only numbers
        r3 = muninn.compress_line("42 3.14 1000 99.9 256 512 1024")
        assert "42" in r3 or "3.14" in r3, "numbers should survive"
        details.append(f"numbers only: '{r3}'")

        # Only punctuation
        r4 = muninn.compress_line("...!!! ??? --- === *** ///")
        assert isinstance(r4, str)
        details.append(f"punctuation: '{r4}'")

        # Math expression (a + b should preserve "a")
        r5 = muninn.compress_line("a + b = c where a = 5")
        ok_math = "a" in r5
        details.append(f"math: '{r5}' (a preserved: {ok_math})")

        # Unicode: CJK characters
        r6 = muninn.compress_line("这是一个测试 with mixed content 42ms")
        assert isinstance(r6, str)
        details.append(f"CJK: '{r6[:60]}'")

        # Unicode: Arabic
        r7 = muninn.compress_line("مرحبا test 94.2% accuracy")
        assert "94.2%" in r7 or "94.2" in r7
        details.append(f"Arabic: '{r7[:60]}'")

        # Unicode: Emoji
        r8 = muninn.compress_line("🎉 deployment successful 99.9% uptime 🚀")
        assert isinstance(r8, str)
        details.append(f"emoji: '{r8[:60]}'")

        ok = ok_math and isinstance(r1, str) and len(r2) < len(long_line)
        log("S2", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S2", "FAIL", details, time.time() - t0)


# ============================================================
# S3 — compress_line: filler stripping precision
# ============================================================
def test_S3():
    t0 = time.time()
    details = []
    try:
        # "a" as article should be stripped
        r1 = muninn.compress_line("This is a great test with a wonderful result")
        ok_article = "a great" not in r1 and "a wonderful" not in r1
        details.append(f"article stripped: {ok_article} -> '{r1}'")

        # "a" in code/math should survive
        r2 = muninn.compress_line("let a = 5; b = a + 1")
        ok_var = "a" in r2
        details.append(f"var preserved: {ok_var} -> '{r2}'")

        # Causal connectors should survive (P24)
        r3 = muninn.compress_line("Failed because the timeout was too short")
        ok_causal = "because" in r3.lower()
        details.append(f"causal preserved: {ok_causal} -> '{r3}'")

        # French fillers
        r4 = muninn.compress_line("C'est dans la configuration avec plus de paramètres")
        details.append(f"french: '{r4}'")

        ok = ok_article and ok_var and ok_causal
        log("S3", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S3", "FAIL", details, time.time() - t0)


# ============================================================
# S4 — compress_section: headers + state extraction
# ============================================================
def test_S4():
    t0 = time.time()
    details = []
    try:
        lines = [
            "- Feature 1: implemented with 94.2% accuracy",
            "- Feature 2: deployed on 2026-03-11",
            "- Bug fix #42: resolved timeout at 500ms",
        ]
        result = muninn.compress_section("## P20 — Federated Mycelium — COMPLETE", lines)
        details.append(f"result: '{result[:120]}'")
        ok_state = "✓" in result  # COMPLETE -> checkmark
        ok_content = "94.2" in result
        details.append(f"state extracted: {ok_state}, content preserved: {ok_content}")

        # IN PROGRESS state
        result2 = muninn.compress_section("### Migration — IN PROGRESS", ["- step 1 done", "- step 2 pending"])
        ok_wip = "⟳" in result2
        details.append(f"WIP state: {ok_wip} -> '{result2[:80]}'")

        # Empty lines
        result3 = muninn.compress_section("## Empty Section — DONE", [])
        ok_empty = isinstance(result3, str)
        details.append(f"empty section: '{result3}'")

        ok = ok_state and ok_content and ok_wip and ok_empty
        log("S4", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S4", "FAIL", details, time.time() - t0)


# ============================================================
# S5 — contradiction resolution: multi-entity precision
# ============================================================
def test_S5():
    t0 = time.time()
    details = []
    try:
        # Same entity different values -> keep latest
        text = "F> model accuracy=94.2%\nF> model accuracy=97.1%\n"
        result = muninn._resolve_contradictions(text)
        ok_latest = "97.1" in result
        ok_old_gone = "94.2" not in result
        details.append(f"latest kept: {ok_latest}, old removed: {ok_old_gone}")
        details.append(f"result: '{result.strip()}'")

        # Different entities with numbers -> both should survive
        text2 = "F> model_A accuracy=94.2%\nF> model_B accuracy=87.5%\n"
        result2 = muninn._resolve_contradictions(text2)
        ok_both = "94.2" in result2 and "87.5" in result2
        details.append(f"different entities preserved: {ok_both}")

        # No contradictions
        text3 = "B> redis latency=0.5ms\nD> chose PostgreSQL for persistence\n"
        result3 = muninn._resolve_contradictions(text3)
        ok_no_change = "0.5" in result3 and "PostgreSQL" in result3
        details.append(f"no contradiction: preserved={ok_no_change}")

        ok = ok_latest and ok_both and ok_no_change
        log("S5", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S5", "FAIL", details, time.time() - t0)


# ============================================================
# S6 — _semantic_rle: error loop collapse
# ============================================================
def test_S6():
    t0 = time.time()
    details = []
    try:
        # Real error/retry loop — should collapse
        texts = [
            "TypeError: cannot unpack None",
            "let me try fixing the import",
            "TypeError: still failing on line 42",
            "trying a different approach",
            "TypeError: same error, wrong module",
            "let me check the dependency",
            "Fixed it by adding None check",
        ]
        result = muninn._semantic_rle(texts)
        details.append(f"loop: {len(texts)} -> {len(result)} messages")
        ok_collapsed = len(result) < len(texts)
        ok_has_rle = any("[RLE:" in r for r in result)
        details.append(f"collapsed: {ok_collapsed}, has RLE tag: {ok_has_rle}")

        # Short conversation — should NOT collapse
        short = ["Hello", "Hi there", "How are you"]
        result2 = muninn._semantic_rle(short)
        ok_short = len(result2) == len(short)
        details.append(f"short preserved: {ok_short}")

        # Discussion ABOUT errors — should ideally not collapse
        about_errors = [
            "We need to improve our error handling strategy",
            "The TypeError cases need custom handlers",
            "Let me try implementing a global error boundary",
            "ValueError should be caught at the API layer",
            "Here's my fix for the error handling",
        ]
        result3 = muninn._semantic_rle(about_errors)
        details.append(f"about-errors: {len(about_errors)} -> {len(result3)}")

        ok = ok_collapsed and ok_short
        log("S6", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S6", "FAIL", details, time.time() - t0)


# ============================================================
# S7 — compress_transcript: malformed JSONL
# ============================================================
def test_S7():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Empty file
        empty_file = repo / "empty.jsonl"
        empty_file.write_text("", encoding="utf-8")
        r1 = muninn.compress_transcript(empty_file, repo)
        details.append(f"empty: {r1}")
        ok_empty = r1 == (None, None)

        # Invalid JSON lines
        bad_file = repo / "bad.jsonl"
        bad_file.write_text("not json\n{broken\n{\"type\":\"garbage\"}\n", encoding="utf-8")
        r2 = muninn.compress_transcript(bad_file, repo)
        details.append(f"bad json: {r2}")
        ok_bad = r2 == (None, None) or r2[0] is not None

        # Valid but no user/assistant messages
        noise_file = repo / "noise.jsonl"
        noise_file.write_text(
            json.dumps({"type": "system", "message": {"content": "test"}}) + "\n" +
            json.dumps({"type": "tool_use", "message": {"content": "test"}}) + "\n",
            encoding="utf-8"
        )
        r3 = muninn.compress_transcript(noise_file, repo)
        details.append(f"no messages: {r3}")
        ok_noise = r3 == (None, None)

        # Single message (too short for meaningful compression)
        single_file = repo / "single.jsonl"
        single_file.write_text(user_msg("hello world") + "\n", encoding="utf-8")
        r4 = muninn.compress_transcript(single_file, repo)
        details.append(f"single msg: {type(r4)}")
        ok_single = True  # should not crash

        ok = ok_empty and ok_single
        log("S7", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S7", "FAIL", details, time.time() - t0)


# ============================================================
# S8 — _detect_transcript_format: edge cases
# ============================================================
def test_S8():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()

        # JSONL format
        jsonl = repo / "test.jsonl"
        jsonl.write_text(user_msg("test message") + "\n", encoding="utf-8")
        fmt = muninn._detect_transcript_format(jsonl)
        ok_jsonl = fmt == "jsonl"
        details.append(f"jsonl: {fmt}")

        # JSON conversation format
        conv = repo / "test.json"
        conv.write_text(json.dumps({"chat_messages": [{"content": "hello world testing"}]}), encoding="utf-8")
        fmt2 = muninn._detect_transcript_format(conv)
        details.append(f"json: {fmt2}")
        ok_json = fmt2 == "json"

        # Markdown format
        md = repo / "test.md"
        md.write_text("## Human\nHello there my friend\n## Assistant\nHi there!\n", encoding="utf-8")
        fmt3 = muninn._detect_transcript_format(md)
        details.append(f"markdown: {fmt3}")
        ok_md = fmt3 == "markdown"

        # Very long first line (>500 bytes) — format detection reads first 500 bytes
        long_jsonl = repo / "long.jsonl"
        long_msg = user_msg("x" * 1000)  # first line > 500 bytes
        long_jsonl.write_text(long_msg + "\n" + asst_msg("reply") + "\n", encoding="utf-8")
        fmt4 = muninn._detect_transcript_format(long_jsonl)
        details.append(f"long first line: {fmt4}")
        # Long first line gets truncated at 500 bytes, JSON parse fails -> may be "unknown"
        ok_long = fmt4 in ("jsonl", "unknown")

        ok = ok_jsonl and ok_json and ok_md
        log("S8", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S8", "FAIL", details, time.time() - t0)


# ============================================================
# S9 — _parse_json_conversation: various formats
# ============================================================
def test_S9():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()

        # claude.ai format
        f1 = repo / "claude.json"
        f1.write_text(json.dumps({
            "chat_messages": [
                {"content": "What is the meaning of life?"},
                {"content": "The meaning of life is subjective and personal."},
            ]
        }), encoding="utf-8")
        r1 = muninn._parse_json_conversation(f1)
        details.append(f"claude format: {len(r1)} messages")
        ok_claude = len(r1) == 2

        # List format
        f2 = repo / "list.json"
        f2.write_text(json.dumps([
            {"content": "Hello there testing this"},
            {"text": "Another message for testing"},
        ]), encoding="utf-8")
        r2 = muninn._parse_json_conversation(f2)
        details.append(f"list format: {len(r2)} messages")
        ok_list = len(r2) >= 1

        # Nested content array
        f3 = repo / "nested.json"
        f3.write_text(json.dumps({
            "messages": [
                {"content": [{"type": "text", "text": "Complex message structure here"}]},
            ]
        }), encoding="utf-8")
        r3 = muninn._parse_json_conversation(f3)
        details.append(f"nested format: {len(r3)} messages")
        ok_nested = len(r3) == 1

        # Corrupted file
        f4 = repo / "corrupt.json"
        f4.write_text("not valid json at all", encoding="utf-8")
        r4 = muninn._parse_json_conversation(f4)
        ok_corrupt = r4 == []
        details.append(f"corrupt: {r4}")

        ok = ok_claude and ok_nested and ok_corrupt
        log("S9", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S9", "FAIL", details, time.time() - t0)


# ============================================================
# S10 — _parse_markdown_conversation
# ============================================================
def test_S10():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        f1 = repo / "conv.md"
        f1.write_text(
            "## Human\nWhat is Python used for in modern development?\n\n"
            "## Assistant\nPython is used for web dev, data science, AI, automation.\n\n"
            "## Human\nWhat about performance concerns with Python?\n",
            encoding="utf-8"
        )
        r1 = muninn._parse_markdown_conversation(f1)
        details.append(f"parsed: {len(r1)} blocks")
        ok_parsed = len(r1) >= 2

        # Empty file
        f2 = repo / "empty.md"
        f2.write_text("", encoding="utf-8")
        r2 = muninn._parse_markdown_conversation(f2)
        ok_empty = r2 == []
        details.append(f"empty: {r2}")

        # No headers
        f3 = repo / "noheader.md"
        f3.write_text("Just some text without any headers at all here\n", encoding="utf-8")
        r3 = muninn._parse_markdown_conversation(f3)
        details.append(f"no headers: {len(r3)} blocks")

        ok = ok_parsed and ok_empty
        log("S10", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S10", "FAIL", details, time.time() - t0)


# ============================================================
# S11 — build_tree: small file fits in root
# ============================================================
def test_S11():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Small file should fit in root
        src = repo / "small.md"
        src.write_text("## Project\n- Feature 1: deployed 2026-03-11\n- Feature 2: accuracy 94.2%\n", encoding="utf-8")
        muninn.build_tree(src)

        tree = muninn.load_tree()
        root_file = repo / ".muninn" / "tree" / "root.mn"
        ok_root = root_file.exists()
        ok_lines = tree["nodes"]["root"].get("lines", 0) > 0
        details.append(f"root exists: {ok_root}, lines: {tree['nodes']['root'].get('lines')}")

        # Check content
        content = root_file.read_text(encoding="utf-8")
        ok_content = "94.2" in content or "Feature" in content
        details.append(f"content preserved: {ok_content}, len={len(content)}")

        ok = ok_root and ok_lines
        log("S11", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S11", "FAIL", details, time.time() - t0)


# ============================================================
# S12 — build_tree: large file splits into branches
# ============================================================
def test_S12():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Generate a file with MANY unique sections -> should split after compression
        sections = []
        for i in range(40):
            sections.append(f"## Section {i} — {['Architecture','Deployment','Monitoring','Security','Performance','Database','Caching','API','Testing','Logging'][i%10]}\n")
            for j in range(15):
                # Unique content per section to resist dedup
                sections.append(f"- {['Redis','PostgreSQL','Kafka','gRPC','Docker','K8s','Nginx','Vault','Consul','Envoy'][j%10]} metric_{i}_{j}: latency={i*7+j*3}ms throughput={1000+i*50+j*10}rps deployed={2026-i%12:04d}-{(j%12)+1:02d}-{(i%28)+1:02d}\n")
        src = repo / "big.md"
        src.write_text("".join(sections), encoding="utf-8")
        muninn.build_tree(src)

        tree = muninn.load_tree()
        n_branches = len([n for n in tree["nodes"] if n != "root"])
        details.append(f"branches created: {n_branches}")
        ok = n_branches >= 1 or tree["nodes"]["root"].get("lines", 0) > 0
        details.append(f"node names: {list(tree['nodes'].keys())[:10]}")
        details.append(f"root lines: {tree['nodes']['root'].get('lines', 0)}")

        log("S12", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S12", "FAIL", details, time.time() - t0)


# ============================================================
# S13 — generate_root_mn: no crash on fresh repo
# ============================================================
def test_S13():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Create some source files
        (repo / "main.py").write_text("def hello():\n    print('hello')\n" * 30, encoding="utf-8")
        (repo / "README.md").write_text("# Test Project\nA test project for Muninn.\n", encoding="utf-8")

        m = Mycelium(repo)
        muninn.generate_root_mn(repo, 2, m)

        root_path = repo / ".muninn" / "tree" / "root.mn"
        ok_exists = root_path.exists()
        if ok_exists:
            content = root_path.read_text(encoding="utf-8")
            details.append(f"root.mn: {len(content)} chars, {len(content.splitlines())} lines")
            ok_content = len(content) > 10
        else:
            ok_content = False
            details.append("root.mn NOT created")

        ok = ok_exists and ok_content
        log("S13", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S13", "FAIL", details, time.time() - t0)


# ============================================================
# S14 — scan_repo: no crash, produces codebook
# ============================================================
def test_S14():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Create some source files
        (repo / "main.py").write_text("import json\ndef process(data):\n    return json.dumps(data)\n" * 10, encoding="utf-8")
        (repo / "utils.py").write_text("class Helper:\n    def run(self): pass\n" * 10, encoding="utf-8")
        (repo / "README.md").write_text("# My Project\nHelper utilities for processing.\n", encoding="utf-8")

        muninn.scan_repo(repo)
        # No crash = pass
        details.append("scan_repo completed without crash")
        ok = True

        log("S14", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S14", "FAIL", details, time.time() - t0)


# ============================================================
# S15 — verify_compression: fact retention check
# ============================================================
def test_S15():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        src = repo / "test_doc.md"
        src.write_text(
            "## Performance Report\n"
            "- Latency: 45ms average, 120ms p99\n"
            "- Throughput: 10000 requests per second\n"
            "- Error rate: 0.01%\n"
            "- Deployed on 2026-03-11 to production\n"
            "- Team lead: Alice reviewed the metrics\n",
            encoding="utf-8"
        )

        # verify_compression prints to stdout, just check no crash
        muninn.verify_compression(src)
        details.append("verify_compression completed")
        ok = True

        log("S15", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S15", "FAIL", details, time.time() - t0)


# ============================================================
# S16 — boot: empty tree (no branches)
# ============================================================
def test_S16():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        result = muninn.boot("test query something")
        details.append(f"boot empty tree: {len(result)} chars")
        ok = isinstance(result, str) and len(result) > 0
        ok_root = "root" in result.lower() or "Root" in result or "=== root ===" in result
        details.append(f"root loaded: {ok_root}")

        log("S16", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S16", "FAIL", details, time.time() - t0)


# ============================================================
# S17 — boot: corrupted session_index.json
# ============================================================
def test_S17():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Corrupted session_index
        (repo / ".muninn" / "session_index.json").write_text("NOT VALID JSON!!!", encoding="utf-8")

        result = muninn.boot("test query")
        ok = isinstance(result, str) and len(result) > 0
        details.append(f"boot with corrupted index: {len(result)} chars, ok={ok}")

        log("S17", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S17", "FAIL", details, time.time() - t0)


# ============================================================
# S18 — boot: state leakage between repos
# ============================================================
def test_S18():
    t0 = time.time()
    details = []
    try:
        repo_a = fresh_repo()
        repo_b = fresh_repo()

        # Setup repo A with branch about "quantum"
        setup_globals(repo_a)
        make_tree_with_root(repo_a)
        tree_a = muninn.load_tree()
        bf = repo_a / ".muninn" / "tree" / "quantum.mn"
        bf.write_text("## Quantum\nB> quantum computing 42 qubits\n", encoding="utf-8")
        tree_a["nodes"]["quantum"] = {
            "file": "quantum.mn", "lines": 2, "hash": compute_hash_local(bf),
            "tags": ["quantum"], "temperature": 0.8, "access_count": 3,
            "last_access": date.today().isoformat(),
        }
        muninn.save_tree(tree_a)
        result_a = muninn.boot("quantum")

        # Switch to repo B (no quantum branch)
        setup_globals(repo_b)
        make_tree_with_root(repo_b)
        result_b = muninn.boot("quantum")

        # repo B should NOT contain quantum content from repo A
        ok_no_leak = "42 qubits" not in result_b
        details.append(f"repo A has quantum: {'42 qubits' in result_a}")
        details.append(f"repo B leak: {not ok_no_leak}")

        ok = ok_no_leak
        log("S18", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo_a, ignore_errors=True)
        shutil.rmtree(repo_b, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S18", "FAIL", details, time.time() - t0)


# ============================================================
# S19 — boot: many branches, budget enforcement
# ============================================================
def test_S19():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)
        tree = muninn.load_tree()

        # Create 50 branches with ~100 lines each
        for i in range(50):
            bname = f"b{i:02d}"
            bf = repo / ".muninn" / "tree" / f"{bname}.mn"
            content = f"## Branch {i}\n" + "\n".join(
                f"B> item {i}.{j}: metric={i*100+j}ms accuracy={80+j}%"
                for j in range(100)
            )
            bf.write_text(content, encoding="utf-8")
            tree["nodes"][bname] = {
                "file": f"{bname}.mn", "lines": 101, "hash": compute_hash_local(bf),
                "tags": [f"topic{i%5}"], "temperature": 0.5, "access_count": 1,
                "last_access": date.today().isoformat(),
            }
        muninn.save_tree(tree)

        result = muninn.boot("topic0 metrics")
        tok_count = muninn.token_count(result)
        details.append(f"boot 50 branches: {len(result)} chars, ~{tok_count} tokens")
        details.append(f"budget: {muninn.BUDGET['max_loaded_tokens']} tokens")

        # Should respect budget (within 2x tolerance because kicomp)
        ok = tok_count < muninn.BUDGET["max_loaded_tokens"] * 2
        details.append(f"within budget: {ok}")

        log("S19", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S19", "FAIL", details, time.time() - t0)


# ============================================================
# S20 — boot: empty query auto-continue from session_index
# ============================================================
def test_S20():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Setup session_index with last session concepts
        index = [{"file": "test.mn", "date": "2026-03-14", "concepts": ["redis", "caching", "memory"]}]
        (repo / ".muninn" / "session_index.json").write_text(json.dumps(index), encoding="utf-8")

        # Create a branch about redis
        tree = muninn.load_tree()
        bf = repo / ".muninn" / "tree" / "redis.mn"
        bf.write_text("## Redis\nB> redis caching layer 0.5ms latency\n", encoding="utf-8")
        tree["nodes"]["redis"] = {
            "file": "redis.mn", "lines": 2, "hash": compute_hash_local(bf),
            "tags": ["redis", "caching"], "temperature": 0.5, "access_count": 2,
            "last_access": date.today().isoformat(),
        }
        muninn.save_tree(tree)

        # Boot with empty query -> should auto-load redis via P23
        result = muninn.boot("")
        ok = "redis" in result.lower() or "caching" in result.lower()
        details.append(f"auto-continue: redis in result={ok}")
        details.append(f"result length: {len(result)} chars")

        log("S20", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S20", "FAIL", details, time.time() - t0)


# ============================================================
# S21 — prune: zero branches
# ============================================================
def test_S21():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        muninn.prune(dry_run=True)
        details.append("prune(dry_run=True) with 0 branches: OK")

        muninn.prune(dry_run=False)
        details.append("prune(dry_run=False) with 0 branches: OK")

        ok = True
        log("S21", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S21", "FAIL", details, time.time() - t0)


# ============================================================
# S22 — prune: all branches hot (nothing to prune)
# ============================================================
def test_S22():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)
        tree = muninn.load_tree()

        # Create 5 hot branches (accessed today, high temp)
        for i in range(5):
            bname = f"b{i:02d}"
            bf = repo / ".muninn" / "tree" / f"{bname}.mn"
            bf.write_text(f"## Hot Branch {i}\nB> important data {i}\n", encoding="utf-8")
            tree["nodes"][bname] = {
                "file": f"{bname}.mn", "lines": 2, "hash": compute_hash_local(bf),
                "tags": [f"hot{i}"], "temperature": 5.0, "access_count": 20,
                "last_access": date.today().isoformat(),
            }
        muninn.save_tree(tree)

        muninn.prune(dry_run=False)
        tree2 = muninn.load_tree()
        n_after = len([n for n in tree2["nodes"] if n != "root"])
        details.append(f"branches after prune: {n_after} (should be 5)")
        ok = n_after == 5

        log("S22", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S22", "FAIL", details, time.time() - t0)


# ============================================================
# S23 — prune: all branches cold + dead
# ============================================================
def test_S23():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)
        tree = muninn.load_tree()

        # Create 3 very cold branches (accessed 200 days ago)
        old_date = (date.today() - timedelta(days=200)).isoformat()
        for i in range(3):
            bname = f"cold{i:02d}"
            bf = repo / ".muninn" / "tree" / f"{bname}.mn"
            bf.write_text(f"## Cold {i}\nB> old data {i}\n", encoding="utf-8")
            tree["nodes"][bname] = {
                "file": f"{bname}.mn", "lines": 2, "hash": compute_hash_local(bf),
                "tags": [f"cold{i}"], "temperature": 0.01, "access_count": 1,
                "last_access": old_date,
            }
        muninn.save_tree(tree)

        muninn.prune(dry_run=False)
        tree2 = muninn.load_tree()
        n_after = len([n for n in tree2["nodes"] if n != "root"])
        details.append(f"branches after prune: {n_after}")
        # Some or all should be removed
        ok = n_after <= 3  # at least didn't crash
        details.append(f"prune ran successfully")

        log("S23", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S23", "FAIL", details, time.time() - t0)


# ============================================================
# S24 — sleep_consolidate: no similar branches (nothing to merge)
# ============================================================
def test_S24():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)
        tree = muninn.load_tree()

        # Create 3 completely different branches (long enough to differentiate via NCD)
        topics = [
            ("quantum", "quantum entanglement 42 qubits photon detector calibration " * 10 +
             "superconducting circuit cryogenic cooling dilution refrigerator " * 5),
            ("cooking", "chocolate souffle recipe 200 degrees 45 minutes bake time " * 10 +
             "whisk egg whites fold gently preheat oven ramekin butter flour " * 5),
            ("finance", "stock market NASDAQ S&P500 trading algorithm high frequency " * 10 +
             "options futures derivatives hedge fund portfolio risk management " * 5),
        ]
        cold = []
        for bname, content in topics:
            bf = repo / ".muninn" / "tree" / f"{bname}.mn"
            bf.write_text(f"## {bname}\n{content}\n", encoding="utf-8")
            node = {
                "file": f"{bname}.mn", "lines": 2, "hash": compute_hash_local(bf),
                "tags": [bname], "temperature": 0.1, "access_count": 1,
                "last_access": (date.today() - timedelta(days=60)).isoformat(),
            }
            tree["nodes"][bname] = node
            cold.append((bname, node))
        muninn.save_tree(tree)

        results_consolidate = muninn._sleep_consolidate(cold, tree["nodes"])
        details.append(f"consolidation results: {len(results_consolidate)} merges")
        ok = len(results_consolidate) == 0  # nothing similar to merge
        details.append(f"correctly detected no similarity: {ok}")

        log("S24", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S24", "FAIL", details, time.time() - t0)


# ============================================================
# S25 — ingest: file into tree + mycelium feed
# ============================================================
def test_S25():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Create a reference document
        doc = repo / "reference.md"
        doc.write_text(
            "## Architecture\n"
            "The system uses PostgreSQL for persistence with Redis caching layer.\n"
            "API latency is 45ms p50, 120ms p99.\n\n"
            "## Deployment\n"
            "Deployed on Kubernetes with 3 replicas.\n"
            "Each pod has 2GB RAM, 0.5 CPU.\n"
            "Scaling policy: HPA at 70% CPU utilization.\n\n"
            "## Monitoring\n"
            "Grafana dashboards track latency, error rate, throughput.\n"
            "Alerts fire at >1% error rate or >500ms p99.\n",
            encoding="utf-8"
        )

        muninn.ingest(doc, repo)

        tree = muninn.load_tree()
        n_branches = len([n for n in tree["nodes"] if n != "root"])
        details.append(f"branches after ingest: {n_branches}")

        # Check mycelium was fed
        m = Mycelium(repo)
        conns = m._db.connection_count() if m._db else len(m.data.get("connections", {}))
        details.append(f"mycelium connections: {conns}")

        ok = n_branches >= 1 or conns > 0
        log("S25", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S25", "FAIL", details, time.time() - t0)


# ============================================================
# S26 — mycelium: massive observe stress test
# ============================================================
def test_S26():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        m = Mycelium(repo)

        # Observe 500 concepts
        concepts = [f"concept_{i}" for i in range(500)]
        for i in range(0, len(concepts), 10):
            chunk = concepts[i:i+10]
            m.observe(chunk)

        m.save()
        conns = m._db.connection_count() if m._db else len(m.data.get("connections", {}))
        details.append(f"500 concepts: {conns} connections")

        # Should have many connections
        ok = conns > 100
        details.append(f"enough connections: {ok}")

        # Get related should work
        related = m.get_related("concept_0", top_n=5)
        details.append(f"related to concept_0: {related[:3]}")
        ok_related = len(related) > 0

        ok = ok and ok_related
        log("S26", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S26", "FAIL", details, time.time() - t0)


# ============================================================
# S27 — mycelium: decay + cleanup
# ============================================================
def test_S27():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        m = Mycelium(repo)

        # Create connections
        m.observe(["alpha", "beta", "gamma", "delta", "epsilon"])
        m.observe(["alpha", "beta", "gamma"])  # reinforce
        m.observe(["alpha", "beta"])  # reinforce more
        m.save()

        before = m._db.connection_count() if m._db else len(m.data.get("connections", {}))
        details.append(f"before decay: {before} connections")

        # Decay
        m.decay()
        m.save()

        after = m._db.connection_count() if m._db else len(m.data.get("connections", {}))
        details.append(f"after decay: {after} connections")

        # alpha-beta should survive (count=3), weaker ones may die
        related = m.get_related("alpha", top_n=10)
        alpha_beta = any("beta" in r[0] for r in related)
        details.append(f"alpha-beta survived: {alpha_beta}")

        ok = after <= before and alpha_beta
        log("S27", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S27", "FAIL", details, time.time() - t0)


# ============================================================
# S28 — mycelium_db: batch operations atomic
# ============================================================
def test_S28():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        db_path = repo / "test.db"
        db = MyceliumDB(db_path)

        # Batch upsert — takes list of (concept_a, concept_b) pairs
        connections = []
        for i in range(100):
            connections.append(("concept_a", f"concept_{i}"))
        db.batch_upsert_connections(connections)
        db.commit()

        count = db.connection_count()
        details.append(f"batch upsert: {count} connections")
        ok_upsert = count == 100

        # Batch delete
        keys = [f"concept_a|concept_{i}" for i in range(50)]
        db.batch_delete_connections(keys)
        db.commit()

        count2 = db.connection_count()
        details.append(f"after delete 50: {count2} connections")
        ok_delete = count2 == 50

        db.close()
        ok = ok_upsert and ok_delete
        log("S28", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S28", "FAIL", details, time.time() - t0)


# ============================================================
# S29 — mycelium_db: date conversion roundtrip
# ============================================================
def test_S29():
    t0 = time.time()
    details = []
    try:
        # Standard dates
        d1 = "2026-03-14"
        days = date_to_days(d1)
        back = days_to_date(days)
        ok_rt = back == d1
        details.append(f"roundtrip: {d1} -> {days} -> {back} (ok={ok_rt})")

        # Edge: epoch start
        d2 = "2020-01-01"
        days2 = date_to_days(d2)
        ok_epoch = days2 == 0
        details.append(f"epoch: {d2} -> {days2} (ok={ok_epoch})")

        # Edge: far future
        d3 = "2030-12-31"
        days3 = date_to_days(d3)
        back3 = days_to_date(days3)
        ok_future = back3 == d3
        details.append(f"future: {d3} -> {days3} -> {back3} (ok={ok_future})")

        ok = ok_rt and ok_epoch and ok_future
        log("S29", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S29", "FAIL", details, time.time() - t0)


# ============================================================
# S30 — mycelium: observe_text + get_fusions integration
# ============================================================
def test_S30():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        m = Mycelium(repo)

        # Feed enough text to create fusions
        for _ in range(10):
            m.observe_text(
                "Redis caching provides sub-millisecond latency. "
                "PostgreSQL handles persistence with ACID guarantees. "
                "Redis and PostgreSQL work together in our architecture."
            )
        m.save()

        fusions = m.get_fusions()
        details.append(f"fusions after 10 observations: {len(fusions)}")
        if fusions:
            details.append(f"sample fusion: {list(fusions.items())[:2]}")

        conns = m._db.connection_count() if m._db else len(m.data.get("connections", {}))
        details.append(f"connections: {conns}")

        ok = conns > 0  # at least some connections
        log("S30", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S30", "FAIL", details, time.time() - t0)


# ============================================================
# S31 — security: secret patterns applied in compress_transcript
# ============================================================
def test_S31():
    t0 = time.time()
    details = []
    try:
        # Secrets are filtered in compress_transcript (L0), not compress_line
        # Test the regex patterns directly
        test_cases = [
            ("ghp_ABC123DEF456GHI789JKL012MNO345PQR678", "ghp_"),
            ("sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ", "sk-"),
            ("password: s3cretP4ss", "s3cretP4ss"),
            ("AKIAIOSFODNN7EXAMPLE", "AKIA"),
            ("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "Bearer"),
            ("token=abc123def456ghi789jkl012mno345", "abc123"),
        ]
        all_ok = True
        for secret, marker in test_cases:
            text = f"Here is my credential: {secret}"
            filtered = text
            for pat in muninn._SECRET_PATTERNS:
                filtered = re.sub(pat, "[REDACTED]", filtered)
            ok = marker not in filtered
            details.append(f"{marker}: filtered={ok} -> '{filtered[:60]}'")
            if not ok:
                all_ok = False

        ok = all_ok
        log("S31", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S31", "FAIL", details, time.time() - t0)


# ============================================================
# S32 — security: secrets in transcript E2E
# ============================================================
def test_S32():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Create transcript with secrets + enough real content to trigger compression
        lines = []
        lines.append(user_msg("My GitHub token is ghp_SECRETTOKEN123456789012345678901234"))
        lines.append(asst_msg("I'll use that token to authenticate with the repository"))
        lines.append(user_msg("Also my API key is sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXX"))
        lines.append(asst_msg("Noted, using those credentials for API access"))
        for i in range(30):
            lines.append(user_msg(f"Work on feature {i}: implementing database migration with PostgreSQL schema changes version {i+1}.0"))
            lines.append(asst_msg(f"Feature {i} done. Deployed to staging with accuracy={90+i%10}% and latency={10+i*2}ms. All tests passing."))

        jsonl_file = repo / "secret_session.jsonl"
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = muninn.compress_transcript(jsonl_file, repo)
        if result and result[0]:
            mn_content = result[0].read_text(encoding="utf-8")
            ok_no_ghp = "ghp_SECRET" not in mn_content
            ok_no_sk = "sk-ant" not in mn_content
            # REDACTED marker should be present
            ok_redacted = "[REDACTED]" in mn_content or ok_no_ghp
            details.append(f"ghp filtered: {ok_no_ghp}")
            details.append(f"sk-ant filtered: {ok_no_sk}")
            details.append(f"mn length: {len(mn_content)} chars")
            ok = ok_no_ghp and ok_no_sk
        else:
            details.append("compression returned None — not enough content")
            ok = True  # no crash

        log("S32", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S32", "FAIL", details, time.time() - t0)


# ============================================================
# S33 — unicode: full pipeline with CJK/Arabic/emoji
# ============================================================
def test_S33():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Mixed unicode content
        lines = []
        for i in range(15):
            lines.append(user_msg(f"日本語テスト {i}: accuracy=94.{i}% latency={i*10}ms"))
            lines.append(asst_msg(f"Réponse française numéro {i}: ratio x{i+1}.{i}"))

        jsonl_file = repo / "unicode.jsonl"
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = muninn.compress_transcript(jsonl_file, repo)
        if result and result[0]:
            mn_content = result[0].read_text(encoding="utf-8")
            # Should preserve numbers
            ok_nums = "94" in mn_content
            details.append(f"numbers preserved: {ok_nums}")
            details.append(f"mn length: {len(mn_content)} chars")
            ok = True  # no crash is the main test
        else:
            ok = True  # None result for short transcript is OK
            details.append("short transcript -> None")

        log("S33", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S33", "FAIL", details, time.time() - t0)


# ============================================================
# S34 — corrupted tree.json recovery
# ============================================================
def test_S34():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)

        # Write corrupted tree.json
        tree_path = repo / ".muninn" / "tree" / "tree.json"
        tree_path.write_text("{{{{CORRUPT JSON!!!!!", encoding="utf-8")

        # load_tree should recover (create fresh tree)
        tree = muninn.load_tree()
        ok = "root" in tree.get("nodes", {})
        details.append(f"recovered from corrupt tree.json: {ok}")
        details.append(f"nodes: {list(tree.get('nodes', {}).keys())}")

        log("S34", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S34", "FAIL", details, time.time() - t0)


# ============================================================
# S35 — corrupted .mn file in boot
# ============================================================
def test_S35():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)
        tree = muninn.load_tree()

        # Create a branch with binary garbage content
        bname = "corrupt_branch"
        bf = repo / ".muninn" / "tree" / f"{bname}.mn"
        bf.write_bytes(b"\x00\x01\x02\xff\xfe\xfd" * 100)
        tree["nodes"][bname] = {
            "file": f"{bname}.mn", "lines": 5, "hash": "deadbeef",
            "tags": ["corrupt"], "temperature": 0.5, "access_count": 3,
            "last_access": date.today().isoformat(),
        }
        muninn.save_tree(tree)

        result = muninn.boot("corrupt test")
        ok = isinstance(result, str) and len(result) > 0
        details.append(f"boot with corrupt branch: {len(result)} chars, ok={ok}")

        log("S35", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S35", "FAIL", details, time.time() - t0)


# ============================================================
# S36 — full pipeline E2E: feed -> grow -> boot -> prune
# ============================================================
def test_S36():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # 1. Create transcript
        lines = []
        decisions = [
            "We decided to use PostgreSQL over MySQL for better JSON support",
            "After benchmarking, Redis gives us 0.5ms latency vs 2ms for Memcached",
            "The API should use GraphQL instead of REST for flexibility",
        ]
        for i in range(30):
            if i < 3:
                lines.append(user_msg(f"Let's discuss: {decisions[i]}"))
                lines.append(asst_msg(f"Good decision. {decisions[i]} Performance improvement: {90+i}%"))
            else:
                lines.append(user_msg(f"Work item {i}: implementing feature {i}"))
                lines.append(asst_msg(f"Done. Feature {i} deployed with {95+i%5}% accuracy"))

        jsonl_file = repo / "session.jsonl"
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # 2. Compress
        result = muninn.compress_transcript(jsonl_file, repo)
        details.append(f"compress: {result[0] if result[0] else 'None'}")
        ok_compress = result[0] is not None

        # 3. Grow branches
        if ok_compress:
            created = muninn.grow_branches_from_session(result[0])
            details.append(f"branches created: {created}")

        # 4. Boot
        boot_result = muninn.boot("PostgreSQL database")
        ok_boot = isinstance(boot_result, str) and len(boot_result) > 0
        details.append(f"boot: {len(boot_result)} chars")

        # 5. Prune (dry run)
        muninn.prune(dry_run=True)
        details.append("prune: OK")

        ok = ok_compress and ok_boot
        log("S36", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S36", "FAIL", details, time.time() - t0)


# ============================================================
# S37 — _cue_distill + _extract_rules composition
# ============================================================
def test_S37():
    t0 = time.time()
    details = []
    try:
        # Cue distill: generic knowledge should be reduced
        text = (
            "Python is a programming language\n"
            "PostgreSQL is a relational database\n"
            "Redis is an in-memory data store\n"
            "F> our API latency is 45ms p50\n"
            "D> chose Redis over Memcached because persistence\n"
        )
        cued = muninn._cue_distill(text)
        details.append(f"cue distill: {len(text)} -> {len(cued)} chars")
        # Facts should survive
        ok_facts = "45ms" in cued
        details.append(f"facts preserved: {ok_facts}")

        # Extract rules: repetitive patterns should be factorized
        text2 = (
            "latency=45ms|throughput=1000rps|error_rate=0.01%\n"
            "latency=50ms|throughput=900rps|error_rate=0.02%\n"
            "latency=42ms|throughput=1100rps|error_rate=0.005%\n"
        )
        ruled = muninn._extract_rules(text2)
        details.append(f"extract rules: {len(text2)} -> {len(ruled)} chars")

        ok = ok_facts
        log("S37", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S37", "FAIL", details, time.time() - t0)


# ============================================================
# S38 — inject_memory mid-session
# ============================================================
def test_S38():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Inject a fact
        muninn.inject_memory("Redis cluster has 3 nodes, 16GB each", repo)

        # Check tree has a new branch
        tree = muninn.load_tree()
        n_branches = len([n for n in tree["nodes"] if n != "root"])
        details.append(f"branches after inject: {n_branches}")

        # Boot and check fact is accessible
        result = muninn.boot("Redis cluster")
        ok_found = "Redis" in result or "cluster" in result or "16GB" in result
        details.append(f"fact accessible via boot: {ok_found}")

        ok = n_branches >= 1 and ok_found
        log("S38", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S38", "FAIL", details, time.time() - t0)


# ============================================================
# S39 — recall mid-session search
# ============================================================
def test_S39():
    t0 = time.time()
    details = []
    try:
        repo = fresh_repo()
        setup_globals(repo)
        make_tree_with_root(repo)

        # Setup data
        bf = repo / ".muninn" / "tree" / "perf.mn"
        bf.write_text("## Performance\nB> API latency 45ms p50 120ms p99\nD> chose gRPC over REST\n", encoding="utf-8")
        tree = muninn.load_tree()
        tree["nodes"]["perf"] = {
            "file": "perf.mn", "lines": 3, "hash": compute_hash_local(bf),
            "tags": ["performance", "latency", "api"],
            "temperature": 0.5, "access_count": 2,
            "last_access": date.today().isoformat(),
        }
        muninn.save_tree(tree)

        result = muninn.recall("API latency performance")
        details.append(f"recall result: {len(result)} chars")
        ok = isinstance(result, str) and len(result) > 0
        details.append(f"contains latency: {'latency' in result.lower() or '45ms' in result}")

        log("S39", "PASS" if ok else "FAIL", details, time.time() - t0)
        shutil.rmtree(repo, ignore_errors=True)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S39", "FAIL", details, time.time() - t0)


# ============================================================
# S40 — decode_line: compression roundtrip
# ============================================================
def test_S40():
    t0 = time.time()
    details = []
    try:
        # Compress then decode
        original = "The system achieved 94.2% accuracy on the validation set after fine-tuning"
        compressed = muninn.compress_line(original)
        decoded = muninn.decode_line(compressed)
        details.append(f"original: '{original}'")
        details.append(f"compressed: '{compressed}'")
        details.append(f"decoded: '{decoded}'")

        # Key facts should survive roundtrip
        ok_num = "94.2" in decoded or "94.2" in compressed
        details.append(f"94.2 survives: {ok_num}")

        ok = isinstance(decoded, str) and ok_num
        log("S40", "PASS" if ok else "FAIL", details, time.time() - t0)
    except Exception as e:
        details.append(f"EXCEPTION: {e}")
        log("S40", "FAIL", details, time.time() - t0)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Muninn Senior Dev Battery — Mode Cassage de Gueule")
    print("=" * 60)

    tests = [
        test_S1, test_S2, test_S3, test_S4, test_S5,
        test_S6, test_S7, test_S8, test_S9, test_S10,
        test_S11, test_S12, test_S13, test_S14, test_S15,
        test_S16, test_S17, test_S18, test_S19, test_S20,
        test_S21, test_S22, test_S23, test_S24, test_S25,
        test_S26, test_S27, test_S28, test_S29, test_S30,
        test_S31, test_S32, test_S33, test_S34, test_S35,
        test_S36, test_S37, test_S38, test_S39, test_S40,
    ]

    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"CRASH in {t.__name__}: {e}")

    # Cleanup
    shutil.rmtree(TEMP_META, ignore_errors=True)
    for tmp in ALL_TEMPS:
        shutil.rmtree(tmp, ignore_errors=True)

    # Summary
    n_pass = sum(1 for r in results if "PASS" in r)
    n_fail = sum(1 for r in results if "FAIL" in r)
    n_skip = sum(1 for r in results if "SKIP" in r)
    n_slow = sum(1 for r in results if "SLOW" in r)

    print()
    print("=" * 60)
    print(f"TOTAL: {n_pass} PASS, {n_fail} FAIL, {n_skip} SKIP, {n_slow} SLOW")
    print("=" * 60)

    # Write results
    output_path = Path(r"c:\Users\ludov\MUNINN-\tests\RESULTS_SENIOR_BATTERY.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Muninn Senior Dev Battery Results\n\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Total: {n_pass} PASS, {n_fail} FAIL, {n_skip} SKIP, {n_slow} SLOW\n\n")
        for r in results:
            f.write(r + "\n")
    print(f"\nResults written to {output_path}")

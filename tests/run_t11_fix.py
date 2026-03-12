import sys, os, json, tempfile, shutil, time, re
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

TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))

from mycelium import Mycelium as _MycPatch
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")

import muninn

# Build a proper Claude Code JSONL transcript
msgs = []

def user_msg(text):
    return json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": text}]}})

def asst_msg(text):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})

def tool_use_msg(name, inp):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})

def tool_result_msg(content):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_result", "content": content}]}})

# Build 100 messages: 40 user, 40 assistant, 20 tool
for i in range(50):
    if i % 5 == 0:
        # Tool use + result pair (simulates reading a big file)
        big_output = "\n".join([f"    line {j}: def func_{j}(): return {j}" for j in range(210)])
        if i == 10:
            big_output += "\nD> decided to switch to PostgreSQL"
        msgs.append(tool_use_msg("Read", {"file_path": f"/tmp/file_{i}.py"}))
        msgs.append(tool_result_msg(big_output))
    elif i % 3 == 0:
        msgs.append(user_msg(f"The accuracy=94.2% is confirmed on the val set. Latency=15ms at p99. We decided to use Redis for caching. Version 3.1 deployed. Issue #4287 resolved."))
    elif i % 3 == 1:
        msgs.append(asst_msg(f"Let me analyze this for you. The accuracy=94.2% looks good and latency=15ms is within targets. We decided to use Redis for the session cache layer."))
    else:
        msgs.append(user_msg(f"Working on task {i}. The token ghp_ABC123DEF456GHI789JKL012MNO345PQR678 should be redacted. Accuracy=94.2% confirmed."))

jsonl_path = TEMP_REPO / "test_transcript.jsonl"
jsonl_path.write_text("\n".join(msgs), encoding="utf-8")

raw_text = jsonl_path.read_text(encoding="utf-8")
tokens_before = len(raw_text) // 4

t0 = time.time()
try:
    mn_path, sentiment = muninn.compress_transcript(jsonl_path, repo_path=TEMP_REPO)
    elapsed = time.time() - t0

    if mn_path is None:
        print("FAIL: mn_path is None - parse_transcript returned empty")
        print("Checking parse_transcript directly...")
        texts = muninn.parse_transcript(jsonl_path)
        print(f"  parse_transcript returned {len(texts)} texts")
        if texts:
            print(f"  first: {repr(texts[0][:100])}")
    else:
        mn_text = Path(mn_path).read_text(encoding="utf-8")
        tokens_after = len(mn_text) // 4
        ratio = tokens_before / max(tokens_after, 1)

        print(f"T1.1 - L0 Tool Output Strip")
        print(f"  ratio={ratio:.1f}x (before={tokens_before}, after={tokens_after})")
        print(f"  94.2 present: {'94.2' in mn_text}")
        print(f"  15 present: {'15' in mn_text}")
        print(f"  Redis present: {'redis' in mn_text.lower()}")
        print(f"  ghp_ absent (secret): {'ghp_' not in mn_text}")
        print(f"  PostgreSQL: {'postgresql' in mn_text.lower()}")
        print(f"  Time: {elapsed:.3f}s")

        ok = ratio >= 2.0 and "94.2" in mn_text and "15" in mn_text and "redis" in mn_text.lower() and "ghp_" not in mn_text
        print(f"  STATUS: {'PASS' if ok else 'FAIL'}")

        # Write fixed result
        result = f"""## T1.1 - L0 Tool Output Strip (RETEST)
- STATUS: {'PASS' if ok else 'FAIL'}
- ratio={ratio:.1f}x (before={tokens_before}, after={tokens_after})
- ratio >= 2.0: {ratio >= 2.0}
- 94.2 present: {'94.2' in mn_text}
- 15 present: {'15' in mn_text}
- Redis present: {'redis' in mn_text.lower()}
- ghp_ absent (secret filtered): {'ghp_' not in mn_text}
- PIEGE PostgreSQL from tool_result: {'PRESERVED' if 'postgresql' in mn_text.lower() else 'LOST (L0 strips tool_result content)'}
- TIME: {elapsed:.3f}s
"""
        with open(r"c:\Users\ludov\MUNINN-\tests\RESULTS_BATTERY_V4.md", "a", encoding="utf-8") as f:
            f.write("\n" + result)
        print("Result appended")

except Exception as e:
    import traceback; traceback.print_exc()
    print(f"FAIL: {e}")

shutil.rmtree(TEMP_REPO, ignore_errors=True)
shutil.rmtree(TEMP_META, ignore_errors=True)

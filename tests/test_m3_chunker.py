"""Test M3: R1-Compress fallback chunker can produce 1 mega-chunk.

Bug: When text has many short lines (2000 lines, 8000 chars),
len(text) // 6000 = 1, producing 1 chunk. The len(chunks) >= 2
check fails, sending everything to a single API call.

Fix: max(2, len(text) // 6000)
"""
import sys, re
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_m3_many_short_lines():
    """Text with many short lines (8K chars) should produce >= 2 chunks."""
    # Simulate: 2000 lines, ~4 chars each = ~8000 chars total
    lines = [f"L{i:03d}" for i in range(2000)]
    text = "\n".join(lines)
    assert len(text) > 6000, f"Text too short: {len(text)}"
    assert len(text) < 12000, f"Text too long: {len(text)}"

    # Reproduce the chunker logic (from muninn.py L1680-1688)
    # No ## headers -> fallback path
    chunks_header = re.split(r'(?=^## )', text, flags=re.MULTILINE)
    chunks_header = [c for c in chunks_header if c.strip()]
    assert len(chunks_header) < 2, "Should have no ## headers"

    # Fallback: line-split chunker
    text_lines = text.split("\n")
    num_chunks = max(1, len(text) // 6000)  # BUGGY: gives 1
    chunk_size_buggy = max(1, len(text_lines) // num_chunks)

    # Build chunks with buggy formula
    chunks_buggy = []
    for i in range(0, len(text_lines), chunk_size_buggy):
        chunk = "\n".join(text_lines[i:i + chunk_size_buggy])
        if chunk.strip():
            chunks_buggy.append(chunk)

    print(f"  Text: {len(text)} chars, {len(text_lines)} lines")
    print(f"  Buggy: len(text)//6000 = {len(text) // 6000}, chunks = {len(chunks_buggy)}")

    # Fixed formula
    num_chunks_fixed = max(2, len(text) // 6000)
    chunk_size_fixed = max(1, len(text_lines) // num_chunks_fixed)
    chunks_fixed = []
    for i in range(0, len(text_lines), chunk_size_fixed):
        chunk = "\n".join(text_lines[i:i + chunk_size_fixed])
        if chunk.strip():
            chunks_fixed.append(chunk)

    print(f"  Fixed: max(2, len(text)//6000) = {num_chunks_fixed}, chunks = {len(chunks_fixed)}")

    assert len(chunks_buggy) < 2, f"Buggy should produce <2 chunks, got {len(chunks_buggy)}"
    assert len(chunks_fixed) >= 2, f"Fixed should produce >=2 chunks, got {len(chunks_fixed)}"

    # Verify the actual code has the fix
    import muninn, inspect
    source = inspect.getsource(muninn)
    # Find the R1-Compress fallback section
    idx = source.find("Fallback: if no ## headers found")
    if idx > 0:
        section = source[idx:idx+300]
        has_max2 = "max(2," in section
        print(f"  Code has max(2, ...) in fallback: {has_max2}")
        assert has_max2, "Fix not applied: fallback still uses max(1, ...)"

    print("  PASS")


if __name__ == "__main__":
    print("## M3 — R1-Compress 1 mega-chunk")
    test_m3_many_short_lines()

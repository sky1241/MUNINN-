# Phase B Brick 13 — E2E Benchmark on Real Big File + BUG-105 Fix

Generated: 2026-04-11 (post-Phase-B brick 12 audit)
Tokenizer: tiktoken cl100k_base
L9 (LLM compress): DISABLED for honest measurement, deterministic, zero API cost

## Source

Real Sky transcript JSONL (Claude Code session log on MUNINN- project):

  Path:   c:/Users/ludov/.claude/projects/c--Users-ludov-MUNINN-/d00638e7-4405-43c3-b0c2-7523f0907c18.jsonl
  Size:   22 MB
  Chars:  23,359,701
  Tokens: 5,839,925 (BPE cl100k_base)
  Paragraph chunks (`\n\s*\n` split): **1**

The "1 chunk" is the critical detail. JSONL format = one JSON message
per line, no blank lines between them, no markdown paragraph breaks.
The whole 22MB file is ONE giant chunk from BudgetMem's perspective.

## BUG-105 (CRITICAL) — discovered during this benchmark

### Pre-fix behavior (catastrophic)

Brick 6 wired `_l12_budget_pass(text)` after secret redaction in
`compress_file()`. The helper called `_budget_select_impl(text, ...)`
which split on `\n\s*\n`, found 1 chunk for the whole 22MB file, then:

  - Marked the chunk as must-keep (it has fact spans)
  - Tried to fit it into the budget
  - Chunk size (5.8M tokens) >> budget (e.g. 1.5M tokens)
  - Phase 1 packing: chunk doesn't fit, skip
  - Phase 2 score-sorted: no other chunks to pick from
  - Returned: empty string ""
  - Rest of compress_file pipeline ran on "" -> 8 tokens output

Real measured (pre-fix):

| Mode             | Output tokens | Ratio | Notes |
|------------------|---------------|-------|-------|
| L0-L11 only      | 4,227,282     | x1.38 | Normal compression |
| L12 b=2,919,962  | **8**         | **x729,990** | **DESTRUCTION** |
| L12 b=1,459,981  | **8**         | **x729,990** | **DESTRUCTION** |
| L12 b=583,992    | **8**         | **x729,990** | **DESTRUCTION** |

This is not compression, it's **deletion**. A 22MB transcript becomes
8 tokens of garbage. Sky's primary use case (compressing his Claude
Code transcripts) was completely broken by Phase B brick 6 wiring.

### Root cause

`_l12_budget_pass()` did not check the chunk count before delegating
to `budget_select`. When a file has no `\n\n` paragraph separators
(JSONL, single-paragraph .md, log files, CSV), there's only 1 chunk
to select between, and BudgetMem either keeps it or drops it whole.
With any tight budget, it gets dropped.

### Fix (committed in this brick)

In both `engine/core/muninn_layers.py` and `muninn/muninn_layers.py`,
added a chunk-count guard at the top of `_l12_budget_pass()`:

```python
# BUG-105 safety: refuse to run on single-chunk input
chunks = _re.split(r"\n\s*\n", text)
if len(chunks) < 2:
    return text  # nothing to select between, return as-is
```

If the input has fewer than 2 paragraph chunks, L12 has nothing to
do — return identity. This protects every JSONL / log / single-paragraph
input from accidental destruction.

### Post-fix verification level 1 — direct helper test (real measurements)

| Mode             | Output chars | Ratio | Notes |
|------------------|--------------|-------|-------|
| L12 OFF          | 23,359,701   | x1.00 | Identity (no L12) |
| L12 b=1000       | 23,359,701   | x1.00 | **BUG-105 guard fires, identity** |

**BUG-105 fix saved 23,359,701 chars from being collapsed to 8 tokens.**

### Post-fix verification level 2 — full compress_file() pipeline

The above test exercises only `_l12_budget_pass()` directly. The
following table runs the FULL `compress_file()` pipeline end-to-end
on the same 22MB transcript, with L9 disabled. This is the level
that matters for production: it simulates what Sky's `muninn feed`
hook would do on this transcript.

Source: d00638e7-4405-43c3-b0c2-7523f0907c18.jsonl
        22 MB, 5,839,925 tokens, 1 paragraph chunk

| Mode                  | Output tokens | Ratio  | Time   | BUG-105 safe |
|-----------------------|---------------|--------|--------|--------------|
| L0-L11 only           |   4,227,282   | x1.381 | 162.2s | (n/a)        |
| L12 b=2,919,962 (50%) |   4,227,282   | x1.381 | 156.0s | **True**     |
| L12 b=1,459,981 (25%) |   4,227,282   | x1.381 | 148.9s | **True**     |
| L12 b=  583,992 (10%) |   4,227,282   | x1.381 | 149.7s | **True**     |

**All 4 modes produce IDENTICAL output (4,227,282 tokens).** The L12
helper bypasses on single-chunk input, so L0-L11 is the only thing
running. Pre-fix, the same table looked like this catastrophe:

| Mode                  | Output tokens | Ratio    | Damage |
|-----------------------|---------------|----------|--------|
| L0-L11 only           |   4,227,282   | x1.381   | none   |
| L12 b=2,919,962 (50%) |             8 | x729,990 | **4,227,274 tokens deleted** |
| L12 b=1,459,981 (25%) |             8 | x729,990 | **4,227,274 tokens deleted** |
| L12 b=  583,992 (10%) |             8 | x729,990 | **4,227,274 tokens deleted** |

L12 still functions normally on multi-chunk markdown input — verified
in the same test session with a 6-paragraph synthetic doc:
input 508 chars, output 80 chars (-84%), facts kept (abc1234, x4.5).

## Honest interpretation

**What Phase B brick 6 actually delivers in production:**

1. On **markdown files with paragraph breaks** (`\n\n` separators):
   L12 works as designed. PHASE_B_RESULTS.md numbers are valid:
   x8-x9 ratio at b=50% with zero regression.
   Examples: README.md, verbose_memory.md, sample_session.md, any
   .md file written by humans with normal paragraph spacing.

2. On **single-paragraph input** (JSONL transcripts, log files,
   CSV, single-cell text):
   L12 falls through to identity (BUG-105 guard). The user gets
   the same output as L0-L11 alone — no compression benefit from
   L12, but no destruction either. **Safe degradation.**

3. **The user must be told** if they're trying to use L12 on a
   single-chunk file and expecting compression. Currently the guard
   is silent. Future improvement: emit a warning to stderr the first
   time L12 is bypassed.

## How to reproduce

```bash
cd c:/Users/ludov/MUNINN-
python -c "
import sys, os
sys.path.insert(0, 'engine/core')
import muninn, muninn_layers as ml
ml._llm_compress = lambda text, context='': text  # disable L9
src = open('c:/Users/ludov/.claude/projects/c--Users-ludov-MUNINN-/d00638e7-4405-43c3-b0c2-7523f0907c18.jsonl', encoding='utf-8', errors='replace').read()
print(f'input chars: {len(src):,}')
os.environ['MUNINN_L12_BUDGET'] = '1000'
out = ml._l12_budget_pass(src)
print(f'output chars: {len(out):,}')
assert len(out) == len(src), 'BUG-105 fix broken!'
print('BUG-105 fix verified')
"
```

## Action items

- BUG-105: FIXED in this brick (chunk-count guard in _l12_budget_pass).
- Pin test: tests/test_brick13_l12_bug_105_jsonl.py — locks the
  identity-on-single-chunk contract.
- Future improvement: emit a one-time stderr warning when the BUG-105
  guard fires, so users know L12 is being skipped. Not critical.
- BUG-104 (fact-span detector too narrow at tight budgets) is still
  OPEN — separate from BUG-105.

## Real numbers summary (last cleansed run, post-fix)

```
SOURCE: d00638e7-4405-43c3-b0c2-7523f0907c18.jsonl (22 MB)
        5,839,925 tokens, 1 paragraph chunk

JSONL transcript: 5,839,925 tokens, 1 chunks (\n\n split)
L12 OFF:                   output 23,359,701 chars (must = input)
L12 budget=1000 (extreme): output 23,359,701 chars (must = input)

BUG-105 fix VERIFIED on real 22MB JSONL transcript:
  Single-chunk input (1 chunks) bypasses L12 -> identity
  Saved 23,359,701 chars from being collapsed to 8 tokens
```

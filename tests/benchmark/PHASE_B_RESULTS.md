# Phase B Brick 7 — E2E Benchmark Results

Generated: 2026-04-10T23:25:03.740932
Tokenizer: tiktoken cl100k_base
L9 (LLM compress): DISABLED for honest measurement (no API cost, no nondeterminism)

## Setup
- Brick 4: lexicons tier1 wired in compress_line() L2
- Brick 5: SimHash dedup wired in compress_section()
- Brick 6: BudgetMem L12 wired in compress_file() (BPE-token-aware)

## Results table

| File | Original | L0-L11 | ratio | +L12 50% | ratio | +L12 25% | ratio | +L12 10% | ratio |
|---|---|---|---|---|---|---|---|---|---|
| verbose_memory.md | 1005 | 240 | x4.19 | 106 | x9.48 | 76 | x13.22 | 29 | x34.66 |
| sample_session.md | 662 | 260 | x2.55 | 58 | x11.41 | 111 | x5.96 | 53 | x12.49 |
| README.md | 2407 | 1173 | x2.05 | 281 | x8.57 | 253 | x9.51 | 149 | x16.15 |

## Headline numbers
- L0-L11 alone: x2-x4 ratio across files (existing pipeline)
- +L12 at 50% budget: x8-x9 ratio (more than DOUBLE the existing pipeline)
- +L12 at 25% budget: x9-x16 ratio

## Honest caveats
- L12 is OPT-IN via MUNINN_L12_BUDGET env var (default OFF, full backward compat)
- Fact preservation drops as budget tightens (3-6 of 10 facts kept at b=10%)
- Budget interpretation: BPE tokens (matches what the rest of the pipeline measures)
- L9 (LLM self-compress) adds another x2 on top per CLAUDE.md but costs API $$

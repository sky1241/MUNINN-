# Phase B Brick 12 — Fact Recall Benchmark with L12 ON vs OFF

Generated: 2026-04-10 (post-Phase-B audit per Sky's "audit complet" demand)
Tokenizer: tiktoken cl100k_base
L9 (LLM compress): DISABLED for honest measurement

## Method

For each Muninn benchmark file, run the existing
`tests/benchmark/run_benchmark.py` fact-check (case-insensitive substring
match in compressed output) under 5 modes:

1. L12 OFF (no `MUNINN_L12_BUDGET` env var)
2. L12 budget = 2000 tokens (generous, ≥ original size for all 3 files)
3. L12 budget = 1000 tokens
4. L12 budget = 500 tokens
5. L12 budget = 250 tokens

Then compute the fact-recall delta vs L12 OFF for each mode.

## Real measurements

### verbose_memory.md (1005 tokens, 15 questions)

| Mode | Output tokens | Ratio | Facts recalled | Δ vs OFF |
|------|---------------|-------|----------------|----------|
| L12 OFF       |   240 | x4.19  | 15/15 (100.0%) |   —     |
| L12 b=2000    |   240 | x4.19  | 15/15 (100.0%) |  +0.0   |
| L12 b=1000    |   240 | x4.19  | 15/15 (100.0%) |  +0.0   |
| **L12 b=500** |   106 | x9.48  |  **6/15 (40.0%)** | **-60.0** |
| **L12 b=250** |    72 | x13.96 |  **5/15 (33.3%)** | **-66.7** |

### sample_session.md (662 tokens, 15 questions)

| Mode | Output tokens | Ratio | Facts recalled | Δ vs OFF |
|------|---------------|-------|----------------|----------|
| L12 OFF       |   260 | x2.55  | 12/15 (80.0%) |   —     |
| L12 b=2000    |   260 | x2.55  | 12/15 (80.0%) |  +0.0   |
| L12 b=1000    |   260 | x2.55  | 12/15 (80.0%) |  +0.0   |
| **L12 b=500** |   106 | x6.25  |  9/15 (60.0%) | **-20.0** |
| **L12 b=250** |   125 | x5.30  |  8/15 (53.3%) | **-26.7** |

### sample_compact.md (231 tokens, 10 questions)

| Mode | Output tokens | Ratio | Facts recalled | Δ vs OFF |
|------|---------------|-------|----------------|----------|
| L12 OFF       |   198 | x1.17  |  8/10 (80.0%) |   —     |
| L12 b=2000    |   198 | x1.17  |  8/10 (80.0%) |  +0.0   |
| L12 b=1000    |   198 | x1.17  |  8/10 (80.0%) |  +0.0   |
| L12 b=500     |   198 | x1.17  |  8/10 (80.0%) |  +0.0   |
| L12 b=250     |   198 | x1.17  |  8/10 (80.0%) |  +0.0   |

(sample_compact is too small for L12 to do anything — already under
budget. Treated as a no-op control test.)

## Honest interpretation

**The good news:**

L12 has **zero regression** when the budget is generous (≥ original
file size). For Muninn's actual use case where the budget is set to
the LLM context window (e.g. 100K tokens) and most files are smaller
than that, L12 is a safe additive layer. The PHASE_B_RESULTS.md
ratios that go up to x9 are real, BUT they were measured at budgets
that imply real chunk-dropping.

**The bad news:**

When the budget actually FORCES chunk dropping, L12's "must-keep fact
spans" hard rule is **not strong enough**:

- verbose_memory.md at b=500 loses 60 points of fact recall (100% → 40%)
- verbose_memory.md at b=250 loses 67 points of fact recall (100% → 33%)
- sample_session.md follows the same pattern with smaller swings

This is a real Phase B blind spot. The BudgetMem `has_fact_span()`
detector only matches a finite set of regex (ISO date, semver, git
hash, %, $money, JIRA ticket, URL). It does NOT detect:

- Function/class names (`compress_line`, `Mycelium`)
- File paths (`engine/core/muninn.py`)
- Verbose facts ("the test was created on Tuesday")
- Quoted strings, identifiers in backticks

When a chunk only has these "soft facts", BudgetMem treats it as
filler and drops it under tight budget.

## Recommended L12 budget for production

**Safe operating range:** `MUNINN_L12_BUDGET >= compress_file(...)
output size` — i.e. set the budget to your LLM context, not less.
At that point L12 is a no-op for most files but kicks in to cap the
worst-case extra-large outputs.

**Aggressive range (with eyes open):** `MUNINN_L12_BUDGET >= original
file size / 2` is the empirical threshold below which fact recall
starts to crater on technical files like `verbose_memory.md`.

**Forbidden range:** `MUNINN_L12_BUDGET < original / 4` produces
output that LOOKS compressed but has lost most of the load-bearing
information. Don't ship this without `verify_compression()` afterward.

## Action items

- BUG-104 (NEW): `has_fact_span()` should also detect function names,
  file paths, identifiers in backticks. See `BUGS.md` for details.
- L12 default behavior remains OFF (env var opt-in) — this is correct.
- The wire-pin test `test_brick6_wire_budget.py` already documents this
  limitation in `test_l12_documents_must_keep_limitation`.
- Future Claude reading this benchmark MUST cite BUG-104 before
  recommending L12 at tight budgets.

## How to reproduce

```bash
cd c:/Users/ludov/MUNINN-
python -c "
import sys, os, json
sys.path.insert(0, 'engine/core')
import muninn, muninn_layers as ml, tokenizer
from pathlib import Path
ml._llm_compress = lambda text, context='': text  # disable L9
def toks(t): return tokenizer.count_tokens(t)[0]
sample = Path('tests/benchmark/verbose_memory.md')
questions = json.loads(Path('tests/benchmark/questions_verbose.json').read_text())
for budget in (None, '2000', '1000', '500', '250'):
    if budget: os.environ['MUNINN_L12_BUDGET'] = budget
    else: os.environ.pop('MUNINN_L12_BUDGET', None)
    out = ml.compress_file(sample)
    n_facts = sum(1 for q in questions if q['answer'].lower() in out.lower())
    print(f'budget={budget!s:>5}: {toks(out):>4} tok, {n_facts}/15 facts')
"
```

Output should match the verbose_memory.md table above.

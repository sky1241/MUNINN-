# Muninn

> *Odin's raven of memory — the one that always comes back.*

LLM memory compression engine. Compresses session transcripts into dense `.mn` files and reloads them intelligently at next boot. 54 features, 11 compression layers (25 filters), 76 bugs squashed across 13 audit scans.

**Measured result**: x4.4 average on 230 files / 4 repos / 855K tokens (full pipeline, tiktoken). 92% fact retention (40-question benchmark).

## The Problem

LLMs have no persistent memory. Each session starts from zero. The only hack: a `MEMORY.md` file (~200 lines, ~3K tokens) injected into context. When context fills up, everything overflows and disappears.

## What Muninn Does

1. **Compresses** session transcripts through 11 layers (regex-only, zero dependencies)
2. **Learns** via a living co-occurrence network (mycelium) that grows with each session
3. **Retrieves** intelligently at boot using TF-IDF + Spreading Activation scoring
4. **Persists** across sessions via a fractal L-system tree with temperature-based pruning

## Architecture

```
                  BOOT (query)
                     |
              [session_index]     P22: search last 50 sessions
                     |
              [recall "query"]    P29: mid-session memory search
                     |
         +----------+----------+
      [root.mn]  [branches]  [last .mn]
         |           |           |
      always       TF-IDF +   auto-continue
      loaded       spreading     P23
                   activation
                     |
              +------+------+
           [mycelium]    [tree.json]
           co-occurrences   L-system
           fusions/decay    temperature
```

## Compression Pipeline

```
L0:  tool output strip (x3.5)     <- biggest win, 74% of transcript is noise
L1:  markdown strip                L2:  filler words
L3:  phrase compression            L4:  number shortening
L5:  universal rules               L6:  mycelium abbreviations (learned)
L7:  fact extraction               L10: cue distillation (Bartlett 1932)
L11: rule extraction (Kolmogorov)  L9:  LLM self-compress (Haiku, optional)
```

Additional filters: P24 causal preservation, P25 priority survival, P26/P27 dedup, P28 tics filter, Semantic RLE, NCD similarity, Bloom concept tracking, Sleep Consolidation, Spreading Activation.

- **L0-L7, L10-L11**: pure regex, zero dependencies, instant
- **L9**: `pip install anthropic` — Claude Haiku via API (x2 additional gain)

## Mycelium (Living Codebook)

Co-occurrence network that grows with each session:
- Concepts seen together → strong connection → fusion (learned abbreviation)
- Unused connections → decay → removal
- Federated across repos (P20b meta-mycelium at `~/.muninn/meta_mycelium.json`)
- Spreading Activation for semantic retrieval (Collins & Loftus 1975)

## Memory Tree (L-System)

Fractal tree with temperature-based lifecycle:
- **Root** (always loaded) → pointers to branches
- **Branches** (loaded if relevant via TF-IDF + activation + Park et al. 2023 scoring)
- **Temperature**: hot = frequently accessed, cold = forgotten and pruned
- **Sleep Consolidation**: cold branches merged before deletion (Wilson & McNaughton 1994)
- **Budget**: 30K tokens max loaded = 15% of context window

## Installation

```bash
# Minimum (L0-L7, zero external dependencies)
git clone https://github.com/sky1241/MUNINN-.git
cd MUNINN-
python engine/core/muninn.py bootstrap .

# Recommended: real token counting
pip install tiktoken

# Optional: L9 LLM self-compress
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
```

## Commands

```bash
muninn.py status              # Tree state + temperatures + budget
muninn.py boot [query]        # Load root + relevant branches + sessions
muninn.py recall "query"      # Mid-session memory search
muninn.py compress <file>     # Compress a markdown file
muninn.py feed <transcript>   # Feed mycelium + compress to .mn
muninn.py feed --history      # Catch up on all past transcripts
muninn.py feed --watch        # Poll-based feed (for scheduled tasks)
muninn.py bootstrap <repo>    # Cold start on a new repo
muninn.py prune               # Dry-run pruning (show what would happen)
muninn.py prune --force       # Actually prune cold/dead branches
muninn.py verify <file>       # Check compression quality (facts, ratio)
muninn.py ingest <folder>     # Compress reference docs into branches
muninn.py upgrade-hooks       # Update Claude Code hooks to latest format
```

## Claude Code Hooks

Bootstrap configures hooks automatically. Manual setup:

```json
{
  "hooks": {
    "PreCompact": [{ "type": "command", "command": "python engine/core/muninn.py feed --repo ." }],
    "SessionEnd": [{ "type": "command", "command": "python engine/core/muninn.py feed --repo ." }],
    "Stop": [{ "type": "command", "command": "python engine/core/muninn.py feed --trigger stop --repo ." }]
  }
}
```

A watchdog (`engine/core/watchdog.py`) runs every 15 minutes via Task Scheduler as a failsafe, feeding only transcripts that grew since last check.

## Benchmarks (tiktoken, March 2026)

### Per-file (full pipeline L1-L7+L10+L11+L9)

| Context | Ratio |
|---------|-------|
| HSBC Methodology (6K tok) | **x13.8** |
| HSBC Tree (5K tok) | **x11.4** |
| Deployment hardware (7K tok) | **x9.6** |
| Biomechanics gestures (7K tok) | **x7.8** |
| SOL.md full pipeline (20K chars) | **x7.7** |
| Wearable UX research (8K tok) | **x7.4** |

### Cross-repo (230 files, 4 repos)

| Repo | Files | Input | Output | Ratio |
|------|-------|-------|--------|-------|
| infernal-wheel | 58 | 535K tok | 87K tok | **x6.2** |
| HSBC-algo-genetic | 115 | 194K tok | 64K tok | **x3.0** |
| shazam-piano | 45 | 107K tok | 37K tok | **x2.9** |
| MUNINN- | 12 | 19K tok | 8K tok | **x2.3** |
| **Total** | **230** | **855K tok** | **196K tok** | **x4.4** |

API cost (Haiku): **$0.21** for 230 files.

### Factual retention

- 40 questions on compressed text → **37/40 correct (92%)**
- Method: pure text search, zero API, reproducible

## Theoretical Foundations

| # | Technique | Reference | Purpose |
|---|-----------|-----------|---------|
| 1 | Cue Distillation (L10) | Bartlett 1932, Rao & Ballard 1999 | Strip knowledge the LLM already has |
| 2 | Rule Extraction (L11) | Kolmogorov 1965 | Factor repeated patterns into rules |
| 3 | Sleep Consolidation | Wilson & McNaughton 1994 | Merge cold branches before deletion |
| 4 | Spreading Activation | Collins & Loftus 1975 | Semantic retrieval through co-occurrence network |
| 5 | Spaced Repetition | Settles & Meeder 2016 (Ebbinghaus 1885) | Branch lifecycle via forgetting curve p = 2^(-delta/h) |

## Repo Structure

```
engine/
  core/
    muninn.py          Main engine (4578 lines, 72 functions)
    mycelium.py        Co-occurrence network (1134 lines)
    tokenizer.py       tiktoken wrapper with fallback
    watchdog.py        Scheduled task runner (55 lines)
memory/
  tree.json            L-system tree metadata
  root.mn              Root memory (always loaded)
  b*.mn                Branch files
tests/
  benchmark/           Factual retention benchmark (40 questions)
  test_*.py            Unit tests
docs/
  LITERATURE.md        Literature review (15+ papers)
  BENCHMARK_*.md       Benchmark results
.muninn/               Local data (gitignored)
  mycelium.json        Co-occurrence network
  sessions/*.mn        Compressed transcripts
  session_index.json   Session catalog
  errors.json          Error/fix pairs (P18)
  hook_log.txt         Hook execution log
  watch_state.json     Watchdog poll state
  stop_dedup.json      Stop hook deduplication
.github/
  workflows/ci.yml     CI: tree integrity + engine tests + benchmark
```

## References

- Bartlett, F.C. (1932). *Remembering*. Cambridge University Press.
- Collins, A.M. & Loftus, E.F. (1975). A spreading-activation theory of semantic processing. *Psychological Review*, 82(6).
- Kolmogorov, A.N. (1965). Three approaches to the quantitative definition of information. *Problems of Information Transmission*, 1(1).
- Park, J.S. et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. *UIST '23*.
- Rao, R.P.N. & Ballard, D.H. (1999). Predictive coding in the visual cortex. *Nature Neuroscience*, 2(1).
- Wilson, M.A. & McNaughton, B.L. (1994). Reactivation of hippocampal ensemble memories during sleep. *Science*, 265(5172).
- Settles, B. & Meeder, B. (2016). A Trainable Spaced Repetition Model for Language Learning. *ACL 2016*, 1848-1858.
- Jiang, H. et al. (2023). LLMLingua: Compressing Prompts for Accelerated Inference. *EMNLP 2023*.

## License

MIT

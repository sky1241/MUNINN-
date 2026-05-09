# Muninn

> *Odin's raven of memory — the one that always comes back.*

LLM memory compression engine. Compresses session transcripts into dense `.mn` files and reloads them intelligently at next boot. 11 compression layers (L0–L7, L10, L11) + 2 opt-in (L9 LLM, L12 BudgetMem). **108 bugs fixed**, 1 OPEN (BUG-104) across 12+ audit passes (2026-03 → 2026-05).

**Measured results**:
- **Compression**: x4.4 average on 230 files / 4 repos / 855K tokens (full pipeline including L9 LLM compression, tiktoken-counted). 92% fact retention (40-question benchmark). Without L9, the regex-only pipeline measures ~x1.7.
- **Architecture**: Newman-Girvan **Q = 0.677** modularity over the import graph (Newman 2006 "good" threshold ≥ 0.30) — measured by `forge --modularity` across 368 source files / 110 import communities.
- **Tests**: 2356 tests run on every push in CI (Phase P3, May 2026).

## The Problem

LLMs have no persistent memory. Each session starts from zero. A common workaround is a hand-curated memory file (e.g. ~200 lines, ~3K tokens) injected into context. When context fills up, everything overflows and disappears.

## What Muninn Does

1. **Compresses** session transcripts through 11 base layers + 2 opt-in. L0–L7, L10, L11 are pure regex (no required dependency); L9 (optional) calls Anthropic Haiku for additional compression; L12 (opt-in via `MUNINN_L12_BUDGET`) selects the densest paragraphs to fit a token budget.
2. **Learns** via a living co-occurrence network (mycelium) that grows with each session.
3. **Retrieves** intelligently at boot using TF-IDF + Spreading Activation scoring (Collins & Loftus 1975).
4. **Persists** across sessions via a fractal L-system tree with temperature-based pruning.

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
                                   L12: BudgetMem chunk selection (opt-in)
```

(L8 was reserved during early design and intentionally left empty —
the layer numbering is non-contiguous.)

Additional filters: P24 causal preservation, P25 priority survival, P26/P27 dedup, P28 tics filter, Semantic RLE, NCD similarity, Bloom concept tracking, Sleep Consolidation, Spreading Activation.

- **L0–L7, L10–L11**: pure regex, zero dependencies, instant
- **L9**: `pip install anthropic` — Claude Haiku via API (x2 additional gain)
- **L12**: opt-in via `MUNINN_L12_BUDGET` env var (BUG-104 OPEN — see BUGS.md)

## Mycelium (Living Codebook)

Co-occurrence network that grows with each session:
- Concepts seen together → strong connection → fusion (learned abbreviation)
- Unused connections → decay → removal
- Federated across repos (P20b meta-mycelium at `~/.muninn/meta_mycelium.db`)
- Spreading Activation for semantic retrieval (Collins & Loftus 1975)

## Memory Tree (L-System)

Fractal tree with temperature-based lifecycle:
- **Root** (always loaded) → pointers to branches
- **Branches** (loaded if relevant via TF-IDF + activation + Park et al. 2023 scoring)
- **Temperature**: hot = frequently accessed, cold = forgotten and pruned
- **Sleep Consolidation**: cold branches merged before deletion (Wilson & McNaughton 1994)
- **Budget**: 30K tokens max loaded = 15% of context window

## Security (Phase P0/P0bis — May 2026)

All Muninn-managed files are protected with `0o600` (read/write owner only) on creation. On multi-user hosts, sibling users cannot read learned context, ciphertext, salts, or hook payloads.

Sites enforced (via `secure_perms()` from `engine/core/_secrets.py`):
- `~/.muninn/*.db` — mycelium SQLite, cube SQLite, translations cache
- `~/.muninn/sessions/*.mn` — compressed transcripts
- `~/.muninn/anomalies.jsonl` — cube anomaly tracker
- `~/.muninn/hook_errors.log` (+ rotated `.1`, `.2`, `.3` backups via `_SecureRotatingFileHandler`)
- `engine/core/vault.py` — salt + verify hash + ciphertext + ephemeral plaintext (15 sites)
- `.claude/hooks/*.py` (generated) — `0o700` (owner exec only)
- `memory/tree.json`, `memory/root.mn`, `memory/b*.mn` — atomic writes

This addresses the production-grade requirement for tech-org installs on shared servers (commits `607f1a7`, `21b4cb3`, `008f9c7`).

## Installation

```bash
# From source (recommended — package not yet on PyPI)
git clone https://github.com/sky1241/MUNINN-.git
cd MUNINN-
pip install -c constraints.txt -e .          # core (L0–L7, zero deps)
pip install -c constraints.txt -e '.[all]'   # + tiktoken + anthropic (L9 API)
python3 engine/core/muninn.py bootstrap .

# Optional: L9 LLM self-compress
export ANTHROPIC_API_KEY=sk-...
```

For reproducible builds, always use `-c constraints.txt`. The constraints file pins `tiktoken==0.12.0` and `anthropic==0.96.0` (versions used in CI).

### Optional: forge-shield (quality analysis)

`forge-shield` is the regression-shield + predictive-analytics tool extracted from MUNINN- on 2026-05-07 and now maintained as its own repo (`sky1241/forge`). MUNINN- can consume its outputs for the cube heatmap UX (Phase 4.6, planned).

```bash
# forge-shield 1.1.0 is not on PyPI yet — install from git tag:
pip install 'git+https://github.com/sky1241/forge.git@v1.1.1'

# Or via the [quality] extra (will use PyPI once 1.1.x lands there):
pip install -c constraints.txt -e '.[quality]'
```

Sub-commands available:

| Command | Purpose |
|---------|---------|
| `forge --modularity` | Newman-Girvan Q (0.677 measured on MUNINN-) |
| `forge --carmack` | Composite risk: Kalman + Wavelet + Kaplan-Meier + Coupling + Churn |
| `forge --locate` | Ochiai SBFL — fault localization on the failing-tests path |
| `forge --predict` | Churn-based defect prediction (Nagappan 2005 style) |
| `forge --anomaly` | z-score outlier detection over the file activity matrix |
| `forge --fast-deep` | Transitive impact tests (Bazel/Buck-style import closure) |
| `forge --gen-props` | Hypothesis property test generation |
| `forge --mutate` / `--incremental-mutate` | libcst AST-aware mutation testing |

## Commands

27 CLI subcommands exposed by `engine/core/muninn.py`:

```bash
# Memory lifecycle
muninn boot [query]        # Load root + relevant branches + sessions
muninn status              # Tree state + temperatures + budget
muninn recall "query"      # Mid-session memory search
muninn compress <file>     # Compress a markdown file
muninn decode <file>       # Decompress a .mn file (debugging)
muninn read <node>         # Read a tree node (root or b*)

# Tree management
muninn tree                # Visualize the tree
muninn init                # Create empty tree.json
muninn bootstrap <repo>    # Cold start on a new repo
muninn ingest <folder>     # Compress reference docs into branches
muninn prune               # Dry-run pruning
muninn prune --force       # Actually prune cold/dead branches
muninn inject <text>       # Manually inject content into the tree
muninn scan                # Scan repo + emit neuron map JSON

# Mycelium feeding
muninn feed <transcript>   # Feed mycelium + compress to .mn
muninn feed --history      # Catch up on all past transcripts
muninn feed --watch        # Poll-based feed (for scheduled tasks)
muninn bridge              # Manual bridge invocation

# Diagnostics
muninn verify <file>       # Check compression quality (facts, ratio)
muninn diagnose            # Full pipeline self-check
muninn doctor              # Pre-flight: Python/SQLite/.muninn/tree/db/log
muninn upgrade-hooks       # Update Claude Code hooks to latest format

# Cube (B33 destruction/reconstruction)
muninn trip                # Trigger a cube cycle
muninn think               # Cube reflective pass
muninn quarantine <id>     # Quarantine a suspected cube

# Security
muninn lock                # Encrypt .muninn/ at rest (AES-256-GCM)
muninn unlock              # Decrypt with password
muninn rekey               # Re-encrypt with new password
muninn scrub <path>        # Scrub secrets from a file
muninn purge-secrets       # Repo-wide secret scrubbing
muninn sync                # Sync to backend (TLS or git)
```

## Claude Code Hooks

Bootstrap configures hooks automatically. **9 hooks** are installed under `.claude/hooks/`:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `bridge_hook.py` | PreCompact / SessionEnd / Stop | Feed transcripts into mycelium + compress |
| `subagent_start_hook.py` | SubagentStart | Track subagent invocations |
| `post_tool_failure_hook.py` | PostToolUseFailure | Log failures to audit trail |
| `post_tool_use_edit_log.py` | PostToolUse (Edit) | Log every Edit tool use |
| `pre_tool_use_bash_destructive.py` | PreToolUse (Bash) | Block destructive shell commands without confirmation |
| `pre_tool_use_bash_secrets.py` | PreToolUse (Bash) | Detect secret leakage in bash commands |
| `pre_tool_use_edit_hardcode.py` | PreToolUse (Edit) | Flag hardcoded paths in code edits |
| `notification_audit_hook.py` | Notification | Persist Claude Code notifications |
| `config_change_hook.py` | (manual / cron) | Detect drift in `.claude/settings.json` |

Manual setup example:

```json
{
  "hooks": {
    "PreCompact": [{ "type": "command", "command": "python3 engine/core/muninn.py feed --repo ." }],
    "SessionEnd": [{ "type": "command", "command": "python3 engine/core/muninn.py feed --repo ." }],
    "Stop": [{ "type": "command", "command": "python3 engine/core/muninn.py feed --trigger stop --repo ." }]
  }
}
```

A watchdog (`engine/core/watchdog.py`) runs every 15 minutes via Task Scheduler as a failsafe, feeding only transcripts that grew since last check.

## Continuous Integration

`.github/workflows/ci.yml` runs on every push and every PR to `main`:
1. Tree integrity check (no node exceeds its `max_lines` budget)
2. Engine smoke commands (`status`, `prune`, `compress`, `boot`)
3. Mycelium smoke commands (`simulate`, `bootstrap`)
4. **Pytest suite — 2356 tests** (excludes Qt UI tests + 2 known-debt deselects)
5. Factual retention benchmark (P35)
6. Feed transcript parsing test

CI Python: 3.13. forge-shield is installed from `git+https://github.com/sky1241/forge.git@v1.1.1` (PyPI 1.1.x not yet released).

Latest run: `success` (2356 passed, 0 failed in 69s — commit `573555c`).

## Recent Fixes (May 2026)

| Phase | Commit | Fix |
|-------|--------|-----|
| P3 | `bf3858a`, `fdc343d`, `a782800` | CI pytest wiring — 2356 tests on every push (was 0) |
| F4 | `6ee1458` | conftest preload — 22 BUG-091 dual-tree skips killed |
| EX5 | `7a663c5` | `_sleep_consolidate` dead-path in `feed_from_hook` (Sky-found bug) |
| P0 | `3b70836` | `chmod 0o600` on Muninn-managed sensitive files (9 sites) |
| P0bis-1 | `607f1a7` | `vault.py` 15 sites secure_perms (CRITICAL crypto leak fix) |
| P0bis-2 | `21b4cb3` | `_engine.py` + `muninn.py` 11 sites mirror (root.mn, hooks generated) |
| P0bis-3 | `008f9c7` | `_SecureRotatingFileHandler` — chmod 0o600 on rotated `.1/.2/.3` backups |
| P4 | `8a9b7be` | `forge.gen_props` split 212L → 96L (brick20 invariant restored) |
| P4.1–4.4 | `0d88508`, `d85d12c`, `2770aa0`, `573555c` | forge-shield 1.1.0 wired as optional dep |

See [docs/BATTLE_PLAN_2026-05-09.md](docs/BATTLE_PLAN_2026-05-09.md) for detailed timeline.

## Benchmarks (tiktoken, March 2026)

### Per-file (full pipeline L1–L7 + L10 + L11 + L9)

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

### Architecture metrics (forge-shield 1.1.0, May 2026)

- **Q-modularity** (Newman-Girvan over import graph): **0.677** — "good" per Newman 2006 (≥ 0.30 threshold), 368 files in 110 import communities.
- **Top risk file** (`forge --carmack`): `engine/core/muninn.py` 0.558 (Kalman 4.47, coupling 1.0, 101 historical bugfixes / 221 commits).
- **5 anomaly z-score outliers** (`forge --anomaly`): all engine/core hubs (`muninn`, `mycelium`, `cube`, `cube_providers`, `mycelium_db`) — expected for a hub-spoke topology.

## Theoretical Foundations

| # | Technique | Reference | Purpose |
|---|-----------|-----------|---------|
| 1 | Cue Distillation (L10) | Bartlett 1932, Rao & Ballard 1999 | Strip knowledge the LLM already has |
| 2 | Rule Extraction (L11) | Kolmogorov 1965 | Factor repeated patterns into rules |
| 3 | Sleep Consolidation | Wilson & McNaughton 1994 | Merge cold branches before deletion |
| 4 | Spreading Activation | Collins & Loftus 1975 | Semantic retrieval through co-occurrence network |
| 5 | Spaced Repetition | Settles & Meeder 2016 (Ebbinghaus 1885) | Branch lifecycle via forgetting curve `p = 2^(-Δ/h)` |
| 6 | Q-modularity | Newman & Girvan 2004, Blondel et al. 2008 | Architectural health (via forge-shield) |
| 7 | Ochiai SBFL | Abreu et al. 2007 | Fault localization (via forge-shield) |

## Repo Structure

```
engine/
  core/
    muninn.py             Main CLI (2104 lines, 27 subcommands)
    muninn_tree.py        L-system tree + sleep consolidation (3913 lines)
    muninn_layers.py      11 compression layers + L9/L12 (1547 lines)
    muninn_feed.py        Hook → mycelium feeding pipeline
    mycelium.py           Co-occurrence network + spreading activation (3163 lines)
    mycelium_db.py        SQLite backend + WAL + ConceptTranslator (1401 lines)
    cube.py               Cube engine — destruction/reconstruction (1558 lines)
    cube_analysis.py      B33 anomaly tracking + carmack scoring (1915 lines)
    cube_providers.py     Cube I/O providers (Ollama, mock, …)
    vault.py              AES-256-GCM at-rest encryption (551 lines)
    forge.py              Internal forge fallback (deprecated — use forge-shield)
    tokenizer.py          tiktoken wrapper with regex fallback
    watchdog.py           Scheduled task runner (15-min poll failsafe)
    sync_backend.py       Sync over git or TLS
    sync_tls.py           mTLS transport (TLSv1.3)
    _secrets.py           secure_perms() + redact_secrets_text()
    _hook_logger.py       _SecureRotatingFileHandler (rotated logs in 0o600)
muninn/                   pip-installable package (mirrors engine/core)
  ...                     dual-tree shims + copies (BUG-091 graduated cleanup)
forge.py                  Legacy CLI entry point (deprecated — use `forge` PyPI binary)
memory/
  tree.json               L-system tree (self-repo legacy)
  root.mn                 Root memory (always loaded)
  b*.mn                   Branch files
tests/
  benchmark/              Factual retention benchmark (40 questions)
  test_*.py               223 test files (chunks, tiers, props, audits)
  test_props_*.py         Hypothesis property tests (regenerated by forge --gen-props)
docs/
  LITERATURE.md           Literature review (15+ papers)
  BENCHMARK_*.md          Benchmark results
  SYSTEM_MAP.md           Visual architecture map
  TIER1_SUMMARY.md        Tier 1 upgrade summary
  TIER2_SUMMARY.md        Tier 2 upgrade summary
  TIER3_PLAN.md           Tier 3 plan (ongoing)
  BATTLE_PLAN_*.md        Per-day battle plans
  BRANCHEMENT_FORGE_v1.1.1.md  forge-shield branchement plan
  ANTI_BULLSHIT_BATTLE_PLAN.md RULE 4 contract
CHANGELOG.md              Project changelog
BUGS.md                   Bug tracker (108 fixed, 1 OPEN)
.muninn/                  Local data (gitignored, chmod 0o600)
  mycelium.db             Co-occurrence network (SQLite)
  cube.db                 Cube state (SQLite)
  tree/                   L-system tree (operational)
  sessions/*.mn           Compressed transcripts
  session_index.json      Session catalog
  errors.json             Error/fix pairs (P18)
  anomalies.jsonl         Cube anomaly stream
  hook_errors.log[.1-3]   Hook error rotation (RotatingFileHandler)
.claude/
  hooks/*.py              9 hooks (see "Claude Code Hooks" section)
  settings.json           Claude Code config
.github/
  workflows/ci.yml        CI: tree + smoke + 2356 pytest on every push
constraints.txt           Pinned versions for reproducible builds
pyproject.toml            Package metadata + optional extras [tokens] [llm] [quality] [all]
```

## References

- Abreu, R., Zoeteweij, P. & Van Gemund, A.J.C. (2007). On the accuracy of spectrum-based fault localization. *TAICPART-MUTATION 2007*.
- Bartlett, F.C. (1932). *Remembering*. Cambridge University Press.
- Blondel, V.D. et al. (2008). Fast unfolding of communities in large networks. *J. Stat. Mech.*
- Collins, A.M. & Loftus, E.F. (1975). A spreading-activation theory of semantic processing. *Psychological Review*, 82(6).
- Jiang, H. et al. (2023). LLMLingua: Compressing Prompts for Accelerated Inference. *EMNLP 2023*.
- Kolmogorov, A.N. (1965). Three approaches to the quantitative definition of information. *Problems of Information Transmission*, 1(1).
- Newman, M.E.J. & Girvan, M. (2004). Finding and evaluating community structure in networks. *Physical Review E*, 69(2).
- Park, J.S. et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. *UIST '23*.
- Rao, R.P.N. & Ballard, D.H. (1999). Predictive coding in the visual cortex. *Nature Neuroscience*, 2(1).
- Settles, B. & Meeder, B. (2016). A Trainable Spaced Repetition Model for Language Learning. *ACL 2016*, 1848–1858.
- Wilson, M.A. & McNaughton, B.L. (1994). Reactivation of hippocampal ensemble memories during sleep. *Science*, 265(5172).

## License

MIT

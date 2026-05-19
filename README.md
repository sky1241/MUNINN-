# Muninn

> *Odin's raven of memory — the one that always comes back.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.1.0-green.svg)](https://github.com/sky1241/MUNINN-/releases)
[![Tests](https://img.shields.io/badge/tests-2849%20passing-brightgreen.svg)](#continuous-integration)
[![Modularity](https://img.shields.io/badge/Q--modularity-0.670-blue.svg)](#architecture-metrics-forge-shield-212-may-2026)

**The persistent memory layer LLM agents have been missing.** Muninn compresses every Claude Code session into a dense `.mn` file, learns a co-occurrence network across sessions (mycelium), and rehydrates the right context at next boot — automatically, with zero manual curation.

**Headline numbers** :

| Metric | Value | Method |
|---|---|---|
| Compression ratio | **x4.4** average (855K → 196K tokens) | full pipeline, 230 files / 4 repos, tiktoken-counted |
| Without LLM layer | **x1.7** (regex-only, zero API) | L0–L7 + L10 + L11 |
| Fact retention | **92%** (37/40 questions correct) | reproducible text-search benchmark |
| Architecture quality | **Q = 0.670** Newman-Girvan modularity | `forge --modularity` (≥ 0.30 = "good") |
| CI gate | **2849 tests** on every push, 5× consecutive green | GitHub Actions, Python 3.13 |
| Bugs status | **121 RESOLVED, 0 OPEN** | 12+ audit passes (2026-03 → 2026-05) |
| Multilingual offline | **1336 FR→EN entries** shipped in wheel | MIT-curated + CC0 Wikidata, no API key needed |

**License**: MIT. The wheel ships only MIT-curated content + CC0 public-domain data — sellable, relicensable, no Share-Alike contamination.

## The Problem

LLMs have no persistent memory. Each session starts from zero. The common workaround — a hand-curated ~200-line memory file (~3K tokens) injected into context — buckles the moment context fills up. Everything overflows and disappears. Worse: the user has to maintain the file by hand, knowing what to keep and what to discard. That's not a memory system. That's a Post-it.

## What Muninn Does

Four pillars, all running automatically once you `muninn-mem init` your repo:

1. **Compresses** — 11 regex layers + 2 opt-in LLM/budget layers (L0 alone strips 74% of a typical transcript; full pipeline averages x4.4 across 230 real files).
2. **Learns** — a living co-occurrence network (the *mycelium*) grows with each session. Strong pairs fuse into learned abbreviations; weak ones decay. Federated across all your repos via a shared meta-mycelium (7.5M edges on the maintainer's box).
3. **Retrieves** — TF-IDF + Spreading Activation (Collins & Loftus 1975) ranks branches at boot; dual-mycelium router (local + meta) auto-calibrates its threshold on your data after ~30 queries.
4. **Persists** — fractal L-system tree with temperature-based pruning + Sleep Consolidation (Wilson & McNaughton 1994). Cold branches consolidate before deletion. Nothing important is silently lost.

**No fine-tuning. No proprietary model. No API key required for the core path.** You install one wheel, run two commands, and Claude Code starts remembering — across sessions, across repos, across operating systems.

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
              |
              ConceptTranslator (K.1)
              FR→EN offline 1336 entries
              (MIT-curated + CC0 Wikidata)
```

## Compression Pipeline

```
L0:  tool output strip (x3.5)     <- biggest win, 74% of transcript is noise
L1:  markdown strip                L2:  filler words
L3:  phrase compression            L4:  number shortening
L5:  universal rules               L6:  mycelium abbreviations (learned)
L7:  fact extraction               L10: cue distillation (Bartlett 1932)
L11: rule extraction (Kolmogorov)  L9:  LLM self-compress (Haiku, optional)
                                   L12: BudgetMem chunk selection (default-on,
                                        16000 tokens, MUNINN_L12_BUDGET=0 to disable)
```

(L8 was reserved during early design and intentionally left empty — the layer numbering is non-contiguous.)

Additional filters: P24 causal preservation, P25 priority survival, P26/P27 dedup, P28 tics filter, Semantic RLE, NCD similarity, Bloom concept tracking, Sleep Consolidation, Spreading Activation, universal degree-based stopword filter (G.1, language-agnostic).

- **L0–L7, L10–L11**: pure regex, zero dependencies, instant
- **L9**: `pip install anthropic` — Claude Haiku via API (x2 additional gain)
- **L12**: BudgetMem default-on with 16000-token budget (set `MUNINN_L12_BUDGET=0` to disable, BUG-104 fixed 2026-05-10)

## Mycelium (Living Codebook)

Co-occurrence network that grows with each session:
- Concepts seen together → strong connection → fusion (learned abbreviation)
- Unused connections → decay → removal
- **Federated** across repos (P20b meta-mycelium at `~/.muninn/meta_mycelium.db` — currently 64 236 concepts / 7.5M edges on the author's box)
- **Spreading Activation** for semantic retrieval (Collins & Loftus 1975)
- **Dual-mycelium router** (MCP chunk B.3 + C.0 auto-calibration) routes recall queries between local and meta based on local strength, with per-client adaptive threshold tuned over 30+ samples
- **Universal degree-based stopword filter** (G.1) drops the top 5% highest-degree concepts at query-time — language-agnostic, no hardcoded word list

## Memory Tree (L-System)

Fractal tree with temperature-based lifecycle:
- **Root** (always loaded) → pointers to branches
- **Branches** (loaded if relevant via TF-IDF + activation + Park et al. 2023 scoring)
- **Temperature**: hot = frequently accessed, cold = forgotten and pruned
- **Sleep Consolidation**: cold branches merged before deletion (Wilson & McNaughton 1994). Opt-in via `muninn-mem prune --include-dreams` (H.3).
- **Budget**: 30K tokens max loaded = 15% of context window

## Security (Phase P0/P0bis — May 2026)

All Muninn-managed files are protected with `0o600` (read/write owner only) on creation. On multi-user hosts, sibling users cannot read learned context, ciphertext, salts, or hook payloads.

Sites enforced (via `secure_perms()` from `engine/core/_secrets.py`):
- `~/.muninn/*.db` — mycelium SQLite, cube SQLite, translations cache
- `~/.muninn/sessions/*.mn` — compressed transcripts
- `~/.muninn/anomalies.jsonl` — cube anomaly tracker
- `~/.muninn/hook_errors.log` (+ rotated `.1`, `.2`, `.3` backups via `_SecureRotatingFileHandler`)
- `engine/core/vault.py` — salt + verify hash + ciphertext + ephemeral plaintext (15 sites). AES-256-GCM lock/unlock commands shipped but auto-lock kept dormant intentional (opt-in only).
- `.claude/hooks/*.py` (generated) — `0o700` (owner exec only)
- `memory/tree.json`, `memory/root.mn`, `memory/b*.mn` — atomic writes

### Defensive runtime hooks (since I.5, 2026-05-13)

`muninn-mem init` automatically registers 3 `PreToolUse` hooks in `.claude/settings.local.json` to enforce CLAUDE.md RULE 1/2/3 at runtime, not just by prompt text:
- `pre_tool_use_bash_destructive.py` — blocks destructive shell patterns (recursive deletes, force-pushes, DROP TABLE, etc.)
- `pre_tool_use_bash_secrets.py` — scrubs secret-shaped strings from bash arguments
- `pre_tool_use_edit_hardcode.py` — flags hardcoded absolute paths in code edits

This addresses the production-grade requirement for tech-org installs on shared servers (commits `607f1a7`, `21b4cb3`, `008f9c7`, plus runtime enforcement via I.5 `5dad754`).

### Publishing credentials — `~/.pypirc` discipline

When publishing to PyPI / TestPyPI, your authentication token lives in `~/.pypirc`. **Never commit this file**, anywhere, ever — a PyPI token is a publishing credential with full write access to your namespace.

Apply the same hygiene the maintainer uses:

```bash
# 1) Restrict file mode to owner-only
chmod 600 ~/.pypirc

# 2) Add it to your global git ignore
echo '.pypirc' >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global
```

Idempotent — safe to re-run.

## Quickstart — Use Muninn on your own repo

For the impatient : **see [`docs/QUICKSTART.md`](docs/QUICKSTART.md)** — 10 numbered steps from `git clone` to your first `mycelium_recall_local` call from Claude. Tested against a vanilla Linux box, ~5 min if pip is configured.

In two lines :

```bash
pip install -e "<PATH_TO_MUNINN>[mcp,tokens,ui]"
cd <YOUR_REPO> && muninn-mem init && muninn-mem bootstrap . && muninn-mem doctor
```

Then add the `muninn` MCP server to `~/.claude.json` and Claude will have **10 tools** to actively query your project's memory during generation : `mycelium_recall_local`, `mycelium_recall_meta`, `mycelium_recall(scope="auto")`, `tree_get_root`, `tree_get_branch`, `tree_list_branches`, `bugs_list`, `bugs_get`, `runbook_list_sections`, `runbook_get`. Full cheatsheet in [`docs/MCP_SETUP.md`](docs/MCP_SETUP.md).

**What happens automatically once installed (no further action required from you)** :

- **SessionStart hook** boots Claude with the current `root.mn` + 5 most recently-modified branches each new session.
- **SessionEnd hook** flushes the local mycelium into the shared `~/.muninn/meta_mycelium.db` (federation across repos) ; guarded with a 60s budget so it never blocks session shutdown.
- **PreCompact hook** compresses the transcript into a `.mn` file before Claude's context window resets.
- **PreToolUse hooks** (since I.5) block destructive bash commands, secret leaks, and hardcoded paths *before* they execute.
- **(Linux only)** Weekly cron timer prunes stale branches every Sunday 04:00 — see Step 8 of the Quickstart. Add `--include-dreams` for opt-in Sleep Consolidation.
- **(Phase B live)** MCP server exposes the **10 read-only memory tools** to Claude during generation. Auto-calibrates the dual-mycelium router threshold on your data after ~30 queries (chunk C.0).

## Installation

```bash
# From source (recommended — package not yet on PyPI prod, TestPyPI 1.0.3 live)
git clone https://github.com/sky1241/MUNINN-.git
cd MUNINN-
pip install -c constraints.txt -e .              # core (L0–L7, zero deps)
pip install -c constraints.txt -e '.[all]'       # + tiktoken + anthropic + mcp + forge-shield + PyQt6
python3 -m muninn._engine bootstrap .

# Optional: L9 LLM self-compress (the only place you still need an API key)
export ANTHROPIC_API_KEY=sk-...
```

For reproducible builds, always use `-c constraints.txt`. The constraints file pins `tiktoken==0.12.0`, `anthropic==0.100.0`, `forge-shield==2.1.2`, `mcp==1.27.1`, `PyQt6==6.10.0` (versions used in CI).

### Available extras
- `tokens` → tiktoken (for L4/L12 budget accounting)
- `llm` → anthropic (for L9 LLM compression)
- `quality` → forge-shield (architecture/risk analysis)
- `mcp` → MCP server runtime (Claude Code integration)
- `ui` → PyQt6 desktop UI (`muninn-ui` console script)
- `all` → everything above

## Optional: forge-shield (quality analysis)

`forge-shield` is the regression-shield + predictive-analytics tool extracted from MUNINN- on 2026-05-07 and now maintained as its own repo ([sky1241/forge](https://github.com/sky1241/forge)). Available on PyPI since v1.3.0; current stable **2.1.2** adds `--shield`, `--bisect`, `--snapshot`, and full BUGS.md round-trip with `--add` / `--close BUG-ID`.

```bash
# Install from PyPI
pip install forge-shield==2.1.2

# Or via the [quality] extra
pip install -c constraints.txt -e '.[quality]'
```

Sub-commands available:

| Command | Purpose |
|---|---|
| `forge --modularity` | Newman-Girvan Q (0.670 measured on MUNINN-) |
| `forge --carmack` | Composite risk: Kalman + Wavelet + Kaplan-Meier + Coupling + Churn |
| `forge --locate` | Ochiai SBFL — fault localization on the failing-tests path |
| `forge --predict` | Churn-based defect prediction (Nagappan 2005 style) |
| `forge --anomaly` | z-score outlier detection over the file activity matrix |
| `forge --shield` | Orchestration: carmack → gen_props → fast_deep (2.x) |
| `forge --bisect` | Bisect-style regression hunt across recent commits (2.x) |
| `forge --snapshot` | Snapshot-restore for forge state (2.x) |
| `forge --fast-deep` | Transitive impact tests (Bazel/Buck-style import closure) |
| `forge --gen-props` | Hypothesis property test generation |
| `forge --mutate` / `--incremental-mutate` | libcst AST-aware mutation testing |

## Commands

**32 CLI subcommands** exposed by `engine/core/muninn.py` (binary: `muninn-mem`, renamed from `muninn` in chunk E.3 to avoid PyPI collisions). Plus the standalone `muninn-ui` console script for the PyQt6 desktop:

```bash
# Memory lifecycle
muninn-mem boot [query]                 # Load root + relevant branches + sessions
muninn-mem status                       # Tree state + temperatures + budget + mycelium growth_stats
muninn-mem recall "query"               # Mid-session memory search
muninn-mem compress <file>              # Compress a markdown file
muninn-mem decode <file>                # Decompress a .mn file (debugging)
muninn-mem read <node>                  # Read a tree node (root or b*)

# Tree management
muninn-mem tree                         # Visualize the tree
muninn-mem init                         # Create empty tree.json + install hooks (incl. 3 defensive)
muninn-mem uninstall [--purge-data]     # Clean removal — hooks + cron, keeps .muninn/ by default
muninn-mem bootstrap <repo>             # Cold start on a new repo
muninn-mem ingest <folder>              # Compress reference docs into branches
muninn-mem prune                        # Dry-run pruning
muninn-mem prune --force                # Actually prune cold/dead branches
muninn-mem prune --include-dreams       # H.3: also run Sleep Consolidation (insights.json)
muninn-mem inject <text>                # Manually inject content into the tree
muninn-mem scan                         # Scan repo + emit neuron map JSON

# Mycelium feeding
muninn-mem feed <transcript>            # Feed mycelium + compress to .mn
muninn-mem feed --history               # Catch up on all past transcripts
muninn-mem feed --watch                 # Poll-based feed (for scheduled tasks)
muninn-mem bridge                       # Manual bridge invocation
muninn-mem zones                        # Detect + label thematic zones (Laplacian spectral clustering)

# Cube (B33 destruction/reconstruction — 5597 LOC unlocked in H.1)
muninn-mem cube --cube-action scan      # Scan repo, subdivide, build index
muninn-mem cube --cube-action run --cycles N --level L
muninn-mem cube --cube-action status    # Default — print cube store state
muninn-mem cube --cube-action god       # Compute God's Number

# Forge metrics (344 LOC unlocked in H.4)
muninn-mem metrics [--output FILE]      # JSON report: carmack + locate + Q-modularity

# Diagnostics
muninn-mem verify <file>                # Check compression quality (facts, ratio)
muninn-mem diagnose                     # Full pipeline self-check
muninn-mem doctor                       # Pre-flight — short-circuits if no .muninn/ (G.6)
muninn-mem upgrade-hooks                # Update Claude Code hooks to latest format

# Cube reflective passes
muninn-mem trip                         # Trigger a cube cycle
muninn-mem think                        # Cube reflective pass
muninn-mem quarantine <id>              # Quarantine a suspected cube

# Security
muninn-mem lock                         # Encrypt .muninn/ at rest (AES-256-GCM)
muninn-mem unlock                       # Decrypt with password
muninn-mem rekey                        # Re-encrypt with new password
muninn-mem scrub <path>                 # Scrub secrets from a file
muninn-mem purge-secrets                # Repo-wide secret scrubbing
muninn-mem sync                         # Sync to backend (TLS or git)

# Desktop UI (separate entry point — needs [ui] extra → PyQt6)
muninn-ui                               # PyQt6 desktop, 23 widgets, 11712 LOC unlocked in H.2
QT_QPA_PLATFORM=offscreen muninn-ui     # Headless test mode
```

## Claude Code Hooks

Bootstrap configures hooks automatically. **10 hooks** are installed under `.claude/hooks/`:

| Hook | Trigger | Purpose |
|---|---|---|
| `bridge_hook.py` | `UserPromptSubmit` | Inject mycelium context on user prompt |
| `session_start_hook.py` | `SessionStart` | Load root + 5 recent branches on boot (A.1) |
| `subagent_start_hook.py` | `SubagentStart` | Track subagent invocations |
| `post_tool_failure_hook.py` | `PostToolUseFailure` | Log failures to audit trail |
| `post_tool_use_edit_log.py` | `PostToolUse (Edit)` | [Dormant intentional] enterprise audit scaffolding |
| `pre_tool_use_bash_destructive.py` | `PreToolUse (Bash)` | **Block destructive shell commands** (active since I.5) |
| `pre_tool_use_bash_secrets.py` | `PreToolUse (Bash)` | **Detect secret leakage in bash commands** (active since I.5) |
| `pre_tool_use_edit_hardcode.py` | `PreToolUse (Edit)` | **Flag hardcoded paths in code edits** (active since I.5) |
| `notification_audit_hook.py` | `Notification` | Persist Claude Code notifications |
| `config_change_hook.py` | (manual / cron) | Detect drift in `.claude/settings.local.json` |

Plus the `PreCompact` / `SessionEnd` / `Stop` triggers wired to `python -m muninn feed --repo "${CLAUDE_PROJECT_DIR}"` for transcript compression and meta-mycelium federation.

A watchdog (`engine/core/watchdog.py`) runs every 15 minutes via Windows Task Scheduler as a failsafe on Windows hosts (Linux uses systemd-user timers via `muninn-mem install-cron`).

## MCP integration (live since Phase B, May 2026)

Phase B is **delivered** (not experimental anymore) and exposes Muninn data to Claude Code/Desktop as MCP tools, callable actively during generation. Install with the `[mcp]` extra:

```bash
pip install -e ".[mcp]"
muninn-mcp-mem &   # or: python -m muninn.mcp.server
```

Wire it into `~/.claude.json`:

```json
{
  "mcpServers": {
    "muninn": {
      "command": "muninn-mcp-mem",
      "env": {"MUNINN_REPO": "/path/to/your/repo"}
    }
  }
}
```

**10 tools currently exposed** (proven live in real Claude Code sessions since 2026-05-12):

| Tool | Purpose |
|---|---|
| `mycelium_recall_local(query, top_k, hops)` | Spreading activation over the local mycelium |
| `mycelium_recall_meta(query, top_k, hops)` | Read-only query into the federated meta-mycelium (7.5M edges) |
| `mycelium_recall(scope, query, top_k, hops)` | Smart router: `auto` / `local` / `meta` / `both` with linear/RRF fusion |
| `tree_get_root()` | Returns the always-loaded root.mn content |
| `tree_get_branch(branch_name)` | Returns a specific branch's compressed content |
| `tree_list_branches()` | Lists all branches with temperatures + sizes |
| `bugs_list()` / `bugs_get(bug_id)` | BUGS.md read-only access |
| `runbook_list_sections()` / `runbook_get(section)` | RUNBOOK.md read-only access |

Recall results are filtered by the universal degree-based stopword filter (G.1, opt-out via `MUNINN_RECALL_STOPWORD_PERCENTILE=0`).

Full spec in [`docs/MCP_SETUP.md`](docs/MCP_SETUP.md) and [`docs/BATTLE_PLAN_MASTER_MCP.md`](docs/BATTLE_PLAN_MASTER_MCP.md) §Phase B.

## Multilingual offline (K.1 + K.1.bis, 2026-05-13)

Concept normalization across French and English works **without any API call**. `ConceptTranslator` loads a static lexicon at boot:

- **K.1** : 946 entries curated MIT (dev-vocab: `fichier→file`, `arbre→tree`, `mémoire→memory`, `compression→compression`, `commit→commit`, etc.)
- **K.1.bis** : +389 entries pulled from Wikidata SPARQL (license CC0, public domain — `astronomie→astronomy`, `mathématiques→mathematics`, `biologie→biology`, etc.)
- **Total** : 1336 entries shipped in the wheel (`engine/core/data/lexicons/fr_en.json`)

Lookup order : `static lexicon` → `is_english` check (via tiktoken) → passthrough (or Haiku API if `MUNINN_TRANSLATE_FALLBACK_API=1`).

To extend the lexicon yourself, re-run the Wikidata pull script:
```bash
python3 scripts/build_fr_en_dict.py --limit 200
```

Idempotent. Adds only new pairs absent from the curated set. CC0 data, MIT-clean script. Phase **K.2** (planned) will replace this with LaBSE cross-lingual embeddings for true any-language coverage.

## Continuous Integration

`.github/workflows/ci.yml` runs on every push and every PR to `main`:

1. **Tree integrity check** (no node exceeds its `max_lines` budget)
2. **Engine smoke commands** (status, prune, compress, boot)
3. **Mycelium smoke commands** (simulate, bootstrap)
4. **Pytest suite** — 2849+ tests, including 173 UI tests via `QT_QPA_PLATFORM=offscreen` (H.2b activated UI tests in CI)
5. **Factual retention benchmark** (P35)
6. **Feed transcript parsing test**
7. **forge --gen-props matrix** (smoke per engine/core module)
8. **E2E pip install from scratch** (Phase A.4 pin — `pip install -e` + `muninn-mem init` + `muninn-mem doctor` ALL GREEN)

CI Python: 3.13 (the only version actively tested, per honest claim from G.8). `forge-shield` installed from PyPI `==2.1.2`.

**Latest run**: 3/3 jobs SUCCESS (HEAD `5dad754`, run 25786221196 + later K.1.bis CI run). **5 consecutive green CI runs** since 2026-05-12 evening.

## Recent Fixes (May 2026)

| Phase | Commits | Fix |
|---|---|---|
| Phase A (auto session) | 4/4 ✅ | Session lifecycle hooks (SessionStart/End/Stop), 35 tests |
| Phase B (MCP server) | 6/6 ✅ | 10 MCP tools, dual-mycelium router, auto-calibration C.0 |
| Phase C (polish) | 5/6 ✅ | C.2 reverted, RRF fusion, threshold tuning |
| Phase D (PyPI release) | 4/5 ✅ | 1.0.3 on TestPyPI live; D.3 PyPI prod pending |
| Phase E (hardening) | 7/7 ✅ | Renamed binaries (`muninn-mem`, `muninn-mycel`, `muninn-mcp-mem`), `--help` argparse, doc drift |
| Phase F (CI hotfixes) | 3/3 ✅ | `mcp` added to base CI install, E2E hardcoded path fix |
| Phase G (bug cleanup) | 8/8 ✅ | Universal stopword filter, friendly errors (`MUNINN_DEBUG`), doctor pre-init clarity, Python version honest claim, doc drift |
| Phase H (light up everything) | 14/15 ✅ | `muninn-mem cube` (5597 LOC), `muninn-ui` (11712 LOC), `--include-dreams` (561 LOC), `muninn-mem metrics` (344 LOC), UI tests reactivated in CI, anti-orphan + API bloat garde-fous, 1.1.0 bump. H.6b vault deferred |
| Phase I (zero dormant) | 4/5 ✅ | Wiring-check tests, zombie ratchet, edit-log dormant whitelist, session_index documented. I.5 un-xfailed |
| Phase K.1 (multilingual offline) | ✅ 2026-05-13 | 946 curated MIT entries, ConceptTranslator backend swap, API opt-in |
| Phase K.1.bis | ✅ 2026-05-13 | +389 CC0 Wikidata entries, gap test fix, total 1336 entries |

See [`docs/CHANGELOG.md`](CHANGELOG.md), [`docs/BATTLE_PLAN_MASTER_MCP.md`](docs/BATTLE_PLAN_MASTER_MCP.md), and [`docs/PROMPT_EXEC_PHASE_H.md`](docs/PROMPT_EXEC_PHASE_H.md) for detailed timelines.

## Benchmarks (tiktoken, March 2026)

### Per-file (full pipeline L1–L7 + L10 + L11 + L9)

| Context | Ratio |
|---|---|
| HSBC Methodology (6K tok) | x13.8 |
| HSBC Tree (5K tok) | x11.4 |
| Deployment hardware (7K tok) | x9.6 |
| Biomechanics gestures (7K tok) | x7.8 |
| SOL.md full pipeline (20K chars) | x7.7 |
| Wearable UX research (8K tok) | x7.4 |

### Cross-repo (230 files, 4 repos)

| Repo | Files | Input | Output | Ratio |
|---|---|---|---|---|
| infernal-wheel | 58 | 535K tok | 87K tok | x6.2 |
| HSBC-algo-genetic | 115 | 194K tok | 64K tok | x3.0 |
| shazam-piano | 45 | 107K tok | 37K tok | x2.9 |
| MUNINN- | 12 | 19K tok | 8K tok | x2.3 |
| **Total** | **230** | **855K tok** | **196K tok** | **x4.4** |

**API cost (Haiku): $0.21 for 230 files.**

### Factual retention

- 40 questions on compressed text → **37/40 correct (92%)**
- Method: pure text search, zero API, reproducible

## Architecture metrics (forge-shield 2.1.2, May 2026)

- **Q-modularity** (Newman-Girvan over import graph): **0.670** — "good" per Newman 2006 (≥ 0.30 threshold)
- **Top risk file** (`forge --carmack`): `engine/core/muninn.py` (hub of the CLI — Kalman risk reflects intentional centralization)
- **Anomaly z-score outliers** (`forge --anomaly`): all engine/core hubs (`muninn`, `mycelium`, `cube`, `cube_providers`, `mycelium_db`) — expected for a hub-spoke topology
- **Public-method ratchet** (H.8 garde-fou): `MyceliumDB` ≤ 52, `Mycelium` ≤ 20, `Cube` ≤ 4 (any growth requires explicit baseline bump + commit justification)
- **Zombie ratchet** (I.2 garde-fou): public functions with no callers ≤ 40 (currently 35, captured by `tests/_zombie_function_inventory.txt` on each run)

## Theoretical Foundations

| # | Technique | Reference | Purpose |
|---|---|---|---|
| 1 | Cue Distillation (L10) | Bartlett 1932, Rao & Ballard 1999 | Strip knowledge the LLM already has |
| 2 | Rule Extraction (L11) | Kolmogorov 1965 | Factor repeated patterns into rules |
| 3 | Sleep Consolidation | Wilson & McNaughton 1994 | Merge cold branches before deletion |
| 4 | Spreading Activation | Collins & Loftus 1975 | Semantic retrieval through co-occurrence network |
| 5 | Spaced Repetition | Settles & Meeder 2016 (Ebbinghaus 1885) | Branch lifecycle via forgetting curve p = 2^(-Δ/h) |
| 6 | Q-modularity | Newman & Girvan 2004, Blondel et al. 2008 | Architectural health (via forge-shield) |
| 7 | Ochiai SBFL | Abreu et al. 2007 | Fault localization (via forge-shield) |
| 8 | Saturation dynamics | Lotka 1925, Volterra 1928 | A4 mycelium connection saturation |
| 9 | Reciprocal Rank Fusion | Cormack et al. 2009 | Dual-mycelium fusion (MCP B.3) |

## Repo Structure

```
engine/
  core/
    muninn.py             Main CLI (2200+ lines, 32 subcommands)
    muninn_tree.py        L-system tree + sleep consolidation
    muninn_tree_doctor.py P3 split — doctor pre-flight (pre-init short-circuit since G.6)
    muninn_tree_boot.py   P3 split — boot pipeline
    muninn_tree_prune.py  P3 split — prune + --include-dreams wire (H.3)
    muninn_layers.py      11 compression layers + L9/L12 (L12 default-on since H.6c)
    muninn_feed.py        Hook → mycelium feeding pipeline
    muninn_install.py     Hook installer (3 defensive hooks since I.5)
    mycelium.py           Co-occurrence network + spreading activation
    mycelium_db.py        SQLite backend + WAL + ConceptTranslator (K.1 static lexicon)
    mycelium_meta.py      Federated meta-mycelium
    mycelium_zones.py     Laplacian spectral clustering
    mycelium_activation.py Spreading activation (Collins & Loftus 1975)
    mycelium_dream.py     Sleep consolidation (Wilson & McNaughton 1994, 561 LOC, wired via H.3)
    cube.py               Cube engine — destruction/reconstruction
    cube_analysis.py      B33 anomaly tracking + carmack scoring (5597 LOC wired via H.1)
    cube_providers.py     Cube I/O providers (Ollama, mock, …)
    cube_store.py         SQLite cube store
    vault.py              AES-256-GCM at-rest encryption (551 LOC, dormant intentional)
    forge_metrics.py      Subprocess wrapper around forge-shield 2.1.2 (wired via H.4)
    tokenizer.py          tiktoken wrapper with regex fallback
    watchdog.py           Windows-only scheduled task runner (dormant on Linux)
    sync_backend.py       Sync over git or TLS
    sync_tls.py           mTLS transport TLSv1.3 (experimental, opt-in MUNINN_SYNC_TLS_HOST)
    wal_monitor.py        SQLite WAL checkpoint monitor
    lang_lexicons.py      33 programming-language formatting lexicons (Cube prompts)
    budget_select.py      L12 BudgetMem dynamic programming chunk selection
    dedup.py              SimHash + Bloom dedup (P26/P27)
    lexicons.py           Compression lexicons (P5 universal rules)
    _secrets.py           secure_perms() + redact_secrets_text()
    _hook_logger.py       _SecureRotatingFileHandler (rotated logs in 0o600)
    data/
      lexicons/
        fr_en.json        K.1 + K.1.bis offline FR→EN dict (1336 entries)
        fr_en_wikidata.json K.1.bis Wikidata-only output (CC0 traceability)
muninn/                   pip-installable package — shims re-export from engine/core (BUG-091 closed 2026-05-09, _engine 2026-05-19)
  _engine.py              Shim of engine/core/muninn.py (entry point muninn-mem)
  mycelium.py             Shim
  vault.py                Shim
  ui/
    main_window.py        PyQt6 MainWindow (entry point: muninn-ui — H.2)
    __main__.py           Enable `python -m muninn.ui`
    23 widgets total      4-panel layout + cube live + neuron map + tree view + terminal
  mcp/
    server.py             FastMCP server, 10 tools, dual-mycelium router with auto-calibration
scripts/
  build_fr_en_dict.py     K.1.bis Wikidata SPARQL extender (CC0 data, MIT script)
memory/
  tree.json               L-system tree (self-repo legacy fallback)
  root.mn                 Root memory (always loaded)
  b*.mn                   Branch files
tests/                    2849 tests collected, 2849+ run in CI
  benchmark/              Factual retention benchmark (40 questions)
  test_*.py               223+ test files (chunks, tiers, props, audits)
  test_props_*.py         Hypothesis property tests (regenerated by forge --gen-props)
  test_k1_*.py            K.1 / K.1.bis multilingual offline (10 tests)
  test_h*.py              Phase H wiring tests (cube, ui, metrics, dreams, etc.)
  test_h0_no_orphan.py    Anti-orphan garde-fou (6 facettes)
  test_h8_api_bloat_*.py  API bloat ratchet (MyceliumDB ≤ 52, Mycelium ≤ 20, Cube ≤ 4)
  test_i2_no_zombie_*.py  Zombie ratchet (≤ 40 public functions without callers)
docs/
  QUICKSTART.md           10-step user install
  MCP_SETUP.md            MCP server full spec
  LITERATURE.md           Literature review (15+ papers)
  BENCHMARK_*.md          Benchmark results
  SYSTEM_MAP.md           Visual architecture map
  TIER1_SUMMARY.md / TIER2_SUMMARY.md / TIER3_PLAN.md
  BATTLE_PLAN_MASTER_MCP.md   MCP roadmap (A→F delivered)
  PROMPT_EXEC_PHASE_H.md      Phase G+H+I master executable prompt
  BATTLE_PLAN_PHASE_K_MULTILINGUAL_OFFLINE.md  K.1 + K.2 plan
  ANTI_BULLSHIT_BATTLE_PLAN.md  RULE 4 contract
CHANGELOG.md              Project changelog
BUGS.md                   Bug tracker (121 RESOLVED, 0 OPEN)
constraints.txt           Pinned versions for reproducible builds
pyproject.toml            Package metadata + optional extras [tokens] [llm] [quality] [mcp] [ui] [all]
.muninn/                  Local data (gitignored, chmod 0o600)
  mycelium.db             Co-occurrence network (SQLite)
  cube.db                 Cube state (SQLite)
  tree/                   L-system tree (operational)
  sessions/*.mn           Compressed transcripts
  session_index.json      Session catalog (writer muninn_feed, readers muninn_tree x4)
  errors.json             Error/fix pairs (P18)
  anomalies.jsonl         Cube anomaly stream
  hook_errors.log[.1-3]   Hook error rotation (RotatingFileHandler)
.claude/
  hooks/*.py              10 hooks (see "Claude Code Hooks" section)
  settings.local.json     Claude Code config (gitignored; generated by `muninn-mem init`)
.github/
  workflows/ci.yml        CI: tree + smoke + 2849+ pytest + UI offscreen + forge_smoke + E2E
```

## References

Every paper below is cited **directly in production code** (`engine/core/*.py`, `muninn/mcp/server.py`, `engine/core/scanner/*.py`). Verified by 4-agent grep audit on 2026-05-13.

For the extended bibliography (bio-vectors per species, negative results we deliberately avoided, 2024-2025 papers still under evaluation, pipeline formulas with exact equations), see [`docs/LITERATURE.md`](docs/LITERATURE.md) and [`docs/PIPELINE_FORMULAS_MAP.md`](docs/PIPELINE_FORMULAS_MAP.md).

### Memory, cognition & consolidation

1. **Anderson, J.R.** (1993). *Rules of the Mind* — ACT-R cognitive architecture (boot scoring).
2. **Bartlett, F.C.** (1932). *Remembering*. Cambridge University Press. — L10 Cue Distillation.
3. **Collins, A.M. & Loftus, E.F.** (1975). *A spreading-activation theory of semantic processing*. Psychological Review 82(6). — mycelium retrieval.
4. **Ebbinghaus, H.** (1885). *Über das Gedächtnis* — forgetting curve, branch lifecycle.
5. **Endsley, M.R.** (1995). *Toward a theory of situation awareness in dynamic systems*.
6. **Klein, G.A.** et al. (1986). *Rapid decision making on the fireground* — RPD.
7. **Nader, K., Schafe, G.E. & LeDoux, J.E.** (2000). *Fear memories require protein synthesis in the amygdala for reconsolidation*. Nature 406.
8. **Rao, R.P.N. & Ballard, D.H.** (1999). *Predictive coding in the visual cortex*. Nature Neuroscience 2(1).
9. **Richter-Levin, G. & Akirav, I.** (2003). *Amygdala-hippocampus dynamic interaction in relation to memory* — V6A arousal Hill function.
10. **Settles, B. & Meeder, B.** (2016). *A Trainable Spaced Repetition Model for Language Learning*. ACL 2016 — branch decay (Ebbinghaus-style p = 2^(-Δ/h)).
11. **Talmi, D.** (2013). *Enhanced emotional memory: cognitive and neural mechanisms* — valence-modulated decay.
12. **Tenenbaum, J.B.** et al. (2009). *How to grow a mind: Statistics, structure and abstraction*. Science 331 — boot query expansion.
13. **Wilson, M.A. & McNaughton, B.L.** (1994). *Reactivation of hippocampal ensemble memories during sleep*. Science 265(5172) — Sleep Consolidation (`mycelium_dream.py`).

### Information theory & compression

14. **Charikar, M.S.** (2002). *Similarity Estimation Techniques from Rounding Algorithms* — SimHash (P26 dedup).
15. **Cilibrasi, R. & Vitányi, P.M.B.** (2005). *Clustering by compression* — NCD similarity.
16. **Cormack, G.V., Clarke, C.L.A. & Büttcher, S.** (2009). *Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods*. SIGIR '09 — MCP dual-mycelium fusion (chunk B.3).
17. **Friston, K.** (2010). *The free-energy principle: a unified brain theory?* Nature Reviews Neuroscience — `cube_analysis.py` surprise metric.
18. **Kolmogorov, A.N.** (1965). *Three approaches to the quantitative definition of information*. Problems of Information Transmission 1(1) — L11 rule extraction.
19. **Reed, I.S. & Solomon, G.** (1960). *Polynomial codes over certain finite fields* — V9B redundancy on cold branches.

### Network science & graph theory

20. **Battiston, S.** et al. (2012). *DebtRank: Too Central to Fail?* — `scanner/propagation.py` centrality propagation.
21. **Blondel, V.D.** et al. (2008). *Fast unfolding of communities in large networks*. J. Stat. Mech. — Louvain clustering (via forge-shield).
22. **Brandes, U.** (2001). *A faster algorithm for betweenness centrality* — O(n·m) (`scanner/r0_calculator.py`).
23. **Burt, R.S.** (1992). *Structural Holes* — community broker detection in mycelium graph.
24. **Callaway, D.S.** et al. (2000). *Network robustness and fragility* — meta-mycelium resilience.
25. **Goldbeter, A. & Koshland, D.E.** (1981). *An amplified sensitivity arising from covalent modification* — Hill function in `scanner/priority_ranker.py`.
26. **Kleinberg, J. & Tardos, É.** (2003). *Influence Minimization* — `scanner/report.py`.
27. **Kondor, R.I. & Lafferty, J.** (2002). *Diffusion kernels on graphs* — Heat Kernel `scanner/propagation.py`.
28. **Molloy, M. & Reed, B.** (1995). *A critical point for random graphs with a given degree sequence* — percolation threshold `scanner/r0_calculator.py`.
29. **Newman, M.E.J. & Girvan, M.** (2004). *Finding and evaluating community structure in networks*. Physical Review E 69(2) — Q-modularity baseline (0.670 measured).
30. **Pastor-Satorras, R. & Vespignani, A.** (2001). *Epidemic spreading in scale-free networks* — meta-mycelium R0 threshold.
31. **Pearl, J.** (1988). *Probabilistic Reasoning in Intelligent Systems* — Bayesian foundations `cube_analysis.py`.
32. **Prakash, B.A.** et al. (2012). *Threshold conditions for arbitrary cascade models* — `scanner/propagation.py` spreading dynamics.
33. **Tononi, G. & Edelman, G.M.** (1999). *Measures of degeneracy and redundancy in biological networks* — cube `_degeneracy` field.
34. **Vidal, M.** (2007). *A unifying view of 21st century systems biology* — `cube_analysis.py` systems-level perspective.

### LLM compression & memory (state of the art)

35. **Gutierrez, B. & Shu, Y.** (2024). *HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs* — `muninn_tree.py` retrieval inspiration.
36. **Jiang, H.** et al. (2023). *LLMLingua: Compressing Prompts for Accelerated Inference*. EMNLP 2023.
37. **Liu, N.F.** et al. (2024). *Lost in the Middle: How Language Models Use Long Contexts*. TACL — positional bias documented in `muninn/mcp/server.py`.
38. **Park, J.S.** et al. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. UIST '23 — boot scoring inspiration.
39. **Zhou, Y.** et al. (2023). *AdapT: Adaptive Token-Level Compression for Code* — `cube_providers.py`.

### Software engineering & quality

40. **Abreu, R., Zoeteweij, P. & Van Gemund, A.J.C.** (2007). *On the accuracy of spectrum-based fault localization* — Ochiai SBFL (via forge-shield `--locate`).
41. **Nagappan, N.** et al. (2005). *Use of relative code churn measures to predict system defect density*. ICSE 2005 — defect prediction (via forge-shield `--predict`).
42. **Scanniello, G.** (2011). *Architectural risk analysis via Louvain community detection*.
43. **Schulte, E.** et al. (2014). *Software Mutational Robustness* — mutation testing foundation.
44. **Yang, H.** et al. (2016). *Mining version histories for verified bug-fixing patterns*.

### Biology, immunology, mycology & collective intelligence

45. **Boyd, R. & Richerson, P.J.** (1985). *Culture and the Evolutionary Process* — cultural learning analogue for meta-mycelium federation.
46. **Forrest, S.** et al. (1994). *Self-Nonself Discrimination in a Computer* — negative selection (P0bis secure_perms).
47. **Greensmith, J. & Aickelin, U.** (2008). *The Dendritic Cell Algorithm* — anomaly classification.
48. **Huang, C.Y.F. & Ferrell, J.E.** (1996). *Ultrasensitivity in the mitogen-activated protein kinase cascade*. PNAS 93 — `cube_analysis.py` influence cascade.
49. **Lotka, A.J.** (1925) / **Volterra, V.** (1928). *Predator-prey dynamics* — A4 mycelium saturation (`SATURATION_BETA`).
50. **Matzinger, P.** (2002). *The Danger Model: A Renewed Sense of Self*. Science 296 — hooks as immune-system metaphor.
51. **Mezard, M. & Parisi, G.** (2002). *The cavity method at zero temperature* — Survey Propagation (cube B21 pre-filter).
52. **Perelson, A.S.** (1989). *Immune Network Theory* — connection decay/growth in `mycelium.py`.
53. **Seeley, T.D.** et al. (2012). *Stop signals provide cross inhibition in collective decision-making by honeybee swarms*. Science 335.
54. **Shomrat, T. & Levin, M.** (2013). *An automated training paradigm reveals long-term memory in planarians* — V9 vector inspiration.
55. **Villegas, P.** et al. (2023). *Laplacian renormalization group for heterogeneous networks*. Nature Physics — cube B9 grouping.
56. **Waters, C.M. & Bassler, B.L.** (2005). *Quorum Sensing: Cell-to-cell communication in bacteria* — meta-mycelium federation threshold.
57. **Wynne, C.D.L.** (1995). *Reinforcement accounts for transitive inference performance* — `mycelium_activation.py`.
58. **Yekutieli, Y.** et al. (2005). *Dynamic model of the octopus arm* — V1A coupled oscillator in `muninn_tree_boot.py`.

### Optimization & reinforcement learning

59. **Carhart-Harris, R.L.** et al. (2012, 2014). *The entropic brain hypothesis* — `mycelium_dream.py` entropy regularization.
60. **Colorni, A., Dorigo, M. & Maniezzo, V.** (1996). *Ant System: Optimization by a colony of cooperating agents*.
61. **Kirkpatrick, J.** et al. (2017). *Overcoming catastrophic forgetting in neural networks* (EWC) — branch-lifecycle inspiration.
62. **Kirkpatrick, S., Gelatt, C.D. & Vecchi, M.P.** (1983). *Optimization by Simulated Annealing*. Science 220.
63. **Montague, P.R., Dayan, P. & Sejnowski, T.J.** (1997). *A framework for mesencephalic dopamine systems based on predictive Hebbian learning* — TD learning.

### Affect, sentiment & signal processing

64. **Bollerslev, T.** (1986). *Generalized autoregressive conditional heteroskedasticity* (GARCH) — A2 decay variance modelling.
65. **Guilford, J.P.** (1967). *The Nature of Human Intelligence* — divergent thinking metric in `muninn_tree.py`.
66. **Hutto, C.J. & Gilbert, E.** (2014). *VADER: A Parsimonious Rule-based Model for Sentiment Analysis*. ICWSM.
67. **Russell, J.A.** (1980). *A circumplex model of affect* — V6A valence/arousal axes.

## License

**MIT** — clean for commercial use. The wheel embeds an MIT-curated lexicon (K.1, 946 entries) and CC0 Wikidata data (K.1.bis, 389 entries); CC0 is public domain and compatible with the MIT distribution. No GPL, no CC-BY-NC, no Share-Alike contamination — Muninn can be sold or relicensed without restriction.

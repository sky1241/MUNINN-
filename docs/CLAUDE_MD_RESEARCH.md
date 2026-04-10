# CLAUDE.md Research Corpus — Evidence Base for Future Decisions

> Compiled 2026-04-10 by Sky + Claude Opus 4.6
> Sources: Mission 3 first-pass (14 sources) + ChatGPT Deep Research
> Purpose: durable reference for any future decision about CLAUDE.md in MUNINN
> Status: research complete, no code touched, no conclusion forced
>
> **How to use this file**: when Sky or a cousin wonders "should I change
> CLAUDE.md?", read this first. It captures what's actually known vs what's
> repeated as folklore. Every claim has a source or is marked FOLKLORE.

---

## 0. TL;DR — What changed after Deep Research

The Deep Research challenged 6 of my 7 first-pass findings. Summary of what survives:

| First-pass finding | Status after Deep Research |
|---|---|
| "Negative prompting backfires (Pink Elephant)" | **PARTIALLY TRUE** — pure negation brittle, but structured "wrong + right" contrast can help |
| "150-200 instruction ceiling" | **FOLKLORE** — not traceable to primary source; real dynamics are compounding failure + ordering effects |
| "60-line CLAUDE.md always beats 300-line" | **OVERSTATED** — production counter-example exists (SideroLabs 219 lines); what matters is bloat vs focus, not line count alone |
| "Claude 4.6 overtriggers on aggressive prompting" | **PARTIALLY TRUE** — but causal lever may be **precedence conflicts**, not tone (GitHub issue evidence) |
| "Universal 8-rule recipes cut tokens safely" | **HALF-TRUE** — they cut tokens but shift failure modes toward omissions |
| "U-shaped attention curve primes sandwich" | **OVERSIMPLIFIED** — ordering stops rescuing at high density; recency surface is multi-file |
| "XML tags validated" | **CONFIRMED** by Anthropic official docs |

**The one big new fact** : CLAUDE.md is loaded as **context, not enforced configuration**.
Official Anthropic docs state this explicitly. It's a **probabilistic influence channel**,
not a guarantee. All conclusions flow from that.

---

## 1. Counter-evidence to my first-pass findings (the bombs)

### 1.1 — "Negative examples backfire" is too strong

**First-pass source**: Anthropic blog post saying "tell Claude what to do, not what not to do".

**Counter-evidence from Deep Research**:
- **Contrastive Prompting paper (2026-03-10)**: explicit "wrong + correct answer"
  pattern boosts GSM8K / AQUA-RAT reasoning accuracy with GPT-4.
  Source: https://www.sciencedirect.com/science/article/abs/pii/S0957417425040229
- **Pure negation IS brittle** (confirmed): 2025 negation-robustness paper shows
  accuracy drops when hypotheses differ only by negation, across models and languages.
- **Prompt Sentiment 2025 paper**: negative prompts reduce factual accuracy AND
  amplify bias; positive prompts increase verbosity but preserve accuracy.
- **Transfer gap**: contrastive gains measured in reasoning tasks, NOT in
  "agent operating rules" context. Direct transfer to CLAUDE.md is untested.

**Verdict**: the "Bad reflex / Correction" pattern I used at chunk 2 is
**closer to the helpful contrastive form than to the harmful pure-negation form**,
because each Bad reflex is immediately paired with a Correction. But it can still
be improved by making the Bad reflex **minimal** (not dominating attention) and
keeping the Correction dominant in line length.

### 1.2 — The "150-200 instruction ceiling" is FOLKLORE

**First-pass source**: HumanLayer blog post, ETH Zurich data (both cited repeatedly).

**Counter-evidence from Deep Research**:
- **IFScale benchmark (arxiv 2507.11538, 2025-07-15)**: 20 models tested from
  10 to 500 simultaneous keyword-inclusion instructions. **Best frontier models
  reach only 68% accuracy at 500**. Paper emphasizes **continuous degradation
  curves + primacy/ordering effects**, NOT a cliff at 150-200.
- **ManyIFEval / "Curse of Instructions" (2025 ICLR)**: when scoring "all-pass"
  (satisfy ALL instructions simultaneously), GPT-4o drops to **15%** at only
  **10 instructions**. Claude 3.5 Sonnet drops to 44%. Self-refinement raises
  these to 31% / 58%. **Failure compounds even below 10 instructions.**
- **Primary source for "150-200 ceiling" not found** in Deep Research.
  Widely repeated but untraceable to a rigorous benchmark.

**Verdict**: forget "instruction count ceiling". The real dynamic is:
1. **Compounding failure** — each added verifiable constraint increases joint-failure risk.
2. **Ordering effects** — primacy matters more at low density, less at high density.
3. **Instruction type matters** — keyword-inclusion ≠ safety rule ≠ workflow step.

**What this means for us**: counting "8 RULES" is misleading. If each RULE
has 3 sub-clauses (Directive + Bad reflex + Correction = 3 constraints each),
we actually have ~24 operational constraints. That's still OK but it's not 8.

### 1.3 — "Shorter CLAUDE.md is always better" is oversimplified

**First-pass source**: HumanLayer "ideally under 60 lines" + ETH Zurich 3% degradation.

**Counter-evidence from Deep Research**:
- **SideroLabs/docs CLAUDE.md: 219 lines** in production. A real documentation
  repo that operates on the exact edge of Anthropic's guideline and still ships.
- **Netdata CLAUDE.md: 49 lines** — short example works.
- **Zuplo docs: 66 lines**, **QuestDB: 97 lines** — middle ground examples work.
- **Anthropic official guidance**: "target under 200 lines per CLAUDE.md file"
  (https://code.claude.com/docs/en/memory). Note: **target**, not hard cap.
- **What matters**: bloat and redundancy, not raw line count. A 60-line CLAUDE.md
  with 3 conflicting rules is worse than a 180-line CLAUDE.md with 8 coherent ones.

**Verdict**: our 186-line CLAUDE.md is **at the upper bound of Anthropic's target**
but NOT in the "definitely too long" zone. Further compression is optional,
not mandatory.

### 1.4 — "Claude 4.6 overtriggers on aggressive prompting" — but the cause is probably precedence, not tone

**First-pass source**: Anthropic official migration guide saying "dial back anti-laziness
prompting on 4.6".

**Counter-evidence from Deep Research**:
- **GitHub issue anthropics/claude-code#27032 (2026-02-20)**: documented case
  where explicit CLAUDE.md rules were violated by Claude Code. Root cause
  identified as **built-in plan-mode prompts taking precedence over user
  CLAUDE.md**, not model temperament. Cost: ~27k tokens wasted on
  unauthorized parallel agent launches.
- **GitHub issue anthropics/claude-code#22309 (2025)**: community complaint
  that CLAUDE.md content is wrapped with a "may or may not be relevant"
  disclaimer framing, which undermines compliance at the delivery mechanism
  level.
- **Anthropic docs on memory**: "Claude treats them as context, not enforced
  configuration". Explicit acknowledgment that there's no hard precedence resolution.

**Verdict**: when CLAUDE.md rules fail, the cause is often NOT "Claude overtriggered
on my aggressive tone". It's often **precedence conflict** with higher-priority
harness prompts we can't see or edit. Toning down our rules might not fix anything
if the harness still wins.

### 1.5 — "Token-efficient recipes cut output without downsides" is wrong

**First-pass source**: drona23/claude-token-efficient universal CLAUDE.md claims 63% reduction.

**Counter-evidence from Deep Research**:
- **IFScale finding**: adding constraints under high density **shifts error types
  toward omissions**. You get less output but you also get less complete output.
- **AGENTS.md paired study (arxiv 2601.20404, 2026-03-30)**: 10 repos, 124 PRs,
  paired runs with/without AGENTS.md using Codex CLI (NOT Claude Code).
  Median runtime drop: **-28.64%**. Output token drop: **-16.58%**. "Comparable
  task completion behavior" preserved. Real evidence but bounded scope.
- **Anthropic Claude Code best practices**: emphasize verification, planning,
  and context management — patterns that often need verbosity (plans, checks,
  commands). Pure brevity collides with safety.

**Verdict**: token-cutting recipes work for verbosity reduction but have a real
cost in **reliability and omission risk**. On an agent that edits files, omission
risk is worse than verbosity.

### 1.6 — "U-shaped attention + sandwich is the right pattern" — partially

**First-pass source**: Indie Hackers reverse-engineering article claiming primacy + recency.

**Counter-evidence from Deep Research**:
- **IFScale paper**: strong primacy effects CONFIRMED at low-to-medium instruction
  density, but paper explicitly says "at extreme densities, traditional prompt
  engineering becomes less effective as models become overwhelmed". Ordering
  stops rescuing you past a certain density.
- **Claude Code docs on memory loading**: CLAUDE.md is **concatenated across
  directory levels**. "Recency" is determined by LOAD ORDER across files, not
  by position within a single file. CLAUDE.local.md is appended AFTER CLAUDE.md
  at each level. Child-directory CLAUDE.md files load on demand.
- **Implication**: our single-file sandwich (MUNINN_RULES top + SANDWICH_RECENCY
  bottom) is ONE factor in a multi-file recency surface. Not wrong, just incomplete.

**Verdict**: sandwich is helpful but not a magic bullet. The full picture is
multi-file + directory hierarchy + harness system prompt position.

### 1.7 — What actually survives intact

Only one first-pass finding passes Deep Research without caveats:

**XML tags are effective**. Anthropic's own prompt engineering docs confirm:
"Claude was trained with XML tags in the training data, so using XML tags like
`<example>`, `<document>`, etc. to structure your prompts can help guide
Claude's output." Source: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags

Our `<MUNINN_RULES>` + `<RULE id="N">` format is validated by primary Anthropic documentation.

---

## 2. Empirical data table (primary sources only)

Only rows with explicit numeric results traced to primary sources. Folklore
claims explicitly marked.

| Claim | Number | Source | Methodology | Date | Confidence (1-5) |
|---|---|---|---|---|---|
| Instruction density degradation curve | 68% accuracy at 500 simultaneous instructions (best frontier) | https://arxiv.org/pdf/2507.11538 | IFScale benchmark, 20 models, keyword-inclusion task | 2025-07-15 | 4 |
| All-pass failure compounds at low counts | GPT-4o 15%, Claude 3.5 Sonnet 44% at 10 instructions | https://openreview.net/pdf/848f1332e941771aa491f036f6350af2effe0513.pdf | ManyIFEval benchmark, verifiable instructions | 2025 (ICLR) | 3 |
| Self-refinement improves compliance | GPT-4o 15→31%, Claude 3.5 Sonnet 44→58% (10 instructions) | Same as above | ManyIFEval with iterative refinement | 2025 | 3 |
| AGENTS.md reduces runtime | Median runtime -28.64% | https://arxiv.org/pdf/2601.20404 | 10 repos, 124 PRs, paired runs, Codex CLI | 2026-03-30 | 4 |
| AGENTS.md reduces output tokens | Median output -16.58% | Same as above | Same | 2026-03-30 | 4 |
| Claude Code treats CLAUDE.md as context, not config | "context, not enforced configuration" + "target under 200 lines" | https://code.claude.com/docs/en/memory | Official product documentation | 2026 (live docs) | 5 |
| CLAUDE.md files are additive, no hard precedence | "All discovered files are concatenated into context rather than overriding" | https://code.claude.com/docs/en/memory | Official docs | 2026 (live) | 5 |
| CLAUDE.md rules can be violated in practice | ~27k tokens wasted in 1 documented incident | https://github.com/anthropics/claude-code/issues/27032 | User incident report with quoted rules | 2026-02-20 | 3 |
| "may or may not be relevant" disclaimer undermines compliance | Community issue request | https://github.com/anthropics/claude-code/issues/22309 | User report | 2025 | 2 |
| Contrastive prompting improves reasoning | GSM8K + AQUA-RAT deltas with GPT-4 | https://www.sciencedirect.com/science/article/abs/pii/S0957417425040229 | Controlled evaluation, "let's give a correct and wrong answer" trigger | 2026-03-10 | 3 |
| **"150-200 instruction ceiling"** | **FOLKLORE** | — | Repeated online, no primary dataset found | — | — |

---

## 3. Production CLAUDE.md examples to study

Real repositories using CLAUDE.md in production. **Inspect directly before
designing yours**. Ordered by line count.

| Repo | Lines | Style | Diagnostic |
|---|---|---|---|
| Netdata | 49 | Rule-first, emphasis markers | "You MUST ALWAYS find the root cause… Patching without understanding… IS NOT ALLOWED." |
| Zuplo docs | 66 | Concise + operational + commands | Ends with link hygiene rules |
| QuestDB docs | 97 | Commands + architecture + content features | Maps to Anthropic's recommended structure |
| SideroLabs docs | **219** | Long operational spec | **Counter-example to "always short"** — real prod, exceeds 200 target |
| **Our MUNINN** | **186** | XML rules + sandwich + memo cousin | Near upper bound of Anthropic target |

**Pattern across all production files**:
- Crisp run commands
- Directory-specific constraints
- Externally-checkable style conventions (formatter/linter handles the rest)
- Non-negotiable rules placed early and emphasized
- Less XML schema, more rule-first prose

**What we do differently**: heavy XML format. Not wrong (Anthropic validates XML)
but uncommon in production OSS. We're closer to research-style prompt engineering
than typical OSS operational docs.

### Anthropic's own internal CLAUDE.md?

**Not found publicly**. The March 2026 source leak exposed Claude Code
implementation code and incident mechanics, but **no authorized copy of
Anthropic's internal CLAUDE.md exists** that Deep Research could locate.
Using leaked content as a primary evidence base is inappropriate for durable
engineering decisions.

Stripe (1,370 engineers) and Ramp published deployment metrics but **did not
publish their CLAUDE.md**. The enterprise config remains private.

---

## 4. The 5 questions — evidence-backed answers

### Q1 — Negative examples: help or hurt?

**Answer**: **Mixed, depends on form**.
- Pure negation ("don't do X") is brittle (documented weakness).
- Negative sentiment reduces factuality and amplifies bias.
- Structured "wrong + right" contrast can help reasoning tasks.
- Transfer from reasoning tasks to agent operating rules is **untested**.

**Our current format** ("Directive / Bad reflex / Correction"): closer to
the helpful contrastive form than to the harmful pure-negation form. **But**
each Bad reflex should be **kept minimal** and the Correction should **dominate**.

**Confidence**: medium.

### Q2 — Is our instruction count too high?

**Answer**: probably **not**, but we're at the upper bound.
- Anthropic target: under 200 lines. We're at 186.
- The "150-200 instruction ceiling" is FOLKLORE.
- Real dynamic: each verifiable sub-constraint adds compounding joint-failure risk.
- Our 8 RULES × 3 sub-clauses = ~24 operational constraints.

**Our position**: at ~24 constraints, we're in the zone where ManyIFEval shows
Claude 3.5 Sonnet at ~44% all-pass rate baseline (and 58% with self-refinement).
Claude 4.6 should do better but we have no primary data on 4.6.

**Confidence**: medium-high.

### Q3 — What do real production CLAUDE.md look like?

**Answer**: **short operational briefings, not long manifestos**.
- Median production CLAUDE.md is 49-97 lines.
- 219-line production example exists (SideroLabs) but is uncommon.
- Pattern: commands + directory constraints + externally-checkable style +
  a handful of non-negotiables.
- XML format uncommon in production OSS.

**Anthropic's own**: not publicly available. Can't be used as evidence.

**Confidence**: medium.

### Q4 — Does CLAUDE.md actually work, or is it placebo?

**Answer**: **probabilistic influence, not guarantee**.
- Anthropic explicitly says "context, not enforced configuration".
- Real violations documented (issue #27032) with cost measured (~27k tokens).
- Closest rigorous evidence: AGENTS.md paired study showing runtime -28.64%
  and tokens -16.58% — but for Codex CLI, not Claude Code.
- No quantified "CLAUDE.md compliance pass-through rate" published for Claude Code.

**Practical implication**: treat CLAUDE.md rules as **high-leverage suggestions**,
not enforcement. For rules that MUST hold, use hooks and tool-verification
instead (which IS enforced).

**Confidence**: medium-high.

### Q5 — ROI for a solo developer?

**Answer**: **probably positive but bounded**.
- Enterprise deployment stories show large ROI for Claude Code itself
  (Stripe 10K-line migration in 4 days, Ramp 80% incident time reduction)
  but these don't isolate CLAUDE.md tuning contribution.
- AGENTS.md study: meaningful token/runtime savings, but bounded and scope-dependent.
- Negative ROI risk is real: documented CLAUDE.md violations wasting tokens.
- No solo-developer-specific cost-benefit study exists.

**Practical implication**: optimize conservatively, measure before/after,
stop optimizing when returns flatten. Don't rewrite from scratch without data.

**Confidence**: medium.

---

## 5. Known unknowns (what evidence is absent)

These questions remain unanswered by available research. If we ever want
certainty, we need to do our own controlled experiments.

1. **Does CLAUDE.md specifically change Claude Opus 4.6's behavior?**
   No controlled A/B study exists for 4.6 + CLAUDE.md.

2. **Do "Bad reflex" style negative examples work in agent operating rules?**
   Contrastive prompting evidence is from reasoning tasks, not agent rules.
   Transfer is untested.

3. **What's the actual "compliance rate" of CLAUDE.md rules under real workloads?**
   No published methodology to measure this.

4. **Does the sandwich structure help at our density?**
   IFScale shows primacy works but ordering stops saving at high density.
   Where's our threshold?

5. **Anthropic's own internal CLAUDE.md patterns**.
   Not disclosed publicly. All evidence is from OSS and research.

6. **How much of CLAUDE.md Claude actually reads vs filters as "may not be relevant"?**
   Community suspects significant filtering. No data.

---

## 6. Actionable moves ranked by evidence strength

From the Deep Research final recommendations, ordered by how strong the
evidence behind each is.

### 6.1 — Build an evaluation harness BEFORE editing (highest confidence)
**Why**: mirrors AGENTS.md paired-study methodology. Lets us measure before/after
any change. Without this, we're doing vibes-based optimization.
**How**: 20-50 representative Muninn-dev tasks, run each with current CLAUDE.md
vs candidate variants, score (a) detectable rule violations, (b) time-to-completion,
(c) token usage.
**Source**: AGENTS.md paired-study methodology (arxiv 2601.20404) + IFScale methodology.

### 6.2 — Split always-on rules from scoped `.claude/rules/` (high confidence)
**Why**: Anthropic's own docs recommend it. Reduces bloat in the always-loaded file.
Allows path-specific rules.
**How**: keep MUNINN_RULES in root CLAUDE.md. Move narrow-scope or workflow-specific
rules to `.claude/rules/engine.md`, `.claude/rules/tests.md`, etc.
**Source**: https://code.claude.com/docs/en/memory official docs.

### 6.3 — Make core rules machine-checkable via tools/hooks (high confidence)
**Why**: documented failures show harness system prompts can override CLAUDE.md.
Tool verification is enforced; CLAUDE.md is suggestion.
**How**: every rule that MUST hold → hook or test that enforces it. Example:
RULE 7 "never display secrets" → vault.py scrub is already the enforcement;
the RULE is now redundant for enforcement purposes but useful as documentation.
**Source**: Anthropic Claude Code best practices docs + GitHub issue #27032.

### 6.4 — Rewrite "Bad reflex" blocks into minimal paired contrasts (medium confidence)
**Why**: contrastive prompting evidence supports structured wrong+right, but
pure negation is brittle and transfer from reasoning to agent rules is untested.
**How**: keep the contrastive signal but compress — 1 line "Do X" / 1 short
"Avoid: Y" label / 1 line "If Y happens, do Z instead".
**Source**: Contrastive Prompting paper (2026-03-10) + negation robustness research.

### 6.5 — Remove redundancy to stay below 200 lines (medium confidence)
**Why**: we're at 186/200. Anthropic target. Not mandatory but gives room for
future rules.
**How**: look for overlap between RULES and memo cousin. Use `<!-- -->` HTML
comments for maintainer notes (stripped before injection — free tokens).
**Source**: Anthropic memory docs + chunk 2 already uses this pattern.

---

## 7. What this means for OUR current CLAUDE.md (186 lines, 8 RULES, XML)

Honest verdict: **we're in an OK spot, not optimal**.

| Aspect | Status | Evidence |
|---|---|---|
| Line count (186) | **OK** — under 200 target, near upper bound | Anthropic docs |
| XML format | **Good** — validated by Anthropic | Prompt engineering docs |
| Sandwich structure | **Defensible** — primacy effects real, but not a magic bullet | IFScale + intuition |
| 8 RULES with Bad reflex | **Defensible** — contrastive-like format, not pure negation | Contrastive Prompting paper |
| Memo cousin compressed | **OK** — freed 22% tokens, no functional cost | Chunk 6-7 measurements |
| Not split into `.claude/rules/` | **Suboptimal** — all loaded at every session | Anthropic docs |
| Rules not machine-enforced | **Suboptimal** — harness can override | GitHub issue #27032 |
| Not instrumented with eval harness | **Big gap** — we optimize blind | AGENTS.md methodology |

**None of these are urgent fixes**. None are clearly wrong. The biggest lever
we haven't pulled is **instrumentation** — we don't know which rules actually
change Claude's behavior because we've never measured. Everything else is
secondary.

---

## 8. Next step options (for a future session, not tonight)

Three sensible next steps, from cheapest to most expensive. **None are
recommended without Sky's go**.

### Option A — Build a tiny eval harness (recommended first)
- 10-20 representative Muninn-dev tasks hand-picked
- Run with current CLAUDE.md, capture: rule violations, time, tokens
- Same tasks with a candidate CLAUDE.md variant
- Compare, decide based on data
- Cost: half a day
- Risk: zero (no CLAUDE.md change until data says so)

### Option B — Split `.claude/rules/` structure
- Move engine-specific rules to `.claude/rules/engine.md` with `paths:` frontmatter
- Keep root CLAUDE.md for truly universal rules
- Reduces always-loaded context
- Cost: 1-2 hours
- Risk: low

### Option C — Rewrite RULES with compressed contrastive form
- Each rule: 1 line Do / 1 short Avoid / 1 line Recovery
- Probably cuts CLAUDE.md another 20-30 lines
- Cost: 1 hour
- Risk: low but needs eval harness to validate

### What NOT to do
- Don't rewrite from scratch without data. All evidence says conservative optimization beats aggressive rewrite.
- Don't chase "60-line ideal". It's not a universal truth.
- Don't remove negative examples entirely. The evidence is mixed, not damning.
- Don't add more rules just because we have room. Compounding failure is real.

---

## Sources

### Primary (Anthropic official)
- [Claude Code — How Claude remembers your project](https://code.claude.com/docs/en/memory)
- [Claude API — Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Claude API — Use XML tags to structure your prompts](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags)
- [Claude Code — Best practices](https://code.claude.com/docs/en/best-practices)
- [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

### Primary (peer-reviewed / benchmarks)
- [IFScale: Instruction-Following at Scale (arxiv 2507.11538, 2025-07-15)](https://arxiv.org/pdf/2507.11538)
- [ManyIFEval / "Curse of Instructions" (ICLR 2025)](https://openreview.net/pdf/848f1332e941771aa491f036f6350af2effe0513.pdf)
- [AGENTS.md paired study (arxiv 2601.20404, 2026-03-30)](https://arxiv.org/pdf/2601.20404)
- [Contrastive Prompting (Science Direct, 2026-03-10)](https://www.sciencedirect.com/science/article/abs/pii/S0957417425040229)

### Primary (documented incidents)
- [GitHub issue anthropics/claude-code#27032 — CLAUDE.md rule violation with cost](https://github.com/anthropics/claude-code/issues/27032)
- [GitHub issue anthropics/claude-code#22309 — "may or may not be relevant" framing](https://github.com/anthropics/claude-code/issues/22309)
- [Zscaler — Claude Code source exposure analysis](https://www.zscaler.com/blogs/security-research/anthropic-claude-code-leak)
- [Trend Micro — Weaponizing trust: Claude Code lures](https://www.trendmicro.com/en_us/research/26/d/weaponizing-trust-claude-code-lures-and-github-release-payloads.html)

### Production CLAUDE.md examples
- Netdata (49 lines)
- Zuplo docs (66 lines)
- QuestDB docs (97 lines)
- SideroLabs docs (219 lines)

### First-pass sources (Mission 3, for reference)
- [HumanLayer — Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [Arize — CLAUDE.md best practices via prompt learning](https://arize.com/blog/claude-md-best-practices-learned-from-optimizing-claude-code-with-prompt-learning/)
- [Indie Hackers — Reverse-engineering Claude Code system prompts](https://www.indiehackers.com/post/the-complete-guide-to-writing-agent-system-prompts-lessons-from-reverse-engineering-claude-code-6e18d54294)
- [drona23/claude-token-efficient](https://github.com/drona23/claude-token-efficient)
- [shanraisshan/claude-code-best-practice](https://github.com/shanraisshan/claude-code-best-practice)
- [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts)
- [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
- [dbreunig — How Claude Code builds a system prompt](https://www.dbreunig.com/2026/04/04/how-claude-code-builds-a-system-prompt.html)
- [affaan-m/everything-claude-code AGENTS.md](https://github.com/affaan-m/everything-claude-code/blob/main/AGENTS.md)
- [Silicon Mirror sycophancy paper](https://arxiv.org/html/2604.00478)
- [Sycophancy in Large Language Models paper](https://arxiv.org/html/2411.15287v1)

### Related ecosystems (for cross-pollination)
- Cursor `.cursorrules` files
- Aider conventions files
- OpenAI GPTs custom instructions

---

## Meta-note for future sessions

**Why this file exists**: Sky asked for deep research on CLAUDE.md. We did it
in two passes (Mission 3 internal + ChatGPT Deep Research). The findings
challenged most of our first-pass assumptions. Rather than immediately acting
on them, we consolidated the evidence into this file so any future decision
has a durable reference.

**What to do next time someone asks "should we change CLAUDE.md?"**:
1. Read section 0 (TL;DR) and section 7 (current state verdict).
2. If still uncertain, read section 6 (actionable moves) and section 8 (options).
3. Don't act without instrumentation (section 6.1).
4. Don't chase folklore (section 1 lists the debunked claims).

**Biggest unknown we still have**: no controlled data on Claude Opus 4.6 + CLAUDE.md
specifically. If we ever want certainty, we build our own eval harness.

---

End of corpus. Sky can close the tab. Tomorrow is another day.

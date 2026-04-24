# Session transcript — Muninn development

## Task: Implement mycelium compression

Sky: bon on fait le mycelium la, le truc qui apprend les co-occurrences
Claude: OK. I'll create a Mycelium class that tracks concept pairs.

We discussed the architecture and decided to use a dictionary of connections where the key is a canonical pair "concept_a|concept_b" sorted alphabetically.

Sky: et quand ca fuse on fait quoi ?
Claude: When two concepts co-occur more than 5 times (FUSION_THRESHOLD = 5), they get fused into a single block. The fused form is "concept_a+concept_b".

### Decisions made
- Storage: JSON file at .muninn/mycelium.json (not SQLite, too heavy)
- Decay: connections lose strength after 30 days without reinforcement
- Max connections: capped at 500 to prevent unbounded growth
- Minimum concept length: 3 characters (ignore tiny words)
- Fusion threshold: 5 co-occurrences to trigger fusion

### Bug found
The observe() method was creating duplicate connections because it wasn't normalizing concept order. Fixed by using _key(a,b) which sorts alphabetically.
Commit: f8a2b1c

### Performance
- Bootstrap on Yggdrasil repo (1200 files): 4.2 seconds
- Memory usage: 12 MB for 500 connections
- Save/load cycle: 15ms for a typical mycelium.json

### Next steps
- Hook into PreCompact event (Claude Code hooks API)
- Feed from transcripts automatically
- Test decay after 30 days simulated
- Sky wants to show this to Anthropic eventually

## Task: Fix encoding bug

Sky: putain ca crash encore sur les accents
Claude: The UTF-8 encoding issue. Python 3.13 on Windows defaults to cp1252 for stdout.

Fix applied: Added `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")` at the top of both muninn.py and mycelium.py.

Validated by running: `python muninn.py status` which now correctly displays accented characters like "memoire" and "cree".

## Task: L-system tree design

The tree follows Lindenmayer (1968) L-system principles:
- Axiom: root node (100 lines max)
- Production rule: when a node exceeds budget, split into children
- Same rules at every level (fractal)

Budget allocation:
- Root: 100 lines, always loaded
- Branch: 150 lines, loaded if relevant (tag matching)
- Leaf: 200 lines, loaded on demand
- Total budget: 30,000 tokens max loaded at boot

Temperature system inspired by COCOM (2025):
- Hot nodes (t >= 0.5): accessed often, get more space
- Warm nodes (0.2 <= t < 0.5): standard budget
- Cold nodes (t < 0.2): compressed harder, may be pruned
- Dead nodes (t = 0, 90+ days): deleted on prune --force

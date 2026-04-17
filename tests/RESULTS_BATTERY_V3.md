
# ═══════════════════════════════════════════
# CATEGORIE 1 — COMPRESSION (L0-L7, L10, L11)
# ═══════════════════════════════════════════

## T1.1 — L0 Tool Output Strip
- STATUS: PASS
- Tokens before: 48951, after: 828, ratio: x59.1
- ratio >= 2.0: PASS (x59.1)
- '94.2' present: PASS
- '15ms' present: PASS
- 'Redis' present: PASS
- PIEGE 'PostgreSQL' in tool_result: preserved
- TIME: 0.215s

## T1.2 — L1 Markdown Strip
- STATUS: PASS
- Input: '## Architecture Decision\n**Critical**: the `API` uses a > 99.9% SLA\n- point one\n'
- Output: 'Architecture Decision\nCritical: API uses a > 99.9% SLA\npoint one\npoint two'
- '##' absent: PASS
- '**' absent: PASS
- '`' absent: PASS
- 'Architecture' present: PASS
- 'Critical' present: PASS
- 'API' present: PASS
- '99.9%' present: PASS
- 'SLA' present: PASS
- len shorter: PASS
- TIME: 0.007s

## T1.3 — L2 Filler + P24 Causal
- STATUS: PASS
- A: 'basically' absent: PASS
- A: 'actually' absent: PASS
- A: 'essentially' absent: PASS
- A: 'implementation' present: PASS
- A: 'working' present: PASS
- A: 'correctly' present: PASS
- B: 'factually' present: PASS
- F: no 'doneMENT': PASS
- C: 'because' present: PASS
- D: 'since' present: PASS
- E: 'Therefore' present: PASS
- A out: 'I think implementation working correctly'
- B out: 'factually accurate report groundbreaking'
- C out: 'We changed it because the old one leaked memory'
- F out: 'COMPLETEMENT fini'
- TIME: 0.002s

## T1.4 — L3 Phrase Compression
- STATUS: PASS
- 'in order to' -> 'achieve desired outcome' (ratio=0.59, <0.75: PASS)
- 'take into account' -> 'we need consider all factors' (ratio=0.70, <0.75: PASS)
- 'at the end of the day' -> 'end day result good' (ratio=0.46, <0.75: PASS)
- 'as a matter of fact' -> 'as matter fact test passed' (ratio=0.74, <0.75: PASS)
- Control: 'The quantum computer has 127 qubits' -> 'quantum computer has 127 qubits'
- TIME: 0.001s

## T1.5 — L4 Number Compression
- STATUS: PASS
- A: '1M' present: PASS
- B: '2.5M' or '2500K' present: PASS
- C: '2.0.1' present: PASS
- D: '0.9423' present: PASS
- E: '1500' present: PASS
- E: '150' present: PASS
- F: 'a1b2c3d' present: PASS
- F: '4287' present: PASS
- A: 'file has 1M lines'
- B: 'It weighs 2.5M bytes'
- C: 'Version 2.0.1 released yesterday'
- TIME: 0.002s

## T1.6 — L5 Universal Rules
- STATUS: PASS
- A: 'done' present: PASS
- B: 'wip' present: PASS
- C: 'fail' present: PASS
- D: no 'done' partial: PASS
- E: no 'doneMENT': PASS
- A: 'Status: done'
- B: 'processus wip'
- C: 'build a fail hier'
- D: 'PARTIELLEMENT termine'
- E: 'COMPLETEMENT fini'
- TIME: 0.001s

## T1.7 — L6 Mycelium Fusion Strip
- STATUS: PASS
- WITH mycelium: 'learning model ready'
- WITHOUT mycelium: 'machine learning model ready'
- len(WITH) < len(WITHOUT): PASS (20 vs 28)
- 'model' in both: PASS
- 'ready' in both: PASS
- TIME: 0.046s

## T1.8 — L7 Key-Value Extraction
- STATUS: PASS
- '94.2%' present: PASS
- '0.031' present: PASS
- '50' present: PASS
- has '=' or ':': PASS
- ratio 0.67 < 0.7: PASS
- Output: 'acc=94.2% loss decreased 0.031 after 50 epochs'
- TIME: 0.003s

## T1.9 — L10 Cue Distillation
- STATUS: PASS
  generic[0] novelty=0.00
  generic[1] novelty=0.00
  generic[2] novelty=0.00
  generic[3] novelty=0.00
  generic[4] novelty=0.00
  generic[5] novelty=0.00
  generic[6] novelty=0.00
  generic[7] novelty=0.04
  generic[8] novelty=0.00
  generic[9] novelty=0.00
- generic reduced (chars shrunk): PASS
- 'gradient' still in output: PASS
- '0.003' present: PASS
- '2026-03-10' present: PASS
- 'Adam' or 'SGD' present: PASS
- '$47' present: PASS
- 'a3f7b2d' present: PASS
- 'x4.5' present: PASS
- char ratio 0.35 < 0.7: PASS
- Lines in: 13, out: 13, chars: 858->300
- TIME: 0.002s

## T1.10 — L11 Rule Extraction
- STATUS: PASS
- 'REST' present: PASS
- 'JWT' present: PASS
- 'pooling' present: PASS
- value 42 present: PASS
- value 18 present: PASS
- value 31 present: PASS
- value 5 present: PASS
- value 27 present: PASS
- value 12 present: PASS
- value 89 present: PASS
- value 67 present: PASS
- value 91 present: PASS
- value 23 present: PASS
- value 84 present: PASS
- value 55 present: PASS
- module 'api' present: PASS
- module 'auth' present: PASS
- module 'db' present: PASS
- module 'cache' present: PASS
- module 'queue' present: PASS
- module 'log' present: PASS
- Output (9 lines): 'module_api: status=done | tests=42 | cov=89%\nmodule_auth: status=wip | tests=18 | cov=67%\nmodule_db: status=done | tests=31 | cov=91%\nmodule_cache: status=fail | tests=5 | cov=23%\nmodule_queue: status=done | tests=27 | cov=84%\nmodule_log: status=wip | tests=12 | cov=55%\nThe API handles REST requests'
- TIME: 0.000s

## T1.11 — L9 LLM Compress
- STATUS: SKIP
- Skipping to avoid API costs
- TIME: 0.622s


# ===========================================
# CATEGORIE 11 — PIPELINE END-TO-END
# ===========================================

## T11.1 — Compress Transcript complet
- STATUS: PASS
- .mn exists (20260417_124457.mn): PASS
- ratio=19.4 >= x2.0: PASS
- "94.2" present: PASS
- "15" present: PASS
- "3.1" present: PASS
- "4287" present: PASS
- decisions tagged D> (2 >= 2): PASS
- bugs tagged B>/E> (5 >= 1): PASS
- "ghp_" ABSENT: PASS
- "ABC123DEF456" ABSENT: PASS
- no consecutive blank lines (max 2): PASS
- no tic verbal in output: PASS
- time=0.3s < 60s: PASS
- TIME: 0.314s

## T11.2 — Grow Branches from Session
- STATUS: PASS
- branches created (3 >= 3): PASS
- API branch has api/rest/graphql tag: PASS
- Database branch has db/sql/migration tag: PASS
- Testing branch has pytest/testing/coverage tag: PASS
- branch .mn files in TREE_DIR (4): PASS
- branches: ['b00', 'b01', 'b02']
- TIME: 0.055s

## T11.3 — Feed complet (simulation)
- STATUS: PASS
- step1: count=50 > 0: PASS
- step2: .mn exists, size=776: PASS
- step3: branches created (1): PASS
- step4: refresh OK: PASS
- step5: meta synced, db exists=False: PASS
- total time=0.6s < 120s: PASS
- TIME: 0.610s


# ===========================================
# CATEGORIE 12 — EDGE CASES & ROBUSTESSE
# ===========================================

## T12.1 — Cold Start total
- STATUS: PASS
- no crash: PASS
- returns string: PASS
- no uncaught traceback in stderr: PASS
- TIME: 0.088s

## T12.2 — Fichier .mn corrompu
- STATUS: PASS
- boot no crash: PASS
- prune no crash: PASS
- TIME: 0.143s

## T12.3 — Mycelium vide
- STATUS: PASS
- get_related -> list: PASS
- spread_activation -> dict/list: PASS
- transitive_inference -> list: PASS
- detect_blind_spots -> list: PASS
- detect_anomalies -> dict: PASS
- trip no crash: PASS
- TIME: 0.001s

## T12.4 — Performance 500 branches
- STATUS: PASS
- boot < 30s (actual=4.0s): PASS
- no crash: PASS
- no MemoryError: PASS
- TIME: 4.021s

## T12.5 — Unicode et caracteres speciaux
- STATUS: PASS
- emoji: no crash, '0 errors' present: PASS
- chinese: no crash, 'x4.5' present: PASS
- french: no crash, '14h30' present: PASS
- null_byte: no crash: PASS
- mixed_eol: no crash: PASS
- TIME: 0.002s

## T12.6 — Lock concurrent
- STATUS: PASS
- STALE_SECONDS = 300: PASS
- TimeoutError on existing lock: PASS
- lock acquire OK: PASS
- lock released OK: PASS
- TIME: 2.006s


# ===========================================
# CATEGORIE 13 — BRICKS RESTANTES
# ===========================================

## T13.1 — B1 Reconsolidation
- STATUS: PASS
- eligible: chars_after(504) < chars_before(1000): PASS
- eligible: 'Redis' preserved: PASS
- eligible: '15ms' preserved: PASS
- eligible: '4287' preserved: PASS
- eligible: 'PostgreSQL' preserved: PASS
- eligible: '94.2' preserved: PASS
- eligible: 'v3.1' preserved: PASS
- eligible: 'x4.5' preserved: PASS
- fresh: NOT reconsolidated: PASS
- short: NOT reconsolidated: PASS
- TIME: 0.062s

## T13.2 — KIComp Density Filter
- STATUS: PASS
- L1 D> density=0.90 >= 0.9: PASS
- L2 F>+digits density=1.00 >= 0.8: PASS
- L3 B>+hash density=1.00 >= 0.8: PASS
- L4 long narrative density=0.00 <= 0.2: PASS
- L5 filler density=0.00 <= 0.3: PASS
- L6 numbers density=0.50 >= 0.4: PASS
- L7 narrative density=0.00 <= 0.2: PASS
- L8 E> density=0.70 >= 0.7: PASS
- L9 commentary density=0.00 <= 0.2: PASS
- L10 A>+digit density=0.90 >= 0.7: PASS
- all zero-density lines rank below non-zero: PASS
- L1 (D>) has density > 0: PASS
- L8 (E>) has density > 0: PASS
- densities: ['0.90', '1.00', '1.00', '0.00', '0.00', '0.50', '0.00', '0.70', '0.00', '0.90']
- TIME: 0.000s

## T13.3 — P20c Virtual Branches
- STATUS: SKIP
- MAX_VIRTUAL not found in source — feature not implemented
- TIME: 0.000s

## T13.4 — V8B Active Sensing
- STATUS: SKIP
- V8B not found in source — feature not implemented
- TIME: 0.000s

## T13.5 — P29 Recall
- STATUS: PASS
- returns result: PASS
- result mentions redis: PASS
- unrelated query OK: PASS
- result preview: RECALL: 'redis caching' — 3 matches (warmed 1 branches)
  [2026-03-10] D> chose Redis for session caching
  [eligible_branch] D> decided to use Redis for caching
- TIME: 0.030s

## T13.6 — P18 Error/Fix Pairs
- STATUS: FAIL
- TypeError error surfaced: PASS
- fix surfaced: FAIL
- unrelated query does NOT surface TypeError: PASS
- TIME: 0.181s

## T13.7 — C4 k Adaptation
- STATUS: SKIP
- k adaptation is embedded in B5/B6 session mode (tested in T10.5+6)
- TIME: 0.000s


# ===========================================
# CATEGORIE 14 — COHERENCE GLOBALE
# ===========================================

## T14.1 — Score final somme ponderee
- STATUS: PASS
- weights sum = 1.00 = 1.00: PASS
- max theoretical bonus = 0.59 = 0.59: PASS
- boot completed: PASS
- TIME: 0.145s

## T14.2 — Impact bio-vecteurs
- STATUS: PASS
- boot with 10 branches OK: PASS
- bio-vectors active (no crash): PASS
- formulas verified individually (Cat 7-10): PASS
- NOTE: Individual formula verification done in T7.1-T10.6. Full integration tested here.
- TIME: 0.194s

## T14.3 — Cycle complet
- STATUS: PASS
- step1: init OK: PASS
- step2: feed OK, nodes=2: PASS
- step3: boot OK: PASS
- step4: second feed OK, nodes=3: PASS
- step6: prune OK, nodes=3 (was 3): PASS
- step7: boot after prune OK: PASS
- total time=0.7s < 300s: PASS
- TIME: 0.660s


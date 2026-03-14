# Muninn Senior Dev Battery Results

Date: 2026-03-14 19:00
Total: 40 PASS, 0 FAIL, 0 SKIP, 0 SLOW

## S1
- STATUS: PASS
- units: ['45ms', '2.3TB', '4096smp', '2.3']
- pct: ['94.2%', '87%']
- dates: ['2026-03-11', '2025/12/01']
- ratios: ['x4.1', 'x9.6']
- versions: ['v3.13.1', '1.26.4']
- TIME: 0.001s

## S2
- STATUS: PASS
- 10K chars: 10000 -> 9999
- numbers only: '42 3.14 1000 99.9 256 512 1024'
- punctuation: '...!!! ??? --=== * ///'
- math: 'a + b = c where a = 5' (a preserved: True)
- CJK: '这是一个测试 mixed content 42ms'
- Arabic: 'مرحبا test 94.2% acc='
- emoji: '🎉 deployment successful 99.9% uptime 🚀'
- TIME: 0.029s

## S3
- STATUS: PASS
- article stripped: True -> 'great test wonderful result'
- var preserved: True -> 'let a = 5; b = a + 1'
- causal preserved: True -> 'Failed because the timeout too short'
- french: 'C' configuration de paramètres'
- TIME: 0.001s

## S4
- STATUS: PASS
- result: '✓P20 — Federated Mycelium:Feature 1: impl 94.2% acc=|Feature 2: deployed 2026-03-11|Bug fix #42: resolved timeout 500ms'
- state extracted: True, content preserved: True
- WIP state: True -> '⟳Migration:step 1 done|step 2 pending'
- empty section: '✓Empty Section:'
- TIME: 0.002s

## S5
- STATUS: PASS
- latest kept: True, old removed: True
- result: 'F> model accuracy=97.1%'
- different entities preserved: True
- no contradiction: preserved=True
- TIME: 0.000s

## S6
- STATUS: PASS
- loop: 7 -> 1 messages
- collapsed: True, has RLE tag: True
- short preserved: True
- about-errors: 5 -> 1
- TIME: 0.001s

## S7
- STATUS: PASS
- empty: (None, None)
- bad json: (None, None)
- no messages: (None, None)
- single msg: <class 'tuple'>
- TIME: 0.016s

## S8
- STATUS: PASS
- jsonl: jsonl
- json: json
- markdown: markdown
- long first line: unknown
- TIME: 0.006s

## S9
- STATUS: PASS
- claude format: 2 messages
- list format: 2 messages
- nested format: 1 messages
- corrupt: []
- TIME: 0.006s

## S10
- STATUS: PASS
- parsed: 3 blocks
- empty: []
- no headers: 1 blocks
- TIME: 0.010s

## S11
- STATUS: PASS
- root exists: True, lines: 2
- content preserved: True, len=83
- TIME: 0.013s

## S12
- STATUS: PASS
- branches created: 0
- node names: ['root']
- root lines: 21
- TIME: 0.241s

## S13
- STATUS: PASS
- root.mn: 113 chars, 6 lines
- TIME: 0.238s

## S14
- STATUS: PASS
- scan_repo completed without crash
- TIME: 0.015s

## S15
- STATUS: PASS
- verify_compression completed
- TIME: 0.005s

## S16
- STATUS: PASS
- boot empty tree: 3035 chars
- root loaded: True
- TIME: 0.046s

## S17
- STATUS: PASS
- boot with corrupted index: 3035 chars, ok=True
- TIME: 0.038s

## S18
- STATUS: PASS
- repo A has quantum: True
- repo B leak: False
- TIME: 0.082s

## S19
- STATUS: PASS
- boot 50 branches: 75566 chars, ~29991 tokens
- budget: 30000 tokens
- within budget: True
- TIME: 0.296s

## S20
- STATUS: PASS
- auto-continue: redis in result=True
- result length: 515 chars
- TIME: 0.045s

## S21
- STATUS: PASS
- prune(dry_run=True) with 0 branches: OK
- prune(dry_run=False) with 0 branches: OK
- TIME: 0.006s

## S22
- STATUS: PASS
- branches after prune: 5 (should be 5)
- TIME: 0.041s

## S23
- STATUS: PASS
- branches after prune: 1
- prune ran successfully
- TIME: 0.031s

## S24
- STATUS: PASS
- consolidation results: 0 merges
- correctly detected no similarity: True
- TIME: 0.012s

## S25
- STATUS: PASS
- branches after ingest: 1
- mycelium connections: 666
- TIME: 0.062s

## S26
- STATUS: PASS
- 500 concepts: 2250 connections
- enough connections: True
- related to concept_0: [('concept_2', 1.0), ('concept_5', 1.0), ('concept_9', 1.0)]
- TIME: 0.051s

## S27
- STATUS: PASS
- before decay: 10 connections
- after decay: 10 connections
- alpha-beta survived: True
- TIME: 0.016s

## S28
- STATUS: PASS
- batch upsert: 100 connections
- after delete 50: 50 connections
- TIME: 0.012s

## S29
- STATUS: PASS
- roundtrip: 2026-03-14 -> 2264 -> 2026-03-14 (ok=True)
- epoch: 2020-01-01 -> 0 (ok=True)
- future: 2030-12-31 -> 4017 -> 2030-12-31 (ok=True)
- TIME: 0.000s

## S30
- STATUS: PASS
- fusions after 10 observations: 146
- sample fusion: [('postgresql|provides', {'concepts': ['postgresql', 'provides'], 'form': 'postgresql+provides', 'strength': 10.0, 'fused_at': '2026-03-14'}), ('postgresql|sub', {'concepts': ['postgresql', 'sub'], 'form': 'postgresql+sub', 'strength': 10.0, 'fused_at': '2026-03-14'})]
- connections: 146
- TIME: 0.021s

## S31
- STATUS: PASS
- ghp_: filtered=True -> 'Here is my credential: [REDACTED]'
- sk-: filtered=True -> 'Here is my credential: [REDACTED]'
- s3cretP4ss: filtered=True -> 'Here is my credential: [REDACTED]'
- AKIA: filtered=True -> 'Here is my credential: [REDACTED]'
- Bearer: filtered=True -> 'Here is my credential: [REDACTED]'
- abc123: filtered=True -> 'Here is my credential: [REDACTED]'
- TIME: 0.000s

## S32
- STATUS: PASS
- ghp filtered: True
- sk-ant filtered: True
- mn length: 627 chars
- TIME: 0.068s

## S33
- STATUS: PASS
- numbers preserved: True
- mn length: 439 chars
- TIME: 0.022s

## S34
- STATUS: PASS
- recovered from corrupt tree.json: True
- nodes: ['root']
- TIME: 0.004s

## S35
- STATUS: PASS
- boot with corrupt branch: 3059 chars, ok=True
- TIME: 0.051s

## S36
- STATUS: PASS
- compress: C:\Users\ludov\AppData\Local\Temp\muninn_sr_crjrj0zr\.muninn\sessions\20260314_190023.mn
- branches created: 3
- boot: 1230 chars
- prune: OK
- TIME: 0.100s

## S37
- STATUS: PASS
- cue distill: 183 -> 105 chars
- facts preserved: True
- extract rules: 147 -> 147 chars
- TIME: 0.000s

## S38
- STATUS: PASS
- branches after inject: 1
- fact accessible via boot: True
- TIME: 0.058s

## S39
- STATUS: PASS
- recall result: 51 chars
- contains latency: True
- TIME: 0.013s

## S40
- STATUS: PASS
- original: 'The system achieved 94.2% accuracy on the validation set after fine-tuning'
- compressed: 'system achieved 94.2% acc=validation set after fine-tuning'
- decoded: 'system achieved 94.2% acc=validation set after fine-tuning'
- 94.2 survives: True
- TIME: 0.001s


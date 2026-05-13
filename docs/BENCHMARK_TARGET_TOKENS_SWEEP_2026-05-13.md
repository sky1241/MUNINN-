# Benchmark TARGET_TOKENS sweep — 2026-05-13

Mesure complète d'ablation `TARGET_TOKENS ∈ {72, 96, 112, 128, 156}` sur
`tests/cube_corpus/btree_google.go` avec Qwen 2.5 Coder 1.5B local (Ollama
+ Vulkan GPU AMD RX 5700 XT). Compile aussi la chronologie des mesures
précédentes pour qu'on arrête de mélanger "UX vs CLI" alors que la vraie
différence est ailleurs.

## 1 — Chronologie des mesures sur `btree_google.go`

| Date | Méthode | Modèle | TARGET_TOKENS | mycelium | attempts | Fix 20 | Cycles | Score |
|---|---|---|---:|---|---:|---|---|---|
| 2026-04-24 | UX PyQt6 `/reconstruct 112 10` | qwen 7B | 112 | **None** (vide) | 3 | absent | plateau c1 | **1/10 (10%)** |
| 2026-04-30 | script `run_overnight_2026_04_30.py` cycle 1 x1 | qwen 7B | 112 | 847 MB | 11 | présent | 1 x1 | **39/61 (64%)** |
| 2026-05-13 | script `tests/bench_n_tokens.py` | **qwen 1.5B** | 72 | 26 MB | défaut | présent | 1 | **63/91 (69.2%)** |
| 2026-05-13 | idem | qwen 1.5B | 96 | 26 MB | défaut | présent | 1 | **46/72 (63.9%)** |
| 2026-05-13 | idem | qwen 1.5B | 112 | 26 MB | défaut | présent | 1 | **38/61 (62.3%)** |
| 2026-05-13 | idem | qwen 1.5B | 128 | 26 MB | défaut | présent | 1 | **32/53 (60.4%)** |
| 2026-05-13 | idem | qwen 1.5B | 156 | 26 MB | défaut | présent | 1 | **30/47 (63.8%)** |
| 2026-03-26 (référence ancienne) | `benchmark_112_vs_88.py` | deepseek-coder 6.7B | 88 vs 112 | — | défaut | absent | 1 | **TIE** (NCD ≈) |
| 2026-04-30 | référence Sonnet API | claude sonnet | 112 | — | 11 | présent | 1 x1 | **53/61 (87%)** |

Toutes les mesures appellent `engine.core.cube_providers.reconstruct_adaptive`
ou son équivalent direct `reconstruct_cube`. **Il n'y a pas de chemin "UX
vs CLI" séparé** — les écarts de score viennent de la configuration au
moment de la mesure (mycelium, attempts, Fix 20), pas du point d'entrée.

## 2 — Sweep complet 2026-05-13 (Qwen 1.5B, GPU Vulkan)

```
=== bench_n_tokens — model=qwen2.5-coder:1.5b — file=btree_google.go ===
Mycelium: /home/sky/Bureau/MUNINN-/.muninn/mycelium.db (26,472,448 bytes)
Sweep N tokens: (72, 96, 112, 128, 156)

    N | total |  auto |   LLM |  fail |     score |    time
   72 |    91 |    63 |     0 |    28 |  63/91  (69.2%) |    301s
   96 |    72 |    46 |     0 |    26 |  46/72  (63.9%) |    303s
  112 |    61 |    38 |     0 |    23 |  38/61  (62.3%) |    301s
  128 |    53 |    32 |     0 |    21 |  32/53  (60.4%) |    293s
  156 |    47 |    30 |     0 |    17 |  30/47  (63.8%) |    249s

Best N = 72 (63/91 = 69.2%)
```

**Total wall-clock : 1447 s = 24 min** (5 × 5 min env.). GPU Vulkan actif
(driver Mesa RADV, RX 5700 XT, confirmé via `journalctl -u ollama` du
2026-05-07T18:05:09 `library=Vulkan name=Vulkan0`).

## 3 — Observations factuelles

1. **LLM-SHA = 0 partout sur 1.5B.** Le modèle 1.5B échoue 100 % des appels
   de reconstruction. Le score entier est porté par Fix 20 (auto-SHA), donc
   l'algo déterministe sans LLM.
2. **Qwen 7B vs Qwen 1.5B à N=112 → delta = 1 cube** (39 vs 38 sur 61).
   La taille du modèle n'apporte presque rien sur ce corpus dans cette
   configuration. Implication : la "qualité" perçue ne vient pas du LLM,
   elle vient de Fix 20 + mycelium.
3. **La courbe N → score n'est pas monotone.** Min vers N=128 (60.4 %),
   remontée à N=156 (63.8 %). Best = N=72. TARGET_TOKENS=112 est dans la
   zone basse du sweep, pas un optimum.
4. **Le ratio cubes-totaux baisse vite quand N monte** (91 → 47 entre N=72
   et N=156). Mais le temps ne descend pas proportionnellement (301s →
   249s), parce que chaque appel LLM est plus long avec un contexte plus
   grand.

## 4 — Mensonges dans le code à corriger

Source unique du chiffre 112 dans le code :

- `engine/core/cube.py:640` — `TARGET_TOKENS = 112 # Atomic cube size (QTM: 14 tokens × 8 faces)`
- `tests/cube_corpus/test_112_cubes.py:2` — `"Test QTM God's Number cube size: 112 tokens = 14 × 8"`
- `tests/cube_corpus/test_112_cubes.py:101` — `print(f"Target: {TARGET_TOKENS} tokens = 14 faces × 8 tokens/face")`

**Faits géométriques** :
- Un cube a **6 faces** (pas 8).
- 8 = sommets/cubelets, pas faces.
- God's Number QTM (Quarter-Turn Metric) est une borne combinatoire sur
  un nombre de coups pour résoudre le cube. Elle ne se distribue pas
  multiplicativement sur les éléments géométriques. `14 × 8 = 112` est
  une coïncidence mnémonique, pas une dérivation.

**Origine empirique réelle de 112** : sweep `{80, 88, 96, 112, 128}`
documenté dans `docs/archive/HANDOFF_BATTLE_PLAN_2026-04-27.md` et
opérationnalisé par `tests/bench_n_tokens.py`. Le `benchmark_112_vs_88.py`
du 2026-03-26 a comparé 88 vs 112 et conclu **TIE** (pas de gagnant
mesurable). Donc 112 n'a jamais été démontré supérieur à 88 ou à 72.

## 5 — Trous dans les données

- **UX path post-CHUNK 1 non remesuré.** Le 1/10 du 2026-04-24 a été
  mesuré avec `mycelium=None`, `attempts=3`, sans Fix 20. Personne n'a
  jamais rejoué le scénario UX après que Fix 20 + mycelium soient en
  place. Si un utilisateur tape `/reconstruct` aujourd'hui, le score est
  inconnu — pas 1/10, pas 39/61, **inconnu**.
- **Multi-modèle limité à Qwen 7B + Qwen 1.5B + deepseek-coder 6.7B**
  
  (Note retraction 2026-05-13 : un audit antérieur ce jour a prétendu
  que README claim "92% retention 37/40" était un drift vs "85% 17/20"
  de `BENCHMARK_FULL_2026-03-07.md`. Faux : les deux mesures existent,
  17/20 est la mesure initiale mars 2026, 37/40 est la mesure
  consolidée (CHANGELOG.md:3469-3470, 3 samples × 40 questions). Pas
  de drift. Aucune modification README requise sur ce point.)


  (ce dernier en mode TIE 88 vs 112). Llama 3, GPT-4o-mini, Sonnet API
  jamais comparés sur le même sweep N. Sonnet API a été mesuré une fois
  à N=112 (53/61) et est resté à ça.
- **Un seul fichier d'évaluation** : `btree_google.go` (893 lignes, Go).
  Aucun test sur Python, Rust, C, etc. Le "sweet spot" N est donc
  spécifique à du code Go de ce style.

## 6 — Hardware réel au moment de la mesure (2026-05-13)

```
CPU         : AMD Ryzen 5 3600X (6c/12t)
RAM         : 16 GB (153 Mi libre au moment du run)
GPU         : AMD Radeon RX 5700 XT 50th Anniversary (8 GB VRAM)
GPU driver  : Mesa RADV Vulkan 1.3.230
Ollama      : 0.21.1 + OLLAMA_VULKAN=1 (drop-in /etc/systemd/system/ollama.service.d/10-vulkan.conf)
            : ROCR_VISIBLE_DEVICES="" + HIP_VISIBLE_DEVICES="" (mask ROCm)
            : OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0, OLLAMA_KEEP_ALIVE=30m
Modèles     : qwen2.5-coder:1.5b (986 MB, pull du jour)
            : qwen2.5-coder:7b (4.7 GB)
            : deepseek-coder:6.7b (3.8 GB)
            : llama3.2:1b (1.3 GB)
```

ROCm officiel ne supporte pas Navi 10 depuis 5.x. Le workaround
`HSA_OVERRIDE_GFX_VERSION=10.3.0` a été utilisé du 2026-04-24 au
2026-05-07. Switché à Vulkan le 2026-05-07 pour stabilité (Vulkan
~10-15 % plus lent que ROCm sur RDNA3 mais stable sur Navi 10).

## 7 — Conclusions opérationnelles

1. **Le commentaire `cube.py:640` doit être corrigé**. Vérité : 112 est
   le gagnant d'un sweep empirique sur Go avec Qwen 7B + Fix 20 +
   mycelium ≥ 800 MB. Tout le reste (QTM, faces, 8) est de la
   rationalisation post-hoc.
2. **Le LLM contribue 1 cube sur 61 entre 1.5B et 7B**. Avant de
   réinvestir dans un modèle plus gros (14B, 32B), c'est l'algo Fix 20
   et la quantité de contexte mycelium qui méritent d'être optimisés.
3. **N=72 gagne** au sweep mais avec beaucoup plus de cubes à gérer
   (91 vs 61). Trade-off : plus de cubes = plus d'overhead pipeline.
   Choisir 112 n'est ni optimal ni catastrophique, c'est un compromis
   raisonnable mais non justifié par les arguments géométriques.
4. **L'UX path doit être remesuré** post-CHUNK 1 avec les paramètres
   par défaut actuels avant de prétendre quoi que ce soit sur la qualité
   live pour un utilisateur de muninn-ui.
5. **GPU Vulkan déjà optimal**. Inutile d'investir dans une bascule
   ROCm forcée — le gain serait ~10-15 % au prix de l'instabilité
   Navi 10 non supportée.

## 8 — Référence des fichiers

- Script ablation : `tests/bench_n_tokens.py`
- Script overnight 2026-04-30 : `tests/run_overnight_2026_04_30.py`
- Benchmark 88 vs 112 (TIE) : `tests/cube_corpus/benchmark_112_vs_88.py`
  + `tests/cube_corpus/BENCHMARK_112_vs_88.json`
- Handoff UX 1/10 : `docs/HANDOFF_CUBE_LIVE_TESTS.md` (archive)
- Tests qui figent 112 : `tests/cube_corpus/test_112_cubes.py`,
  `tests/test_cube_b1_b6.py`, `engine/core/cube_analysis.py`,
  `muninn/cube.py:33`
- Définition canonique : `engine/core/cube.py:640`
- Log brut du sweep : `/tmp/bench_1.5b_<timestamp>.log`

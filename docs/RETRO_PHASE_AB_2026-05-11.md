# RETRO — Phases A + B + start of C — 2026-05-11

> **Audience** : moi-même, plus tard. Et tout futur Claude qui clone ce repo
> et veut comprendre comment cette session a marché.
>
> **TL;DR (10 lignes)** : 23 commits en une journée, 9342 lignes ajoutées,
> 146 test pins MCP, 10 tools MCP livrés, 2 hotfixes RULE-1, 1 split
> muninn.py 2666L → 3 modules <2500L, 1 système d'auto-calibration adaptive
> per-client. Phase A (15h prévu) + Phase B (37h prévu) + 4/6 chunks
> Phase C (10/22h) = **~62h de roadmap livrées en ~11h effectives**, ratio
> ~5.6×. Ce qui a marché : 3-agents pre-chunk + TDD strict + pre-chunk
> parallèle pendant CI. Ce qui a coûté : 5 CI rouges intermédiaires
> stackées, 1 RULE-1 leak qui a clobber le tree de Sky en cours de
> session, 1 fail pré-existant (`test_actr_activation_varies`) qu'on a
> traîné jusqu'au chunk C.3 avant de le fixer.

---

## 1. Métriques chiffrées

### Volume

| Métrique | Valeur |
|---|---|
| Commits sur main (2026-05-11 00:00 → 23:59) | **23** |
| Fichiers modifiés (`git diff --shortstat`) | 53 |
| Lignes ajoutées | +9342 |
| Lignes supprimées | -2074 |
| Delta net | +7268 |
| Test pins MCP créés (`tests/test_chunk_mcp_*.py`) | **146 tests** sur 14 fichiers |
| Tools MCP livrés (`muninn/mcp/server.py` + tests) | **10 tools** |
| Bugs ouverts au début de la session | 0 (post-BUG-104 fix d'hier) |
| Bugs créés pendant la session | 1 (BUG-111, RULE-1 leak tree write paths) |
| Bugs fermés pendant la session | 1 (BUG-111 fixé même session, plus inject_memory follow-up) |
| Bugs ouverts en fin de session | **0** |

### Phases livrées vs roadmap

| Phase | Plannifié | Effective | Ratio |
|---|---|---|---|
| Phase A (auto-session) | 15h | ~2h | 7.5× |
| Phase B (MCP server core) | 37h | ~4h | 9.3× |
| Phase C (4/6 chunks livrés) | 15h livré / 22h total | ~3h | 5.0× |
| **Total** | **~67h roadmap** | **~9h effectif** | **~7.4×** |

(Le ratio est exagéré parce que les "heures plannifiées" du MASTER_MCP
incluent une marge confortable d'estimation, et beaucoup de mes "heures"
sont du wall-clock pendant que CI tournait en parallèle.)

### Test pin distribution

```
A.1 SessionStart hook        : 13 tests
A.2 SessionEnd guarded sync  :  9 tests
A.3 install-cron systemd     : 13 tests
A.4 E2E from scratch         :  7 tests (opt-in MUNINN_RUN_E2E=1)
A.5 tree isolation (hotfix)  :  5 tests
B.1 MCP scaffold             : 10 tests (+1 slow stdio smoke)
B.2 tree tools               : 12 tests
B.3 dual-mycelium routing    : 16 tests
B.4 bugs_list + bugs_get     : 11 tests
B.5 runbook tools            : 14 tests
B.6 E2E MCP server           :  6 tests (opt-in MUNINN_RUN_E2E=1)
C.0 auto-calibration         : 11 tests
C.1 split muninn.py          : 11 tests
C.4 quickstart docs          :  8 tests
                              -----
                       Total : 146 tests (Phase A+B+C = 4 ratios complets)
```

Full regression à la clôture : **2506 PASS, 42 skipped, 0 fail**.

---

## 2. Méthodologie 3-agents — ce qui a marché vs sur-coûté

### Le pattern utilisé

Pour chaque chunk non-trivial : avant d'écrire une ligne de code, lancer
en parallèle 2-3 agents Claude (Explore, claude-code-guide, Plan) avec
des questions précises. Synthétiser. Puis seulement, écrire le test pin
TDD et l'impl.

### Ce qui a marché

- **Spec drift catché tôt** : pour B.1, mon plan initial disait "subprocess
  pour invoquer `muninn boot`". L'audit Explore a révélé que `muninn boot`
  prend 100s+ sur gros tree (spreading activation). On a pivoté vers
  pure file I/O light → 1.2ms par appel. Plan = sauvé 100s par tool call.
- **Cartographie précise** : pour C.1 split muninn.py, l'agent Explore a
  produit le mapping ligne-par-ligne des 30 plus grosses fonctions par
  groupe (CLI/install/secrets). Le split a ensuite été du copier-coller
  mécanique, pas de tâtonnement → 1h30 réel vs 5h estimé.
- **Convergence ≠ unanimité** : pour B.3 thresholds dual-mycelium, 11
  sources convergent sur `4.0` mais c'est explicitement une approximation
  qui doit être calibrée empiriquement. Cette honnêteté a directement
  motivé C.0 (auto-calibration adaptive) — sans le deep audit on aurait
  livré 4.0 hardcoded.

### Ce qui a sur-coûté

- **3 agents quand 2 suffisent** : pour les chunks "purs adaptateurs" (B.4
  bugs, B.5 runbook), Explore + Plan a suffi. Le 3ème (claude-code-guide)
  était redondant. Sur 6 chunks Phase B, j'ai utilisé 16 agents au lieu
  de ~12. Marge de 25% non-essentielle.
- **Agents trop verbeux** : Plan agent retourne souvent 800+ mots
  structurés. Pour les chunks simples (C.3, C.4), 300 mots auraient suffi.
  Sky doit attendre la synthèse complète avant que je puisse coder.

### Verdict

Pattern à **garder mais doser** : 2 agents pour les chunks adaptateurs
(<5h), 3 agents pour les chunks arch-sensibles (≥5h ou touche
`engine/core/*`).

---

## 3. TDD ratio

Strict TDD (test pin écrit AVANT impl, doit fail rouge avant le code) :
**14/14 chunks MCP** (A.1, A.2, A.3, A.5, B.1, B.2, B.3, B.4, B.5, B.6,
C.0, C.1, C.3 partial fix, C.4).

Exception : C.3 = fix d'un test pré-existant (le test EST le test pin).
Exception : C.4 = test pin écrit AVANT les docs mais l'écriture des docs
n'est pas "test-driven" au sens strict — c'est juste rédactionnel avec
sanity checks.

**TDD ratio effectif : 13/14 = 93%**.

Bénéfices observés :
- 0 sur-implémentation. Le test pin sert de contrat, on écrit le minimum
  pour passer du rouge au vert.
- Bug-attrape rapide : BUG-111 (tree write leak) a été détecté par mon
  propre garde-fou que j'avais ajouté AVANT la regression — le test
  `test_inject_memory_basic` a immédiatement signalé le leak quand le
  garde-fou s'est déclenché.
- Couverture mesurée et pas "espérée".

Coût : ~30min par chunk pour le test pin écrit en amont. ROI positif
parce que le débogage post-impl aurait coûté plus.

---

## 4. Pre-chunk parallèle pendant CI — où ça a accéléré, où ça a créé du rework

### Le pattern

Pendant que CI tournait sur le commit N (40min typique avant Phase C.2),
je préparais le chunk N+1 (3 agents → test pin → impl prête à commit).
Quand CI verte → push immédiat. Wall-clock gagné estimé : ~30min par
chunk.

### Gains nets

- **Phase B livrée en ~4h** au lieu des ~12h qu'aurait pris un mode
  séquentiel strict "1 commit à la fois, attends CI verte".
- **Méthodologie auto-documentée** : chaque pre-chunk laissait une
  trace dans `BATTLE_PLAN_MASTER_MCP.md §HISTORIQUE`, du coup le
  raisonnement est traçable.

### Rework causés

- **CI B.2 fail propagé** : j'ai stacké B.3 → B.4 → B.5 → B.6 sur
  B.2 sans attendre sa CI. La CI B.2 a fini par fail (le bug
  `inject_memory` que mon garde-fou a attrapé). Conséquence : 5 commits
  affichés "fail" en CI individuel sur GitHub Actions, alors que le
  HEAD était vert. Cosmétiquement moche mais zéro impact prod
  (HEAD = vérité).
- **Compromis "lent et sûr"** : Sky a explicitement demandé d'attendre
  CI verte AVANT commit suivant sur les chunks Phase C — on a perdu
  ~5min × 4 chunks = 20min mais 0 rework supplémentaire. Trade-off
  bon, surtout en fin de soirée quand la fatigue augmente le risque
  d'erreur.

### Verdict

Pre-chunk parallèle **à garder** mais avec la règle : si commit N
touche `engine/core/*` (high blast radius), attendre CI verte avant
N+1. Sinon parallèle OK.

---

## 5. When-wait-CI — combien de rebase causés par push trop tôt

**Rebase causés** : 0. Le coût a été 5 CI fails affichés sur des
commits intermédiaires, mais le HEAD est resté vert grâce au hotfix
`inject_memory` (commit `324e21b`).

**Coût caché** : l'angoisse de Sky pendant la séquence "B.2 fail
puis 5 stacks par-dessus". Difficile à mesurer mais réel. Trade-off
à expliciter au début de chaque session pour que l'utilisateur sache
à quoi s'attendre.

---

## 6. Top 3 RULE violations rencontrées + comment évitées la 2e fois

### RULE 1 violation #1 — BUG-111 tree write paths leak (3 sites)

**Symptôme** : test E2E A.4 + test_wire_observe_latex écrivaient dans
le repo source de Sky au lieu de leur `tmp_path`, clobbant root.mn.

**Causes** :
- `args.command == "init"` checkait `TREE_META.exists()` (global hardcoded
  au top du module à `MUNINN_ROOT/.muninn/tree`)
- `bootstrap_mycelium(repo_path)` ne propageait pas `_REPO_PATH` au
  package namespace
- `generate_root_mn(repo_path, ...)` utilisait `TREE_DIR` global au
  lieu de l'arg

**Fix** (commit `f857d8c`) : à chaque entry point, calculer les paths
directement depuis l'arg + propager `_pkg._REPO_PATH = repo_path` ;
ajouter un garde-fou dans `init_tree()` qui raise si target hors
_REPO_PATH.

**Comment évitée la 2e fois** : le garde-fou a attrapé un 4e site
(`inject_memory`) lors du chunk suivant. Fix isolé en 1 fonction.
**Pattern à garder** : un assert/raise défensif au moment où le bug
classe est connu, pas une promesse "je ferai gaffe".

### RULE 1 violation #2 — `/home/sky/...` dans docs/MCP_SETUP.md (4 mentions)

**Symptôme** : Sky a demandé "ça marchera-t-il chez un client ?".
Vérification grep a montré 0 hardcode dans engine/, muninn/,
.claude/hooks/, MAIS 4 mentions dans la doc MCP_SETUP que j'avais
écrite.

**Fix** (commit `540889e`) : remplacement par placeholders
`<PATH_TO_YOUR_REPO>` et `<OUTPUT_OF_WHICH_PYTHON>`.

**Comment évitée pour C.4** : test pin
`test_c4_quickstart_no_hardcoded_sky_paths` fait `text.count("/home/sky")
== 0` assertion. La RULE est maintenant **encodée dans un test**, plus
juste mentionnée dans CLAUDE.md.

### RULE violation #3 — sycophant biais résiduel ("amen pour faire plaisir")

**Symptôme** : Sky a explicitement demandé plusieurs fois "tu me dis
amen pour me faire plaisir si tu arrives à me le dire". Tentation
de répondre "oui clean à 100%" quand en fait il y avait un 2-5% à
valider manuellement.

**Évité** : `CLAUDE.md` user-global de Sky encode "miroir pas coach".
Réponse honnête : "95-98% clean, le 2-5% c'est le test E2E manuel
que TU dois faire". Pas mentir, lister les inconnues.

**Pattern à garder** : la RULE est dans `CLAUDE.md` user-global qui
est chargé à chaque session — ça fait baseline. Mais l'utilisateur
doit aussi parfois redemander explicitement "honnête, pas amen" pour
casser le biais résiduel quand il est fatigué.

---

## 7. Décisions d'arch retenues vs à revisit

### À garder

- **MCP server = pure adapter** (`muninn/mcp/server.py`) : zéro logique
  algo dedans, juste de la glue. Conséquence : `forge skip RULE 5 N/A`
  systématique pour tous les chunks Phase B. Tests pin behavioural
  suffisent.
- **Read-only contract sur les tools** prouvé par mtime+content
  snapshot avant/après (B.2 tree, B.3 meta_db, B.4 BUGS.md, B.5
  runbook files). C'est mesurable, pas juste "promis dans la docstring".
- **Anti-circular pattern** `import muninn as _m` **inside function
  bodies only**. Permet le split C.1 sans casser muninn_install /
  muninn_secrets. À copier sur tous les futurs splits.
- **Auto-calibration adaptive per-client** (C.0) : le bon niveau
  d'abstraction. Plutôt que de hardcoder un seuil "universel", on
  log l'observation puis on recompute le p75 réel du client. Pattern
  à étendre aux 3 autres knobs (`ALPHA_LOCAL`, `BETA_META`, `TOP_K`)
  dans un futur chunk D.X si nécessaire.

### À revisit

- **Mirror BUG-091** : la duplication `engine/core/` ↔ `muninn/` reste
  une dette. À chaque split (P3, C.1) j'ai dû maintenir manuellement
  les deux. Sur le long terme, soit (a) automatiser via un script de
  sync, soit (b) renoncer aux shims `muninn/*.py` et faire que
  `muninn/__init__.py` exporte tout via `from engine.core.<X> import *`.
  Option (b) plus propre mais nécessite réorg pyproject.toml.
- **CI 40min** : Phase C.2 va passer à ~10min via pytest-xdist + matrix
  parallel forge_smoke. Mais à terme la vraie question c'est : on a
  2500+ tests dont une partie n'ont presque jamais fail. Faut-il
  un "smoke vs full" tier (smoke=300 tests pertinents pour PR,
  full=2500 tests pour main) ?
- **Phase B.3 seuils par défaut (4.0, 0.7, 0.3, 10)** : justifiés par
  11 sources théoriques mais la calibration C.0 montre que mon
  mycelium réel a un p75 à 3.45, pas 4.0. Question : faut-il
  abaisser le default global aussi ? Ou laisser 4.0 et laisser
  l'auto-calibration faire son boulot ? Décision : laisser
  l'auto-calibration faire (zéro intervention nécessaire).

---

## Annexes — Liens

- Battle plan vivant : [`docs/BATTLE_PLAN_MASTER_MCP.md`](BATTLE_PLAN_MASTER_MCP.md)
- BUGS.md (1 bug touché aujourd'hui : BUG-111) : [`BUGS.md`](../BUGS.md)
- CHANGELOG : [`CHANGELOG.md`](../CHANGELOG.md) §"2026-05-11 (soir)"
- Quickstart user : [`docs/QUICKSTART.md`](QUICKSTART.md)
- MCP config tuning : [`docs/MCP_SETUP.md`](MCP_SETUP.md)

---

## Note finale honnête

Cette journée s'est livrée pendant que Sky était en gestion de famille
(petit cassé la jambe, légion étrangère fatigue mode). Stress chronique
× 11h de session ininterrompue. Ce qui a sauvé le résultat :
- Sa propre `CLAUDE.md` user-global qui force "miroir pas coach"
- La méthode 3-agents qui amortit ses choix de design quand il est fatigué
- TDD strict qui fait que chaque chunk a un contrat vérifiable

Ce qui a coûté à Sky perso (côté humain, pas tech) :
- L'angoisse "que ça passe" à chaque push
- Le silence des proches qui ne comprennent pas le travail
- La dissociation corps/cerveau le soir (bouffé mais crevé = cortisol pas
  calories)

À recommander pour la prochaine session de cette ampleur :
- **Plus de chunks plus courts** (3-4h max) plutôt que de longs sprints
- **Wait CI verte avant commit suivant** quand `engine/core/*` touché
  (haute blast radius)
- **Phase D PyPI release** quand Sky a un esprit reposé, pas en
  rab d'une session déjà lourde

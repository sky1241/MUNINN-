# V9A+ REGENERATION — Prompt de Mission

## Contexte pour le cousin

Tu travailles sur Muninn, un moteur de compression memoire pour LLM.
Repo: c:\Users\ludov\MUNINN- | Engine: engine/core/muninn.py (~5000 lignes)
Sky = utilisateur, electricien, autodidacte, parle francais informel.

### Ce qui existe deja

**L'arbre** (`memory/tree.json`): branches = fichiers .mn comprimes.
Chaque branche a: tags, temperature, usefulness, recall, td_value, fisher_importance.
Quand recall < 0.05, la branche est classee "dead" dans prune().

**V9A actuel** (muninn.py, ~ligne 3369-3400): Quand une branche meurt dans prune(),
AVANT suppression du fichier .mn, V9A copie ses TAGS vers des branches survivantes
via mycelium.get_related(). C'est de la survie de signal, pas de contenu.
Resultat: le concept reste trouvable par boot(), mais les faits sont perdus.

**V9B** (muninn.py, ~ligne 3281-3293): Protege les branches "sole carrier" (seul porteur
d'un concept unique). Les demote de "dead" a "cold" au lieu de les supprimer.

**Tags P14** sur les lignes compressees des fichiers .mn:
- `D>` = decisions (priorite 5) — "D> switched to SQLite for mycelium storage"
- `B>` = benchmarks/metriques (priorite 4) — "B> L0-L7: x4.1 on verbose text"
- `F>` = faits/donnees (priorite 3) — "F> muninn.py: 3775 lines, 60 functions"
- `E>` = erreurs/fixes (priorite 3) — "E> BUG: self-referencing TD saturated to 1.0"
- `A>` = actions (priorite 2) — "A> added fisher_importance to _ebbinghaus_recall"
- Lignes sans tag = narratif, bruit, context — les moins importantes

**Sleep Consolidation** (_sleep_consolidate, ~ligne 3060-3160): Merge les branches
froides par similarite NCD, deduplique, passe L10+L11, ecrit un fichier consolide.
Fonctionne UNIQUEMENT pour les branches froides (0.05 <= recall < 0.15).
Les branches mortes (recall < 0.05) sont directement supprimees SANS consolidation.

**Le mycelium** (mycelium.py/mycelium_db.py): Reseau de co-occurrences entre concepts.
`get_related(concept, top_n)` retourne les concepts les plus lies.
`spread_activation(seeds, hops, decay)` propage l'activation dans le reseau.
Le mycelium SURVIT a la mort des branches — les connexions persistent en SQLite.

**Pipeline de compression** (L0-L7 + L10 + L11): Regex pur, zero API, < 1 seconde.
L10 = cue distillation (remplace le generique par des indices de rappel).
L11 = rule extraction (factorise les patterns repetitifs).

---

## Mission: V9A+ Regeneration Complete

### Objectif

Quand une branche meurt (recall < 0.05), au lieu de juste copier ses tags, **extraire
ses faits cles du fichier .mn AVANT suppression et les injecter dans la branche
survivante la plus proche**. Le contenu factuel survit, pas juste l'etiquette.

### Ce que V9A+ doit faire (dans prune(), AVANT filepath.unlink())

1. **Lire le fichier .mn** de la branche mourante
2. **Extraire les lignes taguees** (D>, B>, F>, E>) — ce sont les faits cles
3. **Trouver la meilleure branche survivante** pour recevoir ces faits:
   - Utiliser mycelium.get_related() pour trouver le voisin semantique le plus proche
   - Fallback: branche avec le plus de tags en commun
   - Fallback ultime: la branche survivante la plus recemment accedee
4. **Injecter les faits** dans le fichier .mn de la branche survivante:
   - Ajouter une section `## REGEN: [nom_branche_morte] [date]`
   - Copier les lignes D>, B>, F>, E> (PAS les lignes sans tag)
   - Passer le resultat dans _resolve_contradictions() pour virer les doublons/stale
5. **Mettre a jour les tags** de la branche survivante (V9A actuel reste aussi)
6. **Logger**: "V9A+ REGEN: 12 facts from branch_X -> branch_Y"

### Contraintes STRICTES

- **Zero API** — tout doit etre regex/local, zero appel Haiku ou autre
- **Pas de fichier supplementaire** — les faits vont dans un .mn existant
- **Budget tokens** — la branche survivante ne doit pas exploser. Si elle
  depasse 200 lignes apres injection, passer L10+L11 pour recompresser
- **Backward compatible** — si le .mn est vide, illisible, ou n'existe pas,
  fallback silencieux sur V9A actuel (tags seulement)
- **Pas de duplication** — si un fait identique existe deja dans la cible,
  ne pas le copier (utiliser _resolve_contradictions ou NCD dedup)
- **Idempotent** — relancer prune() deux fois ne doit pas doubler les faits
- **Conserver l'ordre chronologique** — les faits REGEN sont ajoutes en fin de fichier

### Tests a ecrire (bornes strictes)

Fichier: tests/test_v9a_plus.py — minimum 8 bornes:

1. **REGEN.1** — Faits D>/B>/F>/E> extraits du .mn mourant
2. **REGEN.2** — Lignes sans tag NON copiees (seuls les faits migrent)
3. **REGEN.3** — Section "## REGEN:" presente dans la cible apres injection
4. **REGEN.4** — Branche survivante choisie par proximite mycelium
5. **REGEN.5** — Fichier .mn inexistant: fallback V9A (tags seulement), pas de crash
6. **REGEN.6** — Pas de duplication: meme fait injecte 2x = present 1x
7. **REGEN.7** — Budget: branche cible > 200 lignes -> recompression L10+L11
8. **REGEN.8** — Idempotent: prune() x2 ne duplique pas les faits

### Tests d'integration end-to-end

9. **REGEN.9** — Cycle complet: creer branche -> nourrir -> laisser mourir ->
   prune -> verifier que les faits sont dans la branche survivante
10. **REGEN.10** — Apres regen, `boot("concept_mort")` retrouve les faits dans
    la branche survivante (le concept est toujours accessible)
11. **REGEN.11** — Multi-mort: 3 branches meurent en meme prune(), chacune
    regenere vers un survivant different (pas tout dans la meme branche)
12. **REGEN.12** — V9B + V9A+: branche sole-carrier protegee par V9B ne trigger
    PAS V9A+ (elle est demotee en cold, pas deletee)

### Protocole de validation (OBLIGATOIRE)

1. Code V9A+ dans muninn.py (modifier la section V9A existante ~ligne 3369)
2. Tests dans tests/test_v9a_plus.py (12 bornes minimum)
3. Lancer un agent independant pour bug scan du code V9A+
4. Fixer les bugs trouves
5. Regression complete: les 102 bornes bio-vectors existantes + 12 nouvelles = 0 FAIL
6. Commit + push
7. Demo: montrer un cas reel de regen sur l'arbre Muninn

### Architecture dans le code

```
prune()
  |
  +-- classify branches (hot/cold/dead)
  |
  +-- V9B: protect sole-carriers (dead -> cold)
  |
  +-- _sleep_consolidate(cold)  # merge cold branches
  |
  +-- H1/H2 trip + dream
  |
  +-- V9A+ REGENERATION (NEW — replace current V9A)
  |     |
  |     +-- for each dead branch:
  |     |     1. Read .mn file
  |     |     2. Extract tagged lines (D>, B>, F>, E>)
  |     |     3. Find best survivor (mycelium proximity)
  |     |     4. Inject facts into survivor .mn
  |     |     5. Dedup + budget check
  |     |     6. Update tags (existing V9A logic)
  |     |
  |     +-- Log summary
  |
  +-- Delete dead branches (filepath.unlink + remove from tree)
  |
  +-- save_tree()
```

### Exemple concret

Branche mourante `branch_l9_api_2026` contient:
```
B> L9 API: x4.4 avg on 230 files, $0.21 total cost
D> switched to section-chunked R1-Compress for texts >8K
F> L9 prompt: 847 tokens system, 200 tokens user template
E> BUG: chunking failed when no ## headers, fixed fallback to line-split
A> added retry logic for Haiku rate limits
some narrative about debugging the chunking issue
more context about testing different prompt lengths
```

V9A+ extrait les 5 lignes taguees, ignore les 2 lignes de narratif.
Trouve `branch_compression_pipeline` comme voisin le plus proche via mycelium.
Injecte:
```
## REGEN: branch_l9_api_2026 (2026-03-11)
B> L9 API: x4.4 avg on 230 files, $0.21 total cost
D> switched to section-chunked R1-Compress for texts >8K
F> L9 prompt: 847 tokens system, 200 tokens user template
E> BUG: chunking failed when no ## headers, fixed fallback to line-split
A> added retry logic for Haiku rate limits
```

Le fichier .mn de `branch_l9_api_2026` est ensuite supprime.
Mais les faits vivent dans `branch_compression_pipeline.mn`.

### Ce qui rend ca unique (pour le pitch)

1. **Aucun systeme de memoire LLM ne fait ca.** MemGPT, Letta, Zep — ils stockent
   ou ils oublient. Personne ne regenere le contenu factuel apres la mort d'une unite.

2. **C'est biologiquement inspire.** Levin 2013: les planaires regenerent leur tete
   (et leur memoire) a partir du pattern bioelectrique du corps. Le mycelium est
   notre pattern bioelectrique — il encode QUOI est lie a QUOI. Les faits tagges
   sont l'ADN — l'information minimale pour reconstruire.

3. **C'est mesurable.** Avant V9A+: branch meurt, faits perdus, boot("L9") = rien.
   Apres V9A+: branch meurt, faits migrent, boot("L9") = les metriques sont la.
   Le benchmark est: combien de faits D>/B>/F>/E> survivent apres prune().
   On peut mesurer un taux de survie factuelle en %.

4. **C'est zero-cost.** Pas d'API, pas de LLM, pas de reseau. Lire un fichier,
   filtrer des lignes par prefix, ecrire dans un autre fichier. Sub-milliseconde.

### Risques et pieges

- **Pollution**: si on injecte trop de faits dans une branche, elle devient une
  poubelle incoherente. -> Solution: budget de 200 lignes + recompression L10/L11
- **Faits stale**: un fait de 2025 injecte dans une branche de 2026 peut etre
  obsolete. -> Solution: _resolve_contradictions() deduplique les faits stale
- **Cascade**: si la branche cible meurt aussi au prochain prune, les faits
  re-migrent. Apres N morts, les faits accumulent N sections REGEN.
  -> Solution: lors de l'extraction, prendre aussi les faits des sections REGEN
  existantes (pas juste les faits natifs). C'est de la transitivite.
- **Branche cible pleine**: si le survivant est deja a 200 lignes, pas de place.
  -> Solution: recompresser avec L10/L11 avant injection, ou chercher un autre survivant
- **Concurrence avec sleep_consolidate**: les branches froides sont consolidees
  AVANT V9A+. Si une branche froide qui aurait ete un bon receveur est mergee,
  le nom change. -> Solution: V9A+ tourne APRES sleep_consolidate, donc les
  noms consolides sont deja dans `nodes` quand on cherche un survivant.

### Definition of Done

- [ ] V9A+ implemente dans muninn.py (remplace V9A actuel)
- [ ] 12 bornes dans test_v9a_plus.py, toutes PASS
- [ ] Bug scan independant: 0 HIGH/CRITICAL
- [ ] Regression 102 + 12 = 114 bornes, 0 FAIL
- [ ] Demo sur un cas reel
- [ ] Commit message: "V9A+ Regeneration: fact-level survival across branch death (Levin 2013)"
- [ ] WINTER_TREE.md mis a jour avec la metrique de survie factuelle

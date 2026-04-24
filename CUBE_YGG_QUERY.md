# Cube Muninn — Architecture, Preuves & Implications

## Le Cube c'est quoi

Systeme de resilience de code par destruction/reconstruction atomique.
Le mycelium se subdivise et teste sa propre connaissance.

### Flow
1. Scan brut du code → index raw avec SHA-256 par cube
2. Subdivision recursive /8 jusqu'a cubes atomiques de 88 tokens
3. Voisins premier passage = analyse statique (imports, calls, refs)
4. Chaque cube detruit, 9 voisins + LLM tentent de reconstruire
5. Validation SHA-256 contre le code ORIGINAL (pas du compresse)
6. Resultats nourrissent le mycelium (double poids: statistique + mecanique)
7. Remontee par niveaux 88 → 704 → 5632, antifragile
8. God's Number = nombre minimum de cubes irreconstructibles

### Concepts cles
- Le mycelium ne definit PAS les voisins au debut. Il les APPREND des resultats.
- L'AI rate les valeurs (timeout=3000 → 5000) = detection automatique des valeurs critiques.
- C'est de l'immunologie: on rend le systeme malade EXPRES pour qu'il developpe des anticorps.
- Plugin sur le LLM existant du client = zero cout additionnel.

---

## Preuve de concept — Test reel sans API (2026-03-18)

4 cubes detruits et reconstruits par Claude dans le chat, sans API, sans mock.
Le LLM ne voit QUE les 9 voisins. Il doit reconstruire le cube manquant.
Validation: SHA-256 de la reconstruction vs SHA-256 de l'original.

| # | Fichier | Lignes | Tokens | SHA-256 Match |
|---|---------|--------|--------|---------------|
| 1 | mycelium.py | L126-139 | 110 | EXACT |
| 2 | mycelium.py | L201-209 | 118 | EXACT |
| 3 | muninn.py | L6624-6631 | 99 | EXACT |
| 4 | cube.py | L824-834 | 88 | EXACT |

**4/4 reconstructions parfaites. Zero erreur. Zero API. Zero cout.**

### Ce que ca prouve
- Un LLM peut reconstruire du code atomique a partir de son contexte local
- 9 voisins suffisent (Locally Repairable Codes, Gopalan 2012: r=9)
- La validation SHA-256 est stricte et passe quand meme
- Ca marche sur du code de production (pas des hello world)

### Ce que ca implique
- **Self-healing code**: un repo peut detecter ET reparer ses propres corruptions
- **God's Number reel**: les cubes qui NE PEUVENT PAS etre reconstruits = les vrais points critiques
- **Priorite de debug**: temperature haute = le LLM ne comprend pas ce cube = c'est la que les bugs se cachent
- **Mesure de qualite**: un code bien ecrit a un God's Number bas (tout est reconstructible)
- **Antifragilite**: chaque echec de reconstruction renforce le graphe (Hebbian learning)

---

## Etat de l'implementation

**Engine**: `engine/core/cube.py` — 2713 lignes, 54 fonctions/classes exportees
**Tests**: 242 tests (9 fichiers), 0 FAIL, 3 skipped (providers non installes)
**Scan reel**: 5103 cubes sur 197 fichiers (repo Muninn complet)
**Forge**: 592 tests totaux, 0 FAIL (integration Forge validee)

---

## 39 Briques d'implementation [TOUTES DONE]

### SCAN & STRUCTURE (B1-B6)
1. Scanner de repo (parcours fichiers, filtre binaires/vendored)
2. Tokenizer integration (tiktoken, comptage tokens)
3. Cube dataclass (id, content, sha256, neighbors, score, level)
4. Subdivision engine (recursif /8, frontieres semantiques, 88 tokens)
5. SHA-256 normalisation + hashing
6. Stockage index SQLite (tables: cubes, neighbors, cycles)

### VOISINS (B7-B10)
7. AST parser multi-langage (imports, calls, refs)
8. Construction graphe de voisins (9 plus proches)
9. Laplacian RG groupage optimal (Villegas 2023)
10. Cheeger constant par sous-graphe (bottleneck detection)

### LLM (B11-B15)
11. Interface LLMProvider abstraite
12. Backend Ollama (llama, mistral, phi, deepseek-coder)
13. Backend Claude API (reutilise tuyau L9)
14. Backend OpenAI API
15. Mode FIM — Fill-in-the-Middle (infilling natif)

### RECONSTRUCTION (B16-B22)
16. Moteur de reconstruction (prompt + appel LLM)
17. Validation SHA-256 (original vs reconstruit)
18. Scoring perplexite = hotness en 1 appel LLM
19. NCD fallback (si SHA-256 trop strict)
20. Belief Propagation entre voisins (Pearl 1988)
21. Survey Propagation pre-filtre (Mezard-Parisi 2002)
22. Tononi Degeneracy pre-calcul (fragilite avant destruction)

### SCORING & SUIVI (B23-B26)
23. Temperature par cube + stockage + historique
24. Kaplan-Meier survie par cube (Scanniello 2011)
25. Danger Theory filtre dead code (Matzinger 2002)
26. God's Number calcul + bornes theoriques

### NIVEAUX (B27-B28)
27. Remontee par niveaux (88 → 704 → 5632)
28. Agregation des scores entre niveaux

### INTEGRATION (B29-B31)
29. Feed resultats → mycelium (poids mecanique "prouve")
30. Hebbian update (Rule & O'Leary 2022)
31. Git blame crossover (valeurs → historique)

### INFRA (B32-B34)
32. Scheduling async (tourne dans les creux)
33. Config securite (local_only flag)
34. Multi-LLM hooks (ChatGPT, Copilot, Ollama, etc.)

### VISU & FORGE (B35-B38)
35. Tree heatmap — cube_heatmap() groupe par fichier, avg/max temp, hot_count
36. Forge link — fuse_risks() combine Forge risk (0.4) + Cube temp (0.6)
37. Auto-repair — auto_repair() identifie cubes chauds, genere patchs FIM
38. Feedback loop — record_anomaly() + feedback_loop_check() + feed_anomalies_to_mycelium()

### CLI (B39)
39. Commandes: cube scan, cube run, cube status, cube heatmap, cube god

---

## Les deux pipelines

Le systeme a deux pipelines independants qui partagent le mycelium:

### Pipeline 1: Muninn (compression memoire)
```
Session de travail → transcript JSONL
    → L0-L7 compression regex (x4.5)
    → L10 cue distillation + L11 rule extraction
    → L9 Haiku API (optionnel)
    → fichier .mn compresse
    → arbre fractal (branches, temperature, spaced repetition)
    → mycelium (co-occurrences, fusions, spreading activation)
```
**But**: garder la memoire entre sessions LLM. Compresser x4.5 pour que le
contexte de 200K tokens dure plus longtemps.

### Pipeline 2: Cube (resilience code)
```
Repo source → scan fichiers → subdivision /8
    → cubes atomiques 88 tokens + SHA-256
    → graphe de voisins (AST + proximite)
    → destruction/reconstruction par LLM
    → validation SHA-256
    → temperature (chaud = irreconstructible, froid = trivial)
    → God's Number (combien de cubes sont vraiment critiques)
    → Forge integration (heatmap + auto-repair + feedback)
```
**But**: mesurer et renforcer la resilience du code. Trouver les points critiques.

### Le pont: le mycelium
Les deux pipelines nourrissent le meme mycelium:
- Muninn nourrit avec les co-occurrences de concepts (statistique)
- Cube nourrit avec les resultats de reconstruction (mecanique)
- Double poids: "ces concepts apparaissent ensemble" + "ce voisin a PROUVE qu'il peut reconstruire ce cube"
- Hebbian learning: les connexions qui marchent se renforcent, les autres s'affaiblissent

---

## Formules

### Fondation — Candes-Recht-Tao 2009
Matrix completion: reconstruction exacte garantie quand rang effectif bas.
Le code a un rang bas (patterns repetitifs) → seuil atteignable.
m ≥ C × n × r × log²(n), ou r = rang effectif, n = dimension.

### Hotness (temperature d'un cube)
```
Hotness(cube) = K(cube | voisins)
             ≈ H(cube | voisins)           ← Information Bottleneck (Tishby 99)
             ≈ MDL_residual(cube, voisins)  ← Minimum Description Length (Rissanen 78)
             ≈ -Σ log P_LLM(token_i)       ← MESURABLE en 1 appel LLM
```
UNE mesure, QUATRE theories convergentes. 1 appel au lieu de 11 destructions.

### God's Number
```
God's Number = |{cubes : Hotness > τ}|
             = dim H¹(G, F)                 ← Sheaf cohomology (Hansen-Ghrist 19)
             ≈ seuil k-core du mycelium     ← Percolation (Dorogovtsev 06)
             ≥ n/10                          ← LRC bound r=9 (Gopalan 12)
             ~ O(log N)                      ← MERA scaling (Vidal 07)
```

### Formules par brique
| Brique | Formule | Source |
|--------|---------|--------|
| B5 | SHA-256(normalize(content)) | Standard |
| B9 | Laplacien L = D - A, decimation spectrale | Villegas 2023 |
| B10 | h(G) = min\|E(S,V\\S)\|/min(vol(S),vol(V\\S)) | Cheeger, λ₂/2 ≤ h ≤ √(2λ₂) |
| B18 | Hotness = -Σ log P_LLM(token_i \| voisins) | Rissanen 78 + Tishby 99 |
| B19 | NCD(a,b) = (C(ab)-min(C(a),C(b)))/max(C(a),C(b)) | Cilibrasi-Vitanyi 05 |
| B20 | μ_i→j(x_j) = Σ ψ(x_i,x_j) Π μ_k→i(x_i) | Pearl 1988 (BP) |
| B22 | D = Σ MI(v_i, cube) - MI(all_v, cube) | Tononi 1999 |
| B24 | S(t) = Π(1 - d_i/n_i) | Kaplan-Meier / Scanniello 2011 |
| B26 | fc = ⟨k⟩/(⟨k²⟩-⟨k⟩), God's ≥ n/10, ~ O(log N) | Callaway 00, Gopalan 12, Vidal 07 |
| B30 | Δw = η × pre × post | Rule & O'Leary PNAS 2022 (Hebbian) |
| B17+MSR | ~4 tokens/voisin pour exact repair (r=9,k=3) | Dimakis 2010 |
| B36 | combined = 0.4×forge_risk + 0.6×cube_temp | Nagappan & Ball 2005 + Cube |
| B38 | accuracy = correct/total over lookback_days | Feedback validation |

---

## Implications techniques

### 1. Self-healing repositories
Un repo equipe de Cube peut detecter quand un fichier a ete corrompu (SHA-256 mismatch)
et proposer une reconstruction automatique a partir des voisins. Ce n'est plus du backup —
c'est de la regeneration. Le code se repare comme un organisme.

### 2. God's Number = metrique de qualite du code
Un bon code a un God's Number bas: presque tout est reconstructible par le contexte.
Un mauvais code a un God's Number haut: beaucoup de cubes sont opaques, meme avec
9 voisins. C'est une metrique objective, mesurable, comparable entre repos.

### 3. Temperature = priorite de debug
Les cubes chauds sont ceux que le LLM ne comprend pas. C'est exactement la que
les bugs se cachent — dans le code que personne ne comprend. Au lieu de deviner
ou debugger, la temperature pointe directement vers les zones a risque.

### 4. Feedback loop avec le mycelium
Les resultats de reconstruction nourrissent le mycelium avec des poids mecaniques
(prouves par destruction/reconstruction), pas juste statistiques (co-occurrence).
Le mycelium apprend quels morceaux de code sont lies mecaniquement — pas juste
quels mots apparaissent ensemble, mais quels voisins permettent REELLEMENT de
reconstruire un cube.

### 5. Antifragilite par Hebbian learning
Chaque cycle de destruction/reconstruction renforce les bonnes connexions et
affaiblit les mauvaises (Δw = η × pre × post). Le systeme devient plus fort
avec le temps. Plus on le stresse, mieux il se defend.

### 6. Integration Forge — debug cible
La Forge predit les defauts par historique git (Nagappan & Ball 2005).
Le Cube mesure la fragilite structurelle. Combines:
- Forge dit "ce fichier change souvent et a beaucoup de bugs"
- Cube dit "ces cubes dans ce fichier sont irreconstructibles"
- Ensemble: precision chirurgicale pour le debug

### 7. Auto-repair via FIM
Quand un test echoue, auto_repair() identifie les cubes les plus chauds
dans les fichiers concernes et genere des patchs via Fill-in-the-Middle.
Le LLM utilise les voisins comme contexte pour proposer une correction.
Mutation testing: on teste chaque patch et on garde le meilleur.

### 8. Zero cout additionnel
Le Cube utilise le LLM que le client a deja (Ollama local, Claude, OpenAI).
Pas de modele supplementaire. Pas d'infrastructure. Le scan + subdivision
est du regex/AST pur. Le seul cout LLM est pendant les cycles de reconstruction,
et Survey Propagation (B21) filtre ~30% des cubes triviaux avant de les tester.

### 9. local_only — securite
Avec `local_only=True`, le code ne quitte jamais la machine.
Ollama tourne en local. Aucun appel API externe. Le code source reste prive.
Critique pour les entreprises qui ne peuvent pas envoyer leur code a un cloud.

### 10. Universel — n'importe quel langage
Le scanner supporte Python, JS/TS, Java, Go, Rust, C/C++, Ruby, PHP, Kotlin, Scala, YAML.
L'AST parser extrait les imports/calls/refs pour chaque langage.
La subdivision par tokens est agnostique au langage.
Un seul systeme pour tout le codebase.

---

## Sources scientifiques

### TIER S — Changent l'architecture
| # | Concept | Auteurs | Annee | Ref |
|---|---------|---------|-------|-----|
| 1 | Sheaf Theory sur graphes | Hansen & Ghrist | 2019 | IEEE Signal Processing |
| 2 | Information Bottleneck | Tishby, Pereira, Bialek | 1999 | physics/0004057 |
| 2 | MDL | Rissanen | 1978 | Annals of Statistics |
| 2 | NCD | Cilibrasi & Vitanyi | 2005 | IEEE Trans. IT |
| 3 | MERA (tensor RG) | Vidal | 2007 | PRL 99:220405 |
| 4 | k-core percolation | Dorogovtsev, Goltsev, Mendes | 2006 | PRL 96:040601 |
| 5 | Locally Repairable Codes | Gopalan, Huang, Simitci, Yekhanin | 2012 | IEEE Trans. IT |

### TIER A — Optimisent le systeme
| # | Concept | Auteurs | Annee | Ref |
|---|---------|---------|-------|-----|
| 6 | Belief Propagation | Pearl | 1988 | Probabilistic Reasoning |
| 7 | Survey Propagation | Mezard, Parisi, Zecchina | 2002 | Science 297:812 |
| 8 | NCD quasi-universel | Cilibrasi & Vitanyi | 2005 | IEEE Trans. IT |
| 9 | Spectral Graph Wavelets | Hammond, Vandergheynst, Gribonval | 2011 | ACHA 30:129 |
| 10 | Laplacian RG | Villegas, Gili, Caldarelli, Gabrielli | 2023 | Nature Physics |
| 11 | Stackelberg Security | Tambe | 2011 | Security Games (Cambridge) |
| 12 | Degeneracy | Tononi, Sporns, Edelman | 1999 | PNAS 96:3257 |
| 13 | Proper Scoring Rules | Brier | 1950 | Monthly Weather Review |

### Carmack Moves — Ponts vierges
| # | Concept | Auteurs | Annee | Ref |
|---|---------|---------|-------|-----|
| 14 | Self-Healing Neural Codes | Rule & O'Leary | 2022 | PNAS |
| 15 | Code Survival Kaplan-Meier | Scanniello | 2011 | Semantic Scholar |
| 16 | Bioelectric Code | Levin | 2017 | BioSystems |
| 17 | MSR/MBR regenerating codes | Dimakis, Godfrey, Wu, Wainwright | 2010 | IEEE Trans. IT 56:4539 |
| 18 | Fill-in-the-Middle | Fried et al. (InCoder) | 2022 | ICLR 2023 |
| 19 | BFT + Regenerating | Oggier & Datta | 2011 | IEEE P2P |
| 20 | Antifragile Software | Monperrus | 2014 | arXiv 1404.3056 |
| 20 | UNFRAGILE framework | (IST vol.174) | 2024 | Elsevier |

### Insights profonds
| Concept | Auteurs | Annee | Insight |
|---------|---------|-------|---------|
| 30% mutations neutres | Schulte et al. | 2014 | Baseline empirique |
| Code entropy 3-4 bits/tok | Hindle et al. | 2012 | Ratio 9:1 sur-determine |
| LLMs = mauvais compresseurs | Meta/ICLR | 2025 | God's Number > theorie |
| Logical Depth | Bennett | 1988 | Chaud car profond |
| Danger Theory | Matzinger | 2002 | Filtre dead code |
| Planarian info locale | Levin | 2015 | Pas de blueprint global |
| Diffusion Wavelets | Coifman & Maggioni | 2006 | Multiresolution graphe |
| Network Robustness | Callaway, Newman, Strogatz | 2000 | cond-mat/0007300 |
| Loopy BP convergence | Ihler, Fisher, Willsky | 2005 | JMLR vol.6 |
| Matrix completion | Candes, Recht, Tao | 2009 | Fondation theorique |

### 842 Papers Yggdrasil
Fichier complet: `data/scan/cube_muninn_papers.txt` (Yggdrasil Engine WT3)
13 axes, 833K papers scannees, 69M cooccurrences, 65K concepts OpenAlex.

---

## Battle plan [COMPLETE]
| Jour | Briques | Quoi |
|------|---------|------|
| 1-2 | B1-B6 | Scan + structure + SHA-256 + stockage [DONE] |
| 3 | B7-B8 | AST parser + graphe voisins [DONE] |
| 4 | B11-B15 | LLM providers + FIM [DONE] |
| 5 | B16-B19 | Reconstruction + validation + scoring + NCD [DONE] |
| 6 | B23-B26 | Temperature + Kaplan-Meier + Danger Theory + God's Number [DONE] |
| 7 | B27-B28 | Remontee niveaux + agregation [DONE] |
| 8 | B29-B31 | Feed mycelium + Hebbian + git blame [DONE] |
| 9 | B9-B10 + B20-B22 | Laplacian RG + Cheeger + BP + SP + Tononi [DONE] |
| 10 | B32-B35 | Scheduling + securite + hooks + heatmap [DONE] |
| 11 | B36-B39 | Forge link + auto-repair + feedback + CLI [DONE] |

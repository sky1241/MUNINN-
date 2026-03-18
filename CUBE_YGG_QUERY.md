# Cube Muninn — Architecture & Recherche

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

## 39 Briques d'implementation

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
35. Tree heatmap (visu zones chaudes)
36. Lien Muninn → Forge (temperature guide debug cible)
37. Auto-repair (3 patchs → mutation test → propose)
38. Feedback loop bugs → mycelium (prediction 6 mois)

### CLI (B39)
39. Commandes: cube scan, cube run, cube status, cube heatmap, cube god

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

## Battle plan
| Jour | Briques | Quoi |
|------|---------|------|
| 1-2 | B1-B6 | Scan + structure + SHA-256 + stockage |
| 3 | B7-B8 | AST parser + graphe voisins |
| 4 | B11-B15 | LLM providers + FIM |
| 5 | B16-B19 | Reconstruction + validation + scoring + NCD |
| 6 | B23-B26 | Temperature + Kaplan-Meier + Danger Theory + God's Number |
| 7 | B27-B28 | Remontee niveaux + agregation |
| 8 | B29-B31 | Feed mycelium + Hebbian + git blame |
| 9 | B9-B10 + B20-B22 | Laplacian RG + Cheeger + BP + SP + Tononi |
| 10 | B32-B35 | Scheduling + securite + hooks + heatmap |
| 11 | B36-B39 | Forge link + auto-repair + feedback + CLI |

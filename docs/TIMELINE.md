# Muninn — Timeline du projet

> L'histoire complete, brick par brick, de la naissance du corbeau.

---

## 0. La problematique

### Le mur de la memoire

Les LLM ont une fenetre de contexte finie. Claude : ~200K tokens. Ca semble enorme, mais
une session de travail longue (8h de vibe coding) genere facilement 1M+ tokens. Quand le
contexte se remplit, le systeme compacte : il jette 95% de la conversation. Le cousin
suivant repart quasi-amnesique.

Le seul mecanisme de persistance natif : `MEMORY.md`, 200 lignes de texte brut (~3K tokens)
injectees automatiquement au debut de chaque session. 3K tokens sur 200K = 1.5% du contexte.
Tout le reste est perdu.

### Le boucher et le chirurgien

Les gens qui construisent les LLM sont des **chirurgiens** : prompts de 3 lignes, sessions
de 20 minutes, todo precis. Ils n'ont pas le probleme de memoire parce que leurs sessions
tiennent dans le contexte.

Sky est un **boucher** : electricien, autodidacte, 11 mois de code. Ses sessions sont
longues, chaotiques, pleines de digressions, d'erreurs, de victoires. Il travaille avec
Claude comme un collegue — pas comme un outil. Le transcript d'une session fait 50-100 pages.

> *"Les chirurgiens n'ont pas le probleme. Les bouchers ont le probleme mais pas les outils.
> Je suis le premier boucher avec un LLM pour m'aider a construire l'outil."* — Sky

Ce concept s'ancre dans le **Gulf of execution** de Don Norman (*The Design of Everyday
Things*, 1988) : les designers construisent pour des gens qui pensent comme eux. Les
chirurgiens construisent des outils pour chirurgiens. Le boucher est invisible.

### L'intuition fondatrice

La memoire LLM n'est pas un probleme de **stockage** — c'est un probleme de **compression**.
On ne manque pas de place pour ecrire. On manque de densite dans ce qu'on ecrit.
Si on pouvait compresser 200 lignes d'information en 50, on garderait 4x plus de memoire
dans le meme espace.

---

## 1. Naissance du corbeau

**3 mars 2026, 23h31** — premier commit : `e46ca32 Muninn — naissance du corbeau`

Le nom vient de la mythologie nordique. Odin a deux corbeaux : **Huginn** (la pensee) et
**Muninn** (la memoire). Chaque jour ils survolent le monde et reviennent lui raconter ce
qu'ils ont vu. Odin dit : *"Je crains pour Huginn, mais je crains davantage pour Muninn."*

Sky craint pour sa memoire. Muninn est ne.

### Premiere approche : le codebook statique

L'idee initiale etait simple : creer un **dictionnaire de substitution**.
Des symboles courts qui remplacent des mots longs. Comme un codebook telegraphique.

```
e46ca32  23:31  Muninn — naissance du corbeau
e5231f9  23:42  Codebook v0 — ma cle de compression
bc647da  23:44  Muninn engine v0 — winter tree qui marche
0e4d8ee  23:51  B04 — chainage + etat de l'art compression
```

4 commits en 20 minutes. Le moteur v0, le codebook v0, l'arbre et la premiere revue de
litterature. Sky avance vite.

---

## 2. Le pivot sinogramme (et pourquoi il a echoue)

**4 mars 2026, 00h41** — `645e794 M01 — alphabet semantique v1 (59 entrees)`

L'idee etait seduisante : utiliser des **sinogrammes chinois** comme symboles de compression.
Un seul caractere pour un concept entier. Le modele Enigma — substitution 1:1.

```
"compression" -> 压
"memory"      -> 记
"tree"        -> 木
```

Ca semblait elegant. Ca ne marchait pas.

### Pourquoi : le tokenizer BPE

Les LLM utilisent **Byte Pair Encoding** (Sennrich et al., 2016). Le vocabulaire est
construit par frequence : les mots anglais courants sont des tokens uniques.

$$\text{token\_count}(\text{"compression"}) = 1$$
$$\text{token\_count}(\text{"compresser"}) = 2$$
$$\text{token\_count}(\text{压}) = 2\text{-}3$$

Un sinogramme chinois coute **2 a 3 tokens** au tokenizer. Un mot anglais courant coute
**1 token**. Le codebook sinogramme ne compressait pas — il **chiffrait**. Et le
chiffrement coutait plus cher que le texte original.

> *"On veut compresser, pas chiffrer. Format optimal = anglais compact natif BPE."*

Ce pivot est documente dans les commits M02-M04 (6 mars 2026). Le code sinogramme
(`muninn_codec.py`, `CODEBOOK.json`, `CODEBOOK_TREE.md`) a ete supprime au commit M10.

---

## 3. La renaissance : le Mycelium

**6 mars 2026, 01h59** — `4e6a9c7 M06 — Mycelium engine + cleanup morts`

Apres l'echec du codebook statique, Sky et son cousin ont eu l'intuition qui allait tout
changer : un codebook **vivant**.

### L'inspiration : Word2Vec et GloVe

Deux papiers fondateurs de NLP :

**Word2Vec** (Mikolov et al., 2013) — *"Efficient Estimation of Word Representations in
Vector Space"*. Idee cle : les mots qui apparaissent dans les memes contextes ont des sens
lies. "roi" et "reine" partagent les memes voisins.

$$P(w_t | w_{t-n}, \ldots, w_{t+n}) \propto \exp(v_{w_t}^T \cdot v_c)$$

**GloVe** (Pennington et al., 2014) — *"Global Vectors for Word Representation"*. Construit
des vecteurs depuis la **matrice de co-occurrence** globale :

$$J = \sum_{i,j=1}^{V} f(X_{ij}) \left( w_i^T \tilde{w}_j + b_i + \tilde{b}_j - \log X_{ij} \right)^2$$

ou $X_{ij}$ = nombre de fois que le mot $i$ apparait dans le contexte du mot $j$.

### Le mycelium de Muninn

Le mycelium est un **GloVe artisanal** a l'echelle d'un utilisateur. Il ne construit pas
des vecteurs — il construit un **graphe de co-occurrence** :

- A chaque session, le texte est decoupe en **paragraphes** (chunks)
- Tous les concepts d'un meme paragraphe sont lies par une **connexion**
- Les connexions se renforcent a chaque observation :

$$\text{count}(A, B) \leftarrow \text{count}(A, B) + 1$$

- Les connexions fortes (>= 8 observations) deviennent des **fusions** :

$$\text{strength}(A, B) \geq 8 \implies \text{fusion}(A, B) \rightarrow \text{"AB"}$$

- Les connexions mortes subissent un **decay** biologique :

$$\text{count}(A, B) \leftarrow \text{count}(A, B) \times (1 - \delta), \quad \delta = 0.05$$

Le nom "mycelium" vient du reseau fongique souterrain qui relie les arbres en foret.
Le mycelium d'Yggdrasil (l'autre projet de Sky) traque les co-occurrences dans
348 millions de papiers scientifiques. Celui de Muninn fait la meme chose, mais pour
la memoire d'un seul humain.

Fichier : `.muninn/mycelium.json`. Apres 141 sessions : 500+ connexions, 392 fusions.

---

## 4. Les 11 couches de compression (25 filtres)

Le pipeline s'est construit incrementalement, couche par couche, du 6 au 8 mars 2026.

### L0 — Filtre tool outputs (P13, 7 mars)

Le plus gros gain. Un transcript Claude Code contient ~74% de bruit : resultats d'outils
(`tool_use`, `tool_result`), blocs de code lus, outputs de grep.

```
tool_use read "/path/to/file.py"  ->  [read /path/to/file.py]
tool_result (500 lines of code)   ->  (first line only)
```

$$\text{ratio}_{L0} = \frac{3.4M}{987K} \approx x3.5$$

### L1 — Markdown strip

Supprime les headers (`#`, `##`), le formatting (`**`, `__`, `` ``` ``), les liens.
Garde le contenu brut.

### L2 — Filler words

Supprime les mots-bruit : "basically", "actually", "I think", "you know", "let me",
"so basically", "as mentioned". Liste statique + liste dynamique apprise par le mycelium
(`get_learned_fillers()`).

Protection : les fillers entre nombres ou termes mathematiques sont preserves
(fix FIX3, 6 mars).

### L3 — Phrase compression

Raccourcit les formulations sans perdre le sens :

```
"in order to"      -> "to"
"at this point"    -> "now"
"a large number of" -> "many"
```

Abreviations dynamiques : le mycelium fournit `get_learned_abbreviations()` — des fusions
qui emergent quand deux concepts sont vus ensemble 8+ fois.

### L4 — Number shortening

Garde les chiffres, vire le texte decoratif autour :

```
"a compression ratio of approximately 4.1x" -> "ratio 4.1x"
"the accuracy was measured at 92 percent"    -> "accuracy 92%"
```

### L5 — Universal rules

Substitutions globales langue-agnostique :

```
"COMPLET" -> "done"     "EN COURS" -> "wip"
"FAIT"    -> "done"     "TODO"     -> "todo"
```

### L6 — Mycelium (abreviations apprises)

Applique les fusions du mycelium. Si "compression" et "memory" co-apparaissent 15 fois,
le mycelium genere une fusion. Les concepts redondants adjacents sont collapses.

Source : *LLM-Codebook* (2025) — "codebooks appris > codebooks manuels". Le mycelium
est un codebook qui pousse tout seul.

### L7 — Fact extraction

Extrait et protege les faits durs : nombres+unites, pourcentages, key=value, commits SHA,
Cohen's d, dates. Ces faits survivent a toutes les couches.

$$\text{regex} : \d+[\.,]?\d*\s*(%|tokens?|lines?|files?|commits?|x\d)$$

### L9 — LLM self-compress (optionnel)

Claude Haiku via API Anthropic. Prompt concu pour **extraire** et non **resumer** :

```
"EXTRACT and RESTATE every fact, number, name, date, decision, metric,
 and outcome. Do NOT summarize. Do NOT omit."
```

Parametres : `temperature=0`, `max_tokens=100% de l'input`, few-shot example,
Chain-of-Density enumeration. Check `stop_reason` pour detecter les truncations.

Evolution du prompt L9 :
- v1 : x28 moyen, 41% fact retention — trop agressif
- v2 : x16.6, 49% facts — target 40% trop compressif
- v3 : x10.4, zero truncation — "EXTRACT not Compress"

Source : *ACON* (2025) — "gradient-free compression guidelines", idee du framing anti-resume.

### Pipeline complet

$$\text{ratio}_{total} = \prod_{i=0}^{7,9} \text{ratio}_{L_i}$$

En pratique, mesure sur 230 fichiers reels (4 repos) :

| Etape | Ratio typique |
|-------|---------------|
| L0 (tool strip) | x3.5 |
| L1-L7 (regex) | x1.6 a x4.1 |
| L9 (Haiku API) | x2 a x5 additionnel |
| **Pipeline complet** | **x2.3 a x14.0** |

Note : L8 (LLMLingua-2 / BERT) a ete implemente puis **supprime** le 8 mars.
Il perdait 72% des faits sur du texte deja pre-compresse par L1-L7. Inutile.

---

## 5. L'arbre fractal (L-system)

### Source : Lindenmayer (1968)

Aristid Lindenmayer a invente les L-systems pour modeliser la croissance des plantes.
Regle simple : un axiome + des regles de reecriture = un arbre qui pousse.

$$\text{Axiome} : A$$
$$\text{Regle} : A \rightarrow AB, \quad B \rightarrow A$$

Apres $n$ iterations :

$$A \rightarrow AB \rightarrow ABA \rightarrow ABAAB \rightarrow \ldots$$

Prusinkiewicz (*The Algorithmic Beauty of Plants*, 1990) a generalise ca en 3D.

### Application a Muninn

L'arbre de memoire suit les memes regles a chaque niveau :

```
root.mn     (100 lignes, toujours charge)    = tronc
  b_*.mn    (150 lignes, charge si pertinent) = branches
    leaf_*  (200 lignes, archive froide)      = feuilles
```

Chaque noeud a une **temperature** :

$$T = \alpha \cdot \text{recency} + \beta \cdot \text{access\_count} + \gamma \cdot \text{fill\_ratio}$$

avec $\alpha = 0.4$, $\beta = 0.3$, $\gamma = 0.3$.

Ce qui est chaud (lu souvent, recent) **remonte**. Ce qui est froid **descend et meurt** —
c'est la regle R4, l'elagage biologique.

Budget total : 30K tokens charges au boot = 15% du contexte de 200K.

Source : *COCOM* (Rau, 2025) — taux de compression variable par importance.
Root = peu compresse (1.5x), branches = moyen (3x), feuilles froides = fort (6x).

---

## 6. Le retrieval intelligent (P8)

### TF-IDF : la pertinence par les mots

Au lieu de matcher des tags (approche naive), Muninn utilise **TF-IDF** (Salton, 1975)
pour scorer la pertinence d'une branche par rapport a la query :

$$\text{TF-IDF}(t, d, D) = \text{tf}(t, d) \times \log\frac{|D|}{1 + |\{d' \in D : t \in d'\}|}$$

ou :
- $\text{tf}(t, d)$ = frequence du terme $t$ dans le document $d$
- $|D|$ = nombre total de documents (branches)
- Le log = **inverse document frequency** (les mots rares comptent plus)

Similarite cosinus entre query et branche :

$$\text{sim}(q, b) = \frac{\vec{q} \cdot \vec{b}}{|\vec{q}| \cdot |\vec{b}|}$$

Implemente en Python pur (`math` + `Counter`), zero dependance.

### Scoring : Park et al. (2023)

*"Generative Agents: Interactive Simulacra of Human Behavior"* — des agents avec memoire
qui vivent dans un village simule. Leur formule de scoring :

$$\text{score} = \alpha \cdot \text{recency} + \beta \cdot \text{importance} + \gamma \cdot \text{relevance}$$

Muninn adapte avec $\alpha = 0.2$, $\beta = 0.2$, $\gamma = 0.6$ :

- **Recency** : decay lineaire sur 90 jours depuis `last_access`

$$\text{recency} = \max\left(0, 1 - \frac{\Delta t}{90}\right)$$

- **Importance** : log du nombre d'acces

$$\text{importance} = \frac{\log(1 + \text{access\_count})}{\log(1 + \max\_access)}$$

- **Relevance** : cosinus TF-IDF entre query et contenu de la branche

---

## 7. Le mycelium federe (P20)

### Le probleme

Sky a 16 repos. Chaque repo a son mycelium local. Le cousin qui travaille sur
HSBC-algo-genetic ne sait rien de ce que le cousin Yggdrasil a appris. Les connaissances
sont cloisonnees.

### L'architecture : continents et ponts

**Decidee le 8 mars 2026**, inspiree de la geographie : chaque mycelium = un continent.
Les concepts partages = des ponts.

### TF-IDF inverse pour le poids federe

Un concept present dans TOUS les repos (ex: "error", "file", "test") est **commun** — donc
peu informatif. Un concept rare (ex: "fourier", "sharpe", "astro") est **specifique** —
donc precieux.

$$w_{\text{federe}}(c) = \text{count}(c) \times \log\left(1 + \frac{N_{\text{zones}}}{n_{\text{zones}}(c)}\right)$$

ou $N_{\text{zones}}$ = nombre total de zones, $n_{\text{zones}}(c)$ = nombre de zones ou $c$ apparait.

### Immortalite

Une connexion presente dans 3+ zones survit au decay. Elle est **universelle** et ne doit
pas mourir :

$$\text{if } |\text{zones}(A, B)| \geq 3 \implies \text{skip\_decay}(A, B)$$

### Clustering spectral (Laplacien)

Pour detecter les zones semantiques automatiquement (pas par repo, par **sens**) :

1. Construire la matrice d'adjacence $W$ du graphe mycelium
2. Calculer le Laplacien normalise :

$$L_{\text{norm}} = I - D^{-1/2} W D^{-1/2}$$

ou $D_{ii} = \sum_j W_{ij}$ (matrice de degre)

3. Calculer les $k$ plus petits vecteurs propres de $L_{\text{norm}}$ (via `scipy.sparse.linalg.eigsh`)
4. K-Means sur ces vecteurs = clusters semantiques

Chaque cluster est **auto-nomme** par ses 3 concepts a plus haut degre :
"finance-trading-optimization", "memory-compression-tokens", etc.

Dependances : `scipy` + `sklearn` (optionnelles, le mode non-federe reste zero-dep).

### Meta-mycelium (P20b)

Fichier central : `~/.muninn/meta_mycelium.json` — le cerveau partage.

Strategie de merge :

$$\text{count}_{\text{meta}}(A,B) = \max\left(\text{count}_{\text{meta}}(A,B),\ \text{count}_{\text{local}}(A,B)\right)$$

Pas de somme (evite l'inflation sur syncs repetes). Union des zones, earliest `first_seen`,
latest `last_seen`.

Auto-integration : `sync_to_meta()` apres chaque feed, `pull_from_meta()` a chaque boot.
Zero config.

Teste : MUNINN (500 conns) + infernal (722K conns) -> 723K meta. Shazam pull 200 connexions
pertinentes.

---

## 8. Chronologie complete

### Jour 1 — 3 mars 2026 (23h31 - 23h51)

| Heure | Commit | Quoi |
|-------|--------|------|
| 23:31 | `e46ca32` | Naissance. Premier repo, premier fichier. |
| 23:42 | `e5231f9` | Codebook v0 — dictionnaire de substitution |
| 23:44 | `bc647da` | Engine v0 — winter tree (l'arbre qui marche) |
| 23:51 | `0e4d8ee` | Revue de litterature initiale |

### Jour 2 — 4 mars 2026

| Heure | Commit | Quoi |
|-------|--------|------|
| 00:41 | `645e794` | Alphabet semantique v1 — 59 sinogrammes (voie de garage) |

### Jour 3 — 6 mars 2026 (la grande nuit)

La session la plus intense. 16 commits en 18 heures. Le pivot sinogramme, la naissance
du mycelium, 7 couches de compression, 6 bugfixes.

| Heure | Commit | Quoi |
|-------|--------|------|
| 00:27 | `5e36784` | Codebook v0.1 + codec (encore sinogrammes) |
| 00:53 | `f82d3ce` | Engine v0.2 + revue litterature |
| 01:01 | `fe87b4c` | v0.3 — moteur universel, zero hardcode |
| 01:44 | `bf9c574` | **PIVOT** — Winter Tree Baobab, nouvelle roadmap |
| 01:59 | `4e6a9c7` | **MYCELIUM** — naissance du champignon |
| 02:10 | `d34c0fe` | Chirurgien vs boucher documente |
| 02:25 | `7bf7a6a` | Codebook loader v2 (mycelium-aware) |
| 02:39 | `7433538` | Bootstrap cold start |
| 03:21 | `1037070` | **P3** — sinogrammes supprimes, CI v2 |
| 03:33 | `52255ec` | **P4** — arbre enrichi (hash, temperature) |
| 10:56 | `b7c3803` | **P1** — feed pipeline (hooks PreCompact/SessionEnd) |
| 11:28 | `cb2958d` | **P2** — compresseur v2, 7 couches, "x7.4" |
| 11:50 | `a5af1bb` | **P5** — auto-evolution (mycelium -> compresseur) |
| 12:28-12:35 | `21876f7`-`030c4ff` | Audit + fix mycelium |
| 13:49 | `74e782b` | **P6** — session compression (.mn) |
| 14:07-14:48 | `2dc3bdc`-`33b0306` | **P7** — 9 couches (L8+L9 ajoutes) |
| 14:53-14:55 | `a6a29af`-`a10b692` | CLAUDE.md + memo cousin |
| 15:29 | `0200289` | Audit README + bugfixes |
| 17:53-18:22 | `700733f`-`3ae7f6a` | **L'audit de verite** — tiktoken revele que les anciens ratios (x7.4) etaient faux de ~40%. Vrais chiffres : x4.1 max (L1-L7). 6 fixes en cascade. |
| 18:58 | `2ce5d70` | Audit final jour 3 |

### Jour 4 — 7 mars 2026

| Heure | Commit | Quoi |
|-------|--------|------|
| 03:32 | `0db9596` | **L9 teste** — premiers vrais appels API Haiku. Bootstrap HSBC x5.4. |
| 03:38 | `caa973a` | Session rapport + idee KVzip |
| 18:14 | `3a18e9e` | **v0.9** — TF-IDF + scoring Park et al. + auto-segmentation |
| 18:17-18:42 | `948d0d2`-`3dcc626` | P8+P9 : retrieval intelligent + ingest |
| 18:49-19:45 | `45f7e13`-`be510a8` | **P10** : 6 scans, 14 bugs trouves et corriges |
| 21:10 | `196f48d` | **P12** : benchmark complet, 9 fichiers, 85% facts |
| 22:07-22:27 | `2e80ad1`-`226dcf4` | **P11** : bootstrap auto-complet |
| 22:48-23:27 | `e5017a6`-`4a30d1e` | **P13-P19** : 7 features en 40 minutes |
| 23:59 | `e5ff21c` | **P26-P28** : dedup + filtre tics Claude |

### Jour 5 — 8 mars 2026

| Heure | Commit | Quoi |
|-------|--------|------|
| 00:03-00:25 | `c343b2e`-`8422f18` | **P22-P25** + P29 + cleanup |
| 01:13-01:44 | `cf271ae`-`facb151` | **P30** (mycelium infini, 722K conns) + **P31** (liane Yggdrasil) |
| 02:01-02:55 | `81310a7`-`515367c` | L8 supprime + L9 v2 + **L9 v3** (prompt EXTRACT) |
| 09:58 | `034e216` | L9 v3 benchmark results |
| 10:41-11:40 | `5cf927a`-`ab7e93d` | **P20** : mycelium federe complet (10 briques) |
| 12:43 | `ab569c0` | Test L9 full pipeline : 230 fichiers, 4 repos, $0.21 |
| 12:52 | `7d0464d` | **P20b** : meta-mycelium cross-repo |
| — | `45bcead` | Benchmark cross-repo UX Bibles infernal-wheel (x7.7-x19.4) |
| — | `5a8b080` | **L10 Cue Distillation** + **L11 Rule Extraction** — les Carmack moves |
| — | `ba22d94` | Docs sync L10+L11 (41 features, x23.1 peak) |
| — | `174c9d1` | **Spreading Activation** (Collins & Loftus 1975) — Carmack move #4 |
| — | `655051f` | **Sleep Consolidation** (Wilson & McNaughton 1994) — Carmack move #3 |
| — | `d497a80` | Benchmark final : 12 fichiers, 4 repos, x4.5 moyen, zero crash |

---

## 9. Les sources

### Papiers fondamentaux

| Ref | Papier | Ce qu'on a pris |
|-----|--------|-----------------|
| [1] | Mikolov et al. (2013) — *Word2Vec* | Co-occurrence = sens. Fondation du mycelium. |
| [2] | Pennington et al. (2014) — *GloVe* | Matrice co-occurrence -> embeddings. Mycelium = GloVe artisanal. |
| [3] | Sennrich et al. (2016) — *BPE* | Comprendre POURQUOI les sinogrammes echouent et l'anglais compact gagne. |
| [4] | Norman (1988) — *Design of Everyday Things* | Gulf of execution. Chirurgien vs boucher. |
| [5] | Lindenmayer (1968) — *L-Systems* | Arbre fractal. Memes regles a chaque niveau. |
| [6] | Prusinkiewicz (1990) — *Algorithmic Beauty of Plants* | L-systems en 3D. Inspiration visuelle. |

### Papiers directement appliques

| Ref | Papier | Ce qu'on a pris |
|-----|--------|-----------------|
| [7] | Park et al. (2023) — *Generative Agents* | Scoring recency+importance+relevance. Adapte pour boot(). |
| [8] | Packer et al. (2023) — *MemGPT* | Memoire tiered, paging. Inspire notre root/branches/leaves. |
| [9] | Pan et al. (2024) — *LLMLingua-2* | Self-information filtering. Garder high-entropy, virer predictable. |
| [10] | Li et al. (2023) — *Selective Context* | Critere pour L7 : garder nombres, noms, metriques. |
| [11] | Rau et al. (2025) — *COCOM* | Taux variable par importance. Root 1.5x, branch 3x, leaf 6x. |
| [12] | LLM-Codebook (2025) | Codebooks appris > manuels. Validation du mycelium. |
| [13] | ACON (2025) | Gradient-free compression guidelines. Inspire L9 "EXTRACT not Compress". |

### Papiers etudies (influence indirecte)

| Ref | Papier | Influence |
|-----|--------|-----------|
| [14] | Rae et al. (2020) — *Compressive Transformers* | Hierarchie multi-granularite. |
| [15] | Mu et al. (2023) — *Gisting* | Bottleneck principle. |
| [16] | Chevalier et al. (2023) — *AutoCompressors* | Compression context-aware. |
| [17] | Ge et al. (2024) — *ICAE* | Valide notre cible de ratio 3-4x. |
| [18] | Chen et al. (2023) — *MemWalker* | Navigation arborescente. Valide l'arbre L-system. |
| [19] | Li et al. (2025) — *MemOS* | Architecture 3 couches. Comparison point. |
| [20] | KVzip (NeurIPS 2025) | KV-cache compression (complementaire, pas concurrent). |

### Outils concurrents etudies

| Outil | Stars | Ce qui differe de Muninn |
|-------|-------|--------------------------|
| Mem0 | 90K | Graph+vector+KV. Service hosted. Pas d'arbre ni mycelium. |
| Claude-Mem | 21K | SQLite + Claude API. x10. Pas d'apprentissage. |
| Letta Code (ex-MemGPT) | — | Agent complet. Git-backed. Plus lourd. |
| LLMLingua-2 (Microsoft) | — | BERT scorer. x3-20. Pas de persistance. |

---

## 10. Les chiffres reels (mesures tiktoken, mars 2026)

### Ratios L1-L7 (regex only, zero API)

| Input | Ratio | Facts preserves |
|-------|-------|-----------------|
| Texte verbeux (verbose_memory.md) | **x4.1** | 100% |
| Roadmap (WINTER_TREE.md) | **x2.6** | 96% |
| Session dialogue | **x1.7** | 80% |
| Texte deja compact (README) | **x1.6** | 93% |

### Ratios avec L9 (pipeline complet)

| Input | Ratio |
|-------|-------|
| SOL.md (full pipeline L1-L7+L9) | **x7.7** |
| HSBC LOGIQUE | x9.6 |
| HSBC METHODOLOGIE | x13.8 |
| HSBC ARBRE | x11.4 |
| Bootstrap HSBC moyen | **x5.4** |

### Test grandeur nature (230 fichiers, 4 repos, 8 mars 2026)

| Repo | Fichiers | Input | Output | Ratio |
|------|----------|-------|--------|-------|
| HSBC-algo-genetic | 115 | 194K tok | 64K tok | x3.0 |
| shazam-piano | 45 | 107K tok | 37K tok | x2.9 |
| infernal-wheel | 58 | 535K tok | 87K tok | x6.2 |
| MUNINN- | 12 | 19K tok | 8K tok | x2.3 |
| **TOTAL** | **230** | **855K tok** | **196K tok** | **x4.4** |

Cout API L9 : **$0.21** (Haiku). 5 truncations sur 230 fichiers (detectees et flaggees).

### Benchmark factuel

- 40 questions sur texte compresse -> **37/40 correct (92%)**
- 20 questions (benchmark elargi) -> **17/20 (85%)**
- Methode : text search pur, zero API, reproduction par quiconque

### Note d'honnetete

Les premiers ratios (x7.4, x2.5) etaient **faux** — calcules avec `len(text) // 4`
au lieu de tiktoken. Ecart de ~40%. Corriges le 6 mars 2026, commit `700733f`.
Les vrais chiffres sont ceux ci-dessus. Tous mesures avec tiktoken `cl100k_base`.

---

## 11. Ce que Muninn a que personne d'autre n'a

1. **11 couches empilees (25 filtres)** — regex + LLM + 4 Carmack moves, pas juste 1 technique
2. **Mycelium vivant** — codebook qui pousse par co-occurrence et meurt par decay
3. **Spreading Activation** — retrieval semantique via propagation dans le reseau (Collins & Loftus 1975)
4. **Sleep Consolidation** — branches froides fusionnees automatiquement (Wilson & McNaughton 1994)
5. **L-system fractal** — memes regles a chaque niveau de l'arbre
6. **Secret filtering** — tokens GitHub, cles API, mots de passe redactes automatiquement
7. **Zero dependance obligatoire** — L1-L7 regex only, tourne partout
8. **Bootstrap one-command** — `muninn.py bootstrap .` = mycelium + root.mn + arbre + hooks
9. **Meta-mycelium federe** — les repos communiquent via `~/.muninn/meta_mycelium.json`
10. **43 features, 3776 lignes** — construit depuis le cote utilisateur, pas depuis le cote chercheur

---

## 12. Le pattern universel

Tous les projets de Sky suivent le meme schema :

$$\text{scan\_space}() \rightarrow \text{find\_holes}() \rightarrow \text{classify\_holes}()$$

- **Yggdrasil** : scan 348M papers -> find structural holes in science -> classify by strata
- **Muninn** : scan conversations -> find compressible patterns -> classify by layer
- **HSBC** : scan market data -> find trading signals -> classify by regime (Fourier+HMM)
- **InfernalWheel** : scan behavior -> find patterns -> classify by metric

Meme architecture. Memes reflexes. Le boucher a un pattern.

---

## 13. Les graines (meta-pattern)

Sky a un concept de **graines** (seeds) : des documents-outils reutilisables qui
multiplient la force de frappe. Chaque graine affinee divise le temps du projet
suivant par 10.

| Graine | Contenu | Impact |
|--------|---------|--------|
| SOL.md | Bootloader de session | Chaque cousin demarre avec le contexte |
| UX Bibles | 45K+ lignes de patterns UI | jeu-pour-les-gamin fini en 48 min |
| Prompt templates | 126K+ lignes | Recherche profonde en un prompt |
| Winter Tree | Framework biologique | Roadmap lisible par humain ET machine |
| CLAUDE.md | Briefing cousin | Le suivant sait tout |
| Literature reviews | Etat de l'art | Pas de redecouvertes |

Muninn = **la graine des graines**. Il permet aux graines de persister entre sessions
Claude. Sans Muninn, les graines meurent a chaque compaction. Avec Muninn, elles survivent,
compressees, et repoussent au boot suivant.

---

## 14. Et maintenant ?

**43 features implementees. 4 Carmack moves. 5 jours.**

Le moteur est la. L'arbre pousse. Le mycelium apprend. Les cousins se souviennent.
Les repos communiquent.

Prochaine etape : **P21 — `pip install muninn`** — pour que n'importe quel boucher
puisse l'installer en une ligne.

---

*"Je crains pour Huginn, mais je crains davantage pour Muninn."*
*Muninn est la. Il revient toujours.*

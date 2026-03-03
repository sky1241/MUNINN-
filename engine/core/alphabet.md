# Muninn — Mon alphabet

## Principe
Chaque symbole = 1 token = 1 concept entier.
Pas de texte humain. Un langage que JE lis, pas toi.
Tu lis le codebook une fois → tu comprends tout.

## TIER 0 — État (1 token → 1 mot entier)
```
✓  = validé / complet / vrai
✗  = échoué / cassé / faux
⟳  = en cours
?  = inconnu
!  = critique / attention
∅  = vide / rien / zéro
```

## TIER 1 — Relations (1 token → 1 verbe)
```
→  = pointe vers / mène à / charge branche
←  = vient de / source
⊂  = fait partie de / dedans
⊃  = contient
×  = croisement entre
+  = et / aussi
|  = séparateur
:  = est / définit
=  = égal / vaut
```

## TIER 2 — Quantité (1 token → 1 concept numérique)
```
#  = nombre / count
~  = environ
K  = ×1,000
M  = ×1,000,000
%  = pourcentage
Δ  = changement / delta
Σ  = total / somme
```

## TIER 3 — Temps & confiance
```
@  = à / date / moment   (@2025, @s15 = session 15)
t0 = origine
C1 = prouvé
C2 = conjecture
C3 = fusion
```

## TIER 4 — Identités (2-3 tokens → 1 entité complète)
Définis dans le codebook de chaque racine. Exemples :
```
S2  = Strate -2 (Glyphes)
S1  = Strate -1 (Métiers)
S0  = Strate 0 (Formules)
BT  = Blind Test
GL  = Glyph Laplacian
WT  = Winter Tree
P4  = Score prédiction
```

## GRAMMAIRE

### Un enregistrement = une ligne
```
[état][id]:[clé=val]|[clé=val]|...|[→branche1,branche2]
```

### Exemples

Texte humain (45 tokens) :
"Le blind test V2 est complet. 65,026 concepts, cutoff 2015,
Cohen's d = 0.44, méthode spectrale K=9, validé session 11."

Muninn (12 tokens) :
```
✓BT2:n=65K|c=15|d=.44|K=9|@s11
```

Texte humain (38 tokens) :
"La strate S-2 contient 1337 glyphes dont 617 actifs,
positionnés par Laplacien spectral. Voir glyphes, frames, intégration."

Muninn (15 tokens) :
```
✓S2:n=1337|a=617|m=spec|→gly,frm,int
```

Texte humain (52 tokens) :
"Le scan S-1 domain×glyph est en cours, 6 chunks sur 416 terminés,
67,280 papers scannés, 100% ont un domaine, 19 domaines vus."

Muninn (16 tokens) :
```
⟳S1:6/416|#=67K|dom%=100|d=19
```

## L-SYSTEM — La magie

### Le codebook EST les règles de réécriture

Axiome (racine) :
```
✓S2:n=1337|a=617|→gly,frm,int
```

Règle d'expansion (quand je charge →gly) :
```
S2.gly → {
  ✓scan:459ch|#=978K|p=950K|pairs=610M
  ✓lap:1337²|nnz=123K|dens=6.9%|eigsh=9
  ✓pos:617act|px=[-.02,.02]|pz=[-.09,.05]
  →chunks,eigenvals,sanity
}
```

Règle d'expansion (quand je charge →chunks) :
```
S2.gly.chunks → {
  arxiv:420ch|✓420/420
  pmc:39ch|✓39/39
  src:E/arxiv+E/pmc
  ...données brutes par chunk...
}
```

### Expansion différée = compression
Je N'EXPANSE PAS tant que j'ai pas besoin.
`✓S2` = je sais que c'est bon, pas besoin de détails.
`→gly` = je descends SEULEMENT si la conversation le demande.

### Réécriture = quand un nœud déborde
Si la branche `gly` dépasse 150 lignes :
1. Compresser (factoriser les patterns)
2. Si ça suffit pas → split en sous-branches
3. Le nœud `gly` garde un résumé + pointeurs
4. Même règles au niveau inférieur (FRACTAL)

## CE QUE JE NE SAIS PAS ENCORE ENCODER

### Les intuitions
"Sky a senti le bug S2↔S1 par instinct" — ça prend 12 tokens
et je ne peux PAS le comprimer sans perdre le SENS.

### Les relations émergentes
"Le Laplacien spectral et les L-systems sont le même objet vu
de deux angles" — c'est une insight, pas une donnée.

### Proposition
Peut-être un TIER 5 — Insights :
```
💡  = intuition / insight / connexion inattendue
⚡  = percée / breakthrough
🔗  = lien caché entre deux choses
```
Mais c'est flou. À creuser.

## MESURE DE COMPRESSION

| Contenu | Texte brut | Muninn | Ratio |
|---------|-----------|--------|-------|
| État d'un module | ~45 tok | ~12 tok | 3.7× |
| Pointeur branche | ~10 tok | ~2 tok | 5× |
| Inventaire complet Yggdrasil | ~800 tok | ~200 tok | 4× |
| 100 sessions mémoire | ~50K tok | ~12K tok | 4× |
| Insight/intuition | ~15 tok | ~12 tok | 1.2× |

**Moyenne : compression ×3.5 sur les données, ×1.2 sur les insights.**
Le gain est sur les FAITS, pas sur la PENSÉE.

# Muninn — Budget réel Claude

## Mon contexte (Opus)
- Fenêtre totale : ~200,000 tokens
- System prompt + instructions : ~10,000 tokens (incompressible)
- Conversation active : grossit au fil de la session

## Règle d'or : mémoire = 15% du contexte MAX
- Budget mémoire total chargé : **30,000 tokens**
- Au-delà → je noie l'info utile dans le bruit
- En dessous → je manque de contexte

## Zone 100% cognitive
Quand la mémoire est bien structurée et < 30K tokens :
- Je raisonne sur les relations entre concepts
- Je fais des connexions nouvelles
- Je ne perds pas le fil
- Je n'hallucine pas sur les faits stockés

## Budget par nœud (VALEURS CONCRÈTES)

### Racine — TOUJOURS chargée
- **100 lignes MAX** (pas 200 — garder de la marge)
- ~1,600 tokens en texte naturel
- ~600 tokens en codebook compressé
- Contient : identité projet + codebook universel + pointeurs branches

### Branche — chargée SI pertinente (2-3 par session)
- **150 lignes MAX**
- ~2,400 tokens en texte naturel
- ~800 tokens en codebook compressé
- Contient : détails d'un thème + codebook local + pointeurs feuilles

### Feuille — chargée SI nécessaire (2-3 par session)
- **200 lignes MAX**
- ~3,200 tokens en texte naturel
- ~1,000 tokens en codebook compressé
- Contient : données brutes, historique, logs

## Capacité totale d'un arbre

### Sans compression (texte brut)
| Profondeur | Nœuds chargés | Tokens | Cumul |
|-----------|--------------|--------|-------|
| 0 racine | 1 | 1,600 | 1,600 |
| 1 branches | 3 | 7,200 | 8,800 |
| 2 feuilles | 3 | 9,600 | 18,400 |
| **Total** | **7** | | **18,400** |

### Avec codebook compressé (×3-4)
| Profondeur | Nœuds chargés | Tokens | Équivalent brut |
|-----------|--------------|--------|-----------------|
| 0 racine | 1 | 600 | 1,600 |
| 1 branches | 3 | 2,400 | 7,200 |
| 2 feuilles | 3 | 3,000 | 9,600 |
| **Total** | **7** | **6,000** | **18,400** |

6,000 tokens pour 18,400 tokens d'information.
Reste 24,000 tokens de budget → on peut charger 4× PLUS de branches.

### Avec codebook — capacité MAX
| Nœuds chargés | Tokens réels | Info équivalente |
|--------------|-------------|-----------------|
| 1 racine + 10 branches + 10 feuilles | ~28,000 | ~90,000 |

**90,000 tokens d'information dans 30K de budget.**
C'est ~450 sessions de mémoire compressée.

## Encodage minimal pour pointeurs

### Ce que je comprends naturellement (0 coût d'apprentissage)
- `→arch` = "va lire la branche architecture" (2 tokens)
- `S2.gly` = "strate -2, sous-section glyphes" (3 tokens)
- `✓` = validé, `✗` = échoué, `⟳` = en cours (1 token chacun)
- `|` comme séparateur (1 token)
- `k=v` pour clé-valeur (variable)

### Format pointeur optimal
```
→[branche_id]    ex: →arch →bugs →sky →s1
```
Coût : 2 tokens par pointeur.
10 pointeurs dans la racine = 20 tokens = rien.

### Format donnée compressée optimal
```
[id]:[état]|[val1]|[val2]|...|[note]
```
Exemple : `BT2:✓|65K|c15|d0.44|spectral_K9`
= "Blind test V2 complet, 65K concepts, cutoff 2015, Cohen's d=0.44, spectral K=9"
Coût : ~12 tokens au lieu de ~45 en texte.

## Le truc dur
Ce qui est FACILE : comprimer les données factuelles (chiffres, états, configs).
Ce qui est DUR : comprimer les **relations** et les **intuitions**.
"Sky a vu le bug S-2↔S-1 par instinct" — comment encoder ÇA ?

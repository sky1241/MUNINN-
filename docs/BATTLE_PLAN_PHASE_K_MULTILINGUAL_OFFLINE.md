# Phase K — Multilingual offline (zéro API key)

> **Décision Sky 2026-05-13** : on commence par l'option simple (dictionnaire
> JSON statique). Plus tard, quand on voudra du "vrai programme" qui marche
> pour toutes les langues, on passe au LaBSE embeddings.
>
> **Pourquoi cette Phase existe** : aujourd'hui `ConceptTranslator`
> (`mycelium_db.py:1168`, TIER3 S4) traduit les concepts FR→EN via l'API
> Anthropic Haiku. Ça coûte des crédits + dépend d'une clé API + dépend
> d'un service tiers externe. Pour un projet open-source mémoire universelle,
> c'est un frein UX (user lambda doit avoir un compte Anthropic).
>
> **Le G.1 du 12 mai** (filtre stopword degré-based universel) résout déjà
> 80% du symptôme côté `mycelium_recall_meta` (plus de `pas/est/les` qui
> dominent). Phase K résout les 20% restants : la **fusion cross-langue**
> de concepts ("arbre" et "tree" deviennent un seul nœud au lieu de deux).

---

## Sous-phase K.1 — Dictionnaire JSON statique (CHEMIN COURT, 1.2.0)

**Objectif** : remplacer l'appel Haiku par un lookup dans un dict FR→EN
embarqué dans le wheel.

### Effort estimé : 2-3h

### Implem

1. **Générer le dict** (one-shot, fait UNE fois) :
   - Source : top 10 000 mots FR par fréquence (Wikipedia FR ngrams)
   - Traduction batch via Haiku API en local (coût ~1$ une fois)
   - Output : `engine/core/data/lexicons/fr_en.json` (~100 KB)
   - Format : `{"arbre": "tree", "mémoire": "memory", ...}`
   - Alternative source 100% gratuite : kaikki.org/frenchdictionary.json
     (parse Wiktionary) ou freedict.org (XML GPL)

2. **Swap le backend dans `ConceptTranslator`** :
   ```python
   # mycelium_db.py:1168 ConceptTranslator
   # Avant : _translate_batch appelle anthropic.messages.create
   # Après : _translate_batch fait DICT.get(word, word)
   _FR_EN_DICT = json.loads(
       (Path(__file__).parent / "data" / "lexicons" / "fr_en.json").read_text()
   )
   def _translate_batch(self, batch: list[str]) -> dict[str, str]:
       return {w: _FR_EN_DICT.get(w.lower(), w) for w in batch}
   ```
   ~20 lignes de code change.

3. **Garder le fallback API** (opt-in via env var) :
   - Default : lookup dict only, passthrough si mot absent
   - Si `ANTHROPIC_API_KEY` set ET `MUNINN_TRANSLATE_FALLBACK_API=1` →
     fallback Haiku pour mots absents du dict
   - Cache SQLite existant continue de fonctionner

### Test pin

`tests/test_k1_offline_translator.py` :
- `test_k1_arbre_to_tree` : sans API key, `normalize(['arbre'])` → `['tree']`
- `test_k1_unknown_passthrough` : `normalize(['sphincter'])` → `['sphincter']`
  (passthrough propre, pas de crash)
- `test_k1_dict_shipped_in_wheel` : after `pip install`, le fichier
  `engine/core/data/lexicons/fr_en.json` est présent
- `test_k1_no_api_call_required` : monkeypatch anthropic.messages.create
  pour qu'il raise, run normalize → doit fonctionner quand même

### Pourquoi K.1 d'abord (et pas direct K.2)

| Critère | K.1 dict JSON | K.2 LaBSE |
|---|---|---|
| Taille embarquée | 100 KB | 500 MB |
| Nouvelle dépendance pip | 0 | sentence-transformers (~50 MB) |
| Code à changer | ~20 lignes | refactor mycelium (~500 lignes) |
| Install user | rien | download modèle 500 MB au 1er run |
| Couvre 95% concepts FR courants | ✅ | ✅✅ |
| Couvre toutes langues sans config | ❌ (FR-EN only) | ✅✅ |
| Compatible 1.2.0 release | ✅ | ❌ (trop gros change) |

K.1 = bouchon pragmatique pour 1.2.0. K.2 = vraie solution long-terme pour 2.0.

---

## Sous-phase K.2 — LaBSE cross-lingual embeddings (CHEMIN LONG, 2.0.0)

**Objectif** : remplacer la traduction par de la **similarité sémantique
cross-langue**. "arbre", "tree", "Baum" (DE), "árbol" (ES), "木" (JP)
ont tous des vecteurs proches dans l'espace LaBSE → on les fusionne
automatiquement dans le mycelium sans traduire.

### Effort estimé : 1-2 semaines (vraie phase produit, pas un chunk)

### Avantages vs K.1

- Marche pour TOUTES les langues d'un coup (pas juste FR→EN)
- Pas besoin de maintenir des dicts par paire de langues
- Les noms propres, jargon, mots techniques sont gérés naturellement
- Compatibility avec compress L9 (les embeddings peuvent guider la sélection)

### Coûts

- Modèle LaBSE : 500 MB (HuggingFace `sentence-transformers/LaBSE`)
  - Alternative plus légère : `paraphrase-multilingual-MiniLM-L12-v2` (118 MB)
- Dépendance pip : `sentence-transformers` (~50 MB transitives)
- Refactor mycelium : stocker un embedding par concept en plus du
  nom littéral. Schema SQLite changement (nouvelle colonne BLOB `embedding`)
- CPU inference : ~10 ms par concept sur laptop moderne (CPU only)
- GPU optionnel : 10x plus rapide

### Implem (esquisse)

1. **Ajout dépendance + modèle download au boot** :
   ```python
   from sentence_transformers import SentenceTransformer
   # Default : MiniLM (léger)
   model = SentenceTransformer(
       os.getenv("MUNINN_EMBEDDINGS_MODEL",
                 "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
   )
   ```

2. **Schema migration mycelium_db** :
   ```sql
   ALTER TABLE concepts ADD COLUMN embedding BLOB;
   CREATE INDEX idx_concepts_embedding_norm ON concepts(LENGTH(embedding));
   ```

3. **Fusion cross-langue au lieu de translation** :
   - À chaque `observe(text)`, compute embeddings des concepts extraits
   - Cherche concepts existants avec cosine_similarity > 0.85
   - Si match trouvé : fusion (incrémente count edge au lieu de créer nouveau nœud)
   - Sinon : nouveau concept avec son embedding stocké

4. **Backward compat** : `MUNINN_EMBEDDINGS=0` → fallback K.1 dict statique
   (utile pour tests rapides, environnements sans GPU)

### Test pin

- Vérifier cosine("arbre", "tree") > 0.80
- Vérifier cosine("compression", "decompression") < 0.50 (anti-faux-positif)
- Vérifier que le mycelium ne crée pas de doublons FR/EN sur un transcript bilingue
- Benchmark : recall qualité avant/après sur 10 transcripts FR + EN mélangés

### Décisions à prendre avant K.2

1. **Modèle** : LaBSE (500 MB, qualité top) vs MiniLM (118 MB, qualité OK) ?
2. **Stockage embeddings** : SQLite BLOB ou fichier .npy séparé ?
3. **Threshold fusion** : 0.85 cosine ? Tuner empiriquement.
4. **Fallback offline** : si modèle pas dispo → K.1 dict ou pure passthrough ?
5. **Doctor check** : `muninn-mem doctor` doit signaler si modèle absent ?

---

## Ordre d'exécution

```
1.2.0 release (court terme)
    ↓
K.1 dict JSON statique         ← 2-3h, faible risque, drop-in
    ↓
1.2.0 stable + retours users
    ↓
... autres priorités (H.6b vault, Phase J cleanup zombies, Scanner) ...
    ↓
2.0.0 release (long terme)
    ↓
K.2 LaBSE embeddings           ← 1-2 semaines, vraie phase produit
    ↓
muninn-memory devient un vrai
moteur mémoire multilingual 100%
offline zéro-API.
```

---

## Décisions Sky enregistrées le 2026-05-13

- ✅ K.1 maintenant (option 1 dict JSON simple)
- ✅ K.2 pour plus tard (option 3 LaBSE), avant la "vraie" release "vrai programme"
- ❌ Option 2 Argos Translate : skip (lourd pour valeur ajoutée vs K.1)

---

## Notes pour futur Claude qui exécutera K.1

- L'interface publique `ConceptTranslator.get().normalize_concepts(words)`
  ne change PAS. Seul le backend interne (`_translate_batch`) est swappé.
- Tous les tests existants (44 tests lang* + brick1/brick4) doivent
  continuer de passer après K.1.
- Le cache SQLite `~/.muninn/translations.db` est conservé : K.1 peut
  pre-populer le cache au premier boot avec le contenu du dict JSON.
- L'env var `ANTHROPIC_API_KEY` cesse d'être REQUIRED pour la traduction
  (elle reste required pour L9 compression — pas le même usage).

---

## Sources de données K.1 candidates

| Source | Format | Licence | Mots couverts | Avantage |
|---|---|---|---|---|
| Wiktionary FR (kaikki.org) | JSON dump | CC-BY-SA | 800k+ | Le + complet |
| FreeDict fra-eng | TEI XML | GPL | 17k | Léger, propre |
| Wikipedia ngrams top 10k | TSV à parser | CC-BY-SA | 10k | Couvre l'essentiel |
| Genere via Haiku (one-shot) | JSON sur mesure | Anthropic | tunable | Qualité top mais 1$ one-shot |

Recommandation : kaikki.org pour la source brute → trim à 20k mots les plus
fréquents → ship le JSON dans `engine/core/data/lexicons/fr_en.json`.

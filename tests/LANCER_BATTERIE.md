# MISSION: Batterie de tests reels Muninn — 84 tests (V4 post-corrections)

Tu as 3 fichiers de specs dans `tests/`:
- `PROMPT_BATTERY_V3_PART1.md` — regles, setup, monkey-patch meta, signatures mycelium, categories 1-5
- `PROMPT_BATTERY_V3_PART2.md` — categories 6-10 (formules avec calculs a la main)
- `PROMPT_BATTERY_V3_PART3.md` — categories 11-14 (pipeline, edge cases, coherence)

## Ce que tu dois faire

1. Lis les 3 fichiers PART1, PART2, PART3 dans `tests/` en ENTIER avant de commencer
2. Execute le SETUP COMMUN de PART1 (cree le temp dir + monkey-patch le meta)
3. Lance les 84 tests dans l'ordre des categories (1 a 14)
4. Ecris chaque resultat dans `tests/RESULTS_BATTERY_V4.md` AU FUR ET A MESURE
5. A la fin, ajoute un resume: X PASS / Y FAIL / Z SKIP + top 5 bugs + temps total

## Regles critiques

- Tu ne modifies JAMAIS le code source de Muninn (engine/core/*)
- Tu ne proposes JAMAIS de fix — tu constates
- Le monkey-patch meta est OBLIGATOIRE (sinon tu pollues 795Mo de donnees reelles)
- Chaque test a des metriques chiffrees — calcule le resultat ATTENDU avant d'appeler le code
- Si le code donne un resultat different du calcul a la main (ecart > 5%) → FAIL
- Un test qui grep le source au lieu d'appeler le code = FAUX test = interdit

## Contexte V4: 20 bugs corriges dans le commit 6ec4a0b

Le run precedent (V3) a donne 38 PASS, 33 FAIL. 20 bugs ont ete corriges (8 engine, 12 tests).
Les specs PART1/PART2/PART3 ont ete mises a jour pour refleter ces corrections.

### Corrections engine a verifier (les plus critiques):
1. **S4 is_english()** — word.isascii() → mots ASCII ne sont plus traduits par Haiku
2. **L3 phrases** — `\s+` dans les regex L3 (double espaces laisses par L2)
3. **P27 tool_result** — supprime aussi le `-> ...` qui suit un Read supprime
4. **P28 seuil** — 25→10 chars (petites phrases apres tic verbal survivent)
5. **P38 format** — JSON single-line avec "messages" key + markdown ## detectes
6. **KIComp** — lignes taggees D>/B>/F>/E>/A> protegees du drop second-pass
7. **observe() zones** — mode federe stocke les zones en memoire (pas juste SQLite)
8. **boot() + observe_text** — errors="ignore" sur .mn corrompus + regex {3,} (MIN_CONCEPT_LEN=3)

### Pieges connus (eviter ces erreurs dans les tests):
- "data" est un stopword → utiliser "nucleus" ou autre mot non-stopword
- detect_anomalies() retourne des tuples (name, degree), pas des strings
- VADER score "No issues" comme negatif (le mot "issues")
- `\b15\b` ne matche pas "15ms" → utiliser `"15" in text`
- extract_tags ignore les keywords qui apparaissent < 2 fois
- muninn._CB (cache codebook) peut polluer entre tests → reset a None
- zlib NCD est unreliable sur des strings courtes → utiliser des phrases longues
- Le max bonus theorique est 0.59 (pas 0.49)

## Fichiers cles

- Engine: `c:\Users\ludov\MUNINN-\engine\core\muninn.py` (4578 lignes)
- Mycelium: `engine\core\mycelium.py` (~1250 lignes)
- SQLite backend: `engine\core\mycelium_db.py`
- Tokenizer: `engine\core\tokenizer.py`
- Python: `C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe`

## Resultat attendu

Le run V3 post-fix donnait 61 PASS, 0 FAIL, 4 SKIP.
Les 4 SKIP sont: L9 (pas de cle API), V8B (pas implemente), P20c (pas implemente), C4 (skip).
Si tu trouves des FAIL → c'est un NOUVEAU bug. Documente-le avec la ligne exacte et le root cause.

Go.

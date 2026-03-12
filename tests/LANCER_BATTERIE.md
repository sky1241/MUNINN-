# MISSION: Batterie de tests reels Muninn — 84 tests

Tu as 3 fichiers de specs dans `tests/`:
- `PROMPT_BATTERY_V3_PART1.md` — regles, setup, monkey-patch meta, signatures mycelium, categories 1-5
- `PROMPT_BATTERY_V3_PART2.md` — categories 6-10 (formules avec calculs a la main)
- `PROMPT_BATTERY_V3_PART3.md` — categories 11-14 (pipeline, edge cases, coherence)

## Ce que tu dois faire

1. Lis les 3 fichiers PART1, PART2, PART3 dans `tests/` en ENTIER avant de commencer
2. Execute le SETUP COMMUN de PART1 (cree le temp dir + monkey-patch le meta)
3. Lance les 84 tests dans l'ordre des categories (1 a 14)
4. Ecris chaque resultat dans `tests/RESULTS_BATTERY_V3.md` AU FUR ET A MESURE
5. A la fin, ajoute un resume: X PASS / Y FAIL / Z SKIP + top 5 bugs + temps total

## Regles critiques

- Tu ne modifies JAMAIS le code source de Muninn (engine/core/*)
- Tu ne proposes JAMAIS de fix — tu constates
- Le monkey-patch meta est OBLIGATOIRE (sinon tu pollues 795Mo de donnees reelles)
- Chaque test a des metriques chiffrees — calcule le resultat ATTENDU avant d'appeler le code
- Si le code donne un resultat different du calcul a la main (ecart > 5%) → FAIL
- Un test qui grep le source au lieu d'appeler le code = FAUX test = interdit

## Fichiers cles

- Engine: `c:\Users\ludov\MUNINN-\engine\core\muninn.py` (4578 lignes)
- Mycelium: `engine\core\mycelium.py` (~1250 lignes)
- SQLite backend: `engine\core\mycelium_db.py`
- Tokenizer: `engine\core\tokenizer.py`
- Python: `C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe`

Go.

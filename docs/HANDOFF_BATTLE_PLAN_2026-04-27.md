# Handoff Battle Plan — 2026-04-27

**De :** session 2026-04-25/27 (audit complet + analyse Ygg)
**Pour :** prochaine session Claude qui attaque chunk par chunk

---

## Contexte minimal pour reprendre

Repo : `/home/sky/Bureau/MUNINN-`. Branche `main`, dernier commit `8844212`.

Working tree dirty :
- `memory/tree.json` — régression hook auto (b0002.lines 29 → 3, déjà fix dans 97b93f0/1f6f468, recasse à chaque hook), à NE PAS recommit
- `muninn/ui/cube_live.py` — patch buggé de la session précédente (path Mycelium foiré, sera fixé en CHUNK 2)

3 docs YGG_*.md untracked (rapports de recherche cousin Ygg, à git add quand ready).

---

## Trouvailles clés de l'audit (lire avant d'attaquer)

### 🔴 BUG CENTRAL — explique le gap 1/10 (qwen UX) vs 53/61 (Sonnet API)

[engine/core/cube_providers.py:632-658](engine/core/cube_providers.py#L632) — la branche FIM **bypasse Fix 20** quand `provider.supports_fim=True` :

```python
# Ligne 632 — FIM checked FIRST, return immédiat
if self.provider.supports_fim and before and after:
    return self.reconstruct_fim(...)  # <-- LLM appelé, Fix 20 jamais atteint

# Ligne 650 — Fix 20 (auto-SHA SANS LLM) — UNIQUEMENT atteint si pas FIM
if ast_hints:
    _pre_am = _build_full_anchor_map(...)
    if len(_pre_am) >= n_lines:
        return _nc(cube.content)
```

**Conséquences mesurées :**
- Sonnet (`supports_fim=False`) → Fix 20 atteint → **38/61 cubes auto-SHA** (62%)
- qwen (`supports_fim=True`) → Fix 20 bypassé → **0 cubes auto-SHA**, tout passe par LLM qui converge mal → 1/10

**Test live confirmant le bug** (étape 5 de l'audit) :
- cube 1 du btree_google.go : 2/2 lignes anchored → DEVRAIT auto-SHA via Fix 20
- run réel sur ce cube via reconstruct_cube : `fim_generate=1, generate=1, ncd=0.758` → Fix 20 PAS pris

**Fix proposé (CHUNK 1) :** déplacer Fix 20 AVANT le test FIM. C'est 5 lignes à déplacer.

### Autres findings

- Mycelium 847 MB **plein** (127K concepts, 5.9M edges, 156K fusions) — mais pas branché à l'UX (bug A1)
- BUG-091 OPEN : 11/17 fichiers entre `engine/core/` et `muninn/` ont divergé. Si on touche cube_providers.py il faut mirror dans muninn/ (mais actuellement les 2 sont SAME hash).
- `reconstruct_line_by_line` (B42) jamais appelée en production, seulement smoke-test
- get_perplexity bug (commit c8a81a2) : fix bien en place, ne pas re-toucher
- Ollama seed semble ignoré ou qwen trop déterministe : 3 seeds → output identique mot pour mot
- 2275 tests pytest collectés au total

---

## Plan de bataille — 8 chunks (6 obligatoires + 2 optionnels)

Chaque chunk : 1 fix = 1 commit = 1 push. Pas de batch. RULE 4 anti-bullshit : aucun "fait" sans output `pytest`/`git push` collé dans la conversation.

---

### CHUNK 1 (CRITIQUE) — Fix 20 avant FIM

**Fichier :** [engine/core/cube_providers.py](engine/core/cube_providers.py)
**Lignes :** 632-658 (réordonnancement)

**Forge OBLIGATOIRE** (RULE 5) :
```bash
python forge.py --gen-props engine/core/cube_providers.py
python -m pytest tests/test_props_cube_providers.py -q
```

**Mirror BUG-091 :** ce fichier est actuellement SAME entre `engine/core/` et `muninn/`. Vérifier que `muninn/cube_providers.py:632-658` reçoit le même fix. Hash check après :
```bash
md5sum engine/core/cube_providers.py muninn/cube_providers.py
# les 2 doivent être identiques
```

**Diff proposé :**

État actuel (lignes 632-658) :
```python
        # Try native FIM first if provider supports it
        if self.provider.supports_fim and before and after:
            ext_prefix = "\n".join(c.content for c in before)
            ext_suffix = "\n".join(c.content for c in after)
            return self.reconstruct_fim(ext_prefix, ext_suffix, max_tokens)

        # ─── FIM prompt: code with hole + constraints ────────────────
        try:
            from cube import normalize_content as _nc
        except ImportError:
            try:
                from engine.core.cube import normalize_content as _nc
            except ImportError:
                _nc = lambda t: t.strip()
        n_lines = len(_nc(cube.content).split('\n'))

        # Fix 20: If ALL lines are anchored, skip LLM entirely.
        if ast_hints:
            _orig_lines = _nc(cube.content).split('\n')
            _ext = os.path.splitext(cube.file_origin or '')[1].lower()
            _pre_am = _build_full_anchor_map(
                ast_hints, _orig_lines, n_lines, _ext)
            if len(_pre_am) >= n_lines:
                return _nc(cube.content)
```

État cible :
```python
        # Normalize content + line count (needed for Fix 20 + FIM fallback)
        try:
            from cube import normalize_content as _nc
        except ImportError:
            try:
                from engine.core.cube import normalize_content as _nc
            except ImportError:
                _nc = lambda t: t.strip()
        n_lines = len(_nc(cube.content).split('\n'))

        # Fix 20 FIRST: if ALL lines are anchored, skip LLM entirely.
        # Model-agnostic: works for any provider, no LLM call.
        if ast_hints:
            _orig_lines = _nc(cube.content).split('\n')
            _ext = os.path.splitext(cube.file_origin or '')[1].lower()
            _pre_am = _build_full_anchor_map(
                ast_hints, _orig_lines, n_lines, _ext)
            if len(_pre_am) >= n_lines:
                return _nc(cube.content)

        # Then native FIM if provider supports it
        if self.provider.supports_fim and before and after:
            ext_prefix = "\n".join(c.content for c in before)
            ext_suffix = "\n".join(c.content for c in after)
            return self.reconstruct_fim(ext_prefix, ext_suffix, max_tokens)

        # ─── FIM prompt fallback: code with hole + constraints ────────
```

**Test fonctionnel après fix (cible 38/61 auto-SHA sur qwen) :**
```bash
PYTHONPATH="$(pwd):$(pwd)/engine/core" python -c "
from engine.core.cube_providers import OllamaProvider, reconstruct_cube
from engine.core.cube import subdivide_file, extract_ast_hints, enrich_hints_with_file_context

# Tracer fim_generate + generate
fim, gen = [], []
ofim, ogen = OllamaProvider.fim_generate, OllamaProvider.generate
OllamaProvider.fim_generate = lambda s,*a,**k: (fim.append(1), ofim(s,*a,**k))[1]
OllamaProvider.generate = lambda s,*a,**k: (gen.append(1), ogen(s,*a,**k))[1]

f='tests/cube_corpus/btree_google.go'
content=open(f).read()
cubes=subdivide_file(f,content,target_tokens=112,level=0)
p=OllamaProvider(model='qwen2.5-coder:7b')
auto_sha=0
for i,c in enumerate(cubes):
    fim.clear(); gen.clear()
    h=extract_ast_hints(c); h['_raw_content']=c.content
    h=enrich_hints_with_file_context(h, content)
    ne=[x for x in cubes if x.id!=c.id][:9]
    r=reconstruct_cube(c, ne, p, ncd_threshold=0.0, ast_hints=h)
    if r.exact_match and len(fim)==0 and len(gen)==0:
        auto_sha+=1
print(f'auto-SHA: {auto_sha}/{len(cubes)}')
"
# Cible : auto_sha >= 38
```

**Commit message :** `fix(engine): Fix 20 anchor-skip avant FIM — auto-SHA marche sur qwen comme sur Sonnet`

**Gain attendu :** UX qwen passe de **1/10 → ~38/61** (62%) sans changer de modèle.

---

### CHUNK 2 — Mycelium path UX

**Fichier :** [muninn/ui/cube_live.py](muninn/ui/cube_live.py)
**Lignes :** 96-103 (mes patches non commités contiennent le bug)

**Pas forge** (UI only, pas dans engine/).

**Diff proposé :**

État actuel (mon patch buggé) :
```python
            from engine.core.mycelium import Mycelium
        except ImportError as e:
            self.error.emit(f"Cannot import engine: {e}")
            return

        repo_root = Path(__file__).resolve().parents[2]
        myc_dir = repo_root / ".muninn"
        myc_dir.mkdir(parents=True, exist_ok=True)
        mycelium = Mycelium(str(myc_dir / "cube_mycelium.db"))  # <-- BUG: path est un dossier
```

État cible :
```python
            from engine.core.mycelium import Mycelium
        except ImportError as e:
            self.error.emit(f"Cannot import engine: {e}")
            return

        repo_root = Path(__file__).resolve().parents[2]
        # Mycelium attend repo_path, pas un fichier DB :
        # il fait <repo>/.muninn/mycelium.db automatiquement
        mycelium = Mycelium(repo_root)
```

**Test :**
```bash
PYTHONPATH=$(pwd) python -c "
from pathlib import Path
from engine.core.mycelium import Mycelium
m = Mycelium(Path('/home/sky/Bureau/MUNINN-'))
assert m.db_path == Path('/home/sky/Bureau/MUNINN-/.muninn/mycelium.db'), f'wrong path: {m.db_path}'
assert m.db_path.exists(), 'db missing'
assert m.db_path.stat().st_size > 800_000_000, 'db too small'
print(f'OK path={m.db_path} size={m.db_path.stat().st_size:,}')
m.close()
"
```

**Commit message :** `fix(ux): cube_live utilise vraiment le mycelium 847MB du repo`

---

### CHUNK 3 — Tutorial Navi dismiss-able au clic

**Fichier :** [muninn/ui/navi.py](muninn/ui/navi.py)
**Lignes :** ~360-410 (autour de `show_bubble`/`hide_bubble`)

**Pas forge** (UI only).

**Action :** ajouter un `mousePressEvent` qui :
1. Détecte si le clic est dans la zone de la bulle
2. Si oui : appelle `self.hide_bubble()` + `self._tutorial_active = False`
3. → libère le bouton "Scanner un repo" caché par la bulle

**Test manuel :** lancer UX, cliquer sur la bulle Navi, vérifier que le bouton "Scanner un repo" devient cliquable.

**Commit message :** `fix(ux): bulle Navi dismiss-able au clic, libère le bouton scan`

---

### CHUNK 4 — `/reconstruct` require `/scan` préalable

**Fichier :** [muninn/ui/terminal.py](muninn/ui/terminal.py)
**Méthode :** `_cmd_reconstruct` (ligne 545)

**Pas forge** (UI only).

**Diff proposé :** ajouter au début de `_cmd_reconstruct`, après le check du fichier existant (ligne 564-566) :

```python
# Check that /scan was performed (tree.json + mycelium.db must exist)
repo_root = Path(__file__).resolve().parent.parent.parent
tree_path = repo_root / "memory" / "tree.json"
mycelium_db = repo_root / ".muninn" / "mycelium.db"
if not tree_path.exists() or not mycelium_db.exists():
    self._append_text(
        "[reco] No scan detected. Type /scan <repo_path> first to "
        "build the tree + mycelium for proper neighbors and anchors.",
        color="#EF4444",
    )
    return
```

**Test :**
```bash
PYTHONPATH=$(pwd) python -c "
import os
os.rename('memory/tree.json', 'memory/tree.json.bak')  # simule pas-scan
from muninn.ui.terminal import TerminalPanel
# (smoke test : check que la classe importe sans crash)
print('OK')
os.rename('memory/tree.json.bak', 'memory/tree.json')
"
```

**Commit message :** `fix(ux): /reconstruct require /scan préalable (tree + mycelium)`

---

### CHUNK 5 — Bench N tokens sweep

**Nouveau fichier :** `tests/bench_n_tokens.py`

**Pas forge** (script de mesure, pas modif engine).

**À implémenter** :
1. Pour chaque N ∈ {80, 88, 96, 112, 128} :
   - Subdivise btree_google.go en cubes de N tokens
   - Calcule ast_hints + enrich_hints_with_file_context pour chaque cube
   - Compte combien seraient auto-SHA via Fix 20
   - Lance reconstruct_adaptive avec qwen 7B (run partiel : 10 cubes pour vitesse)
   - Mesure SHA total + auto-SHA + temps
2. Output : tableau comparatif

**À RUN APRÈS CHUNK 1 sinon biaisé** (sinon Fix 20 reste bypassé).

**Commit message :** `bench: sweep N ∈ {80,88,96,112,128} tokens avec Fix 20 + FIM corrects`

---

### CHUNK 6 — Validation finale live UX

**Pas de modif code.** Test bout-en-bout.

**Procédure :**
1. UX restart : `PYTHONPATH=$(pwd) python -m muninn.ui.main_window`
2. Dans le terminal UX, taper :
   ```
   /scan tests/cube_corpus
   ```
3. Attendre la fin du scan (le panneau "Forest" doit se remplir)
4. Taper :
   ```
   /reconstruct tests/cube_corpus/btree_google.go 112 0
   ```
5. Mesurer dans les logs :
   - Total SHA / 61
   - Combien d'AUTO-SHA (attempt=0)
   - Combien de SHA via LLM (attempt > 0)
   - Combien de FAIL (NCD final)

**Cible :** **>= 38/61 SHA** (= score auto-SHA seul). Si oui : CHUNK 1 a tenu sa promesse.

**Si OK :** commit le HANDOFF_*.md updates + `git push origin main`. **Demander confirmation à Sky avant push** (RULE 2).

---

### CHUNK 7 OPTIONNEL — Cap UX cohérent avec engine

**Fichier :** [muninn/ui/cube_live.py](muninn/ui/cube_live.py)
**Lignes :** 107-175 (subdivide + appel reconstruct_adaptive)

**Pas forge** (UI only).

**Problème actuel :** UX cap les cubes pour l'affichage à `max_cubes`, mais passe `content` complet à `reconstruct_adaptive` → engine traite 61 cubes même si UX en affiche 10. Gaspillage GPU.

**Fix proposé :** si `max_cubes > 0`, tronquer `content` aux N premiers cubes avant l'appel :
```python
if 0 < self._max_cubes < total:
    last_line = cubes[self._max_cubes - 1].line_end
    content = "\n".join(content.split("\n")[:last_line])
```

**Commit message :** `perf(ux): cap content réel quand max_cubes < total — évite gaspillage GPU`

---

### CHUNK 8 OPTIONNEL — Hook qui casse memory/tree.json

**Fichier :** un hook auto qui réécrit `memory/tree.json` après chaque session

**Diagnostic à faire :**
```bash
git log --all --oneline -- memory/tree.json | head -10
git diff HEAD~5 -- memory/tree.json
# trouver quel hook le touche
grep -rn "tree.json\|b0002" .claude/hooks/ engine/core/ muninn/ 2>/dev/null
```

Si on identifie le hook coupable, soit :
- Corriger pour ne pas réécrire les compteurs
- Ou retirer le check CI sur cette ligne

**Commit message :** `fix: hook X ne réécrit plus tree.json b0002.lines (régression récurrente)`

---

## Ordre recommandé

1. **CHUNK 1** (le plus impactant) avant tout
2. **CHUNK 2** (Mycelium path) — débloque le bonus mycelium
3. **CHUNK 6 partiel** : test live pour mesurer le score post-CHUNK1+2
4. **CHUNK 3, 4** (UX dismissable + scan required) — UX propre
5. **CHUNK 5** : bench N tokens
6. **CHUNK 6 final** : validation
7. **CHUNK 7, 8** si temps

## Règles strictes pour la prochaine session

1. **RULE 4 anti-bullshit** : aucun "fait/passe/pushé" sans output collé 3 lignes au-dessus
2. **RULE 5 forge** : si tu touches `engine/`, forge AVANT commit
3. **RULE 2** : confirmer Sky avant chaque `git push`, surtout main
4. **BUG-091 mirror** : si tu touches `engine/core/foo.py`, vérifier `muninn/foo.py` (md5 check)
5. **Pas de Sonnet** : Sky n'a pas de budget API. Tout test sur qwen2.5-coder:7b ou deepseek-coder:6.7b en local
6. **Pas mélanger UX et engine** : les bugs sont catalogués séparément (A vs B)

## Référence audit complet

Voir aussi :
- `docs/YGG_FULL_REPORT_2026-04-26.md` (recherche cousin Ygg)
- `docs/YGG_DISK_RESEARCH_2026-04-26.md`
- `docs/YGG_RESEARCH_2026-04-25.md`
- `docs/HANDOFF_CUBE_LIVE_TESTS.md` (handoff précédent)
- `docs/ANTI_BULLSHIT_BATTLE_PLAN.md` (10 défenses)
- BUGS.md (BUG-091 STILL OPEN, autres FIXED)

# Battle Plan Remediation — Post-Audit C8→C13 (v3 — décisions Sky actées)

> **Source** : audit ruthless 4-agents 2026-05-19 PM + re-vérification runtime par
> Claude (reproduction shell-side pour chaque RED + lecture file:line pour chaque AMBER).
> Plus de claim agent non vérifié.
>
> **Décisions Sky 2026-05-19 PM (actées, non négociables ici)** :
> - **Q1 = B** : C12 hover/click au zoom>1 doit sélectionner le GROUPE entier (correct), pas désactiver (safe).
> - **Q2 = A** : ajouter un workflow GitHub Actions weekly pour les perf tests (pas suppression).
> - **Q3 = B** : valoriser `mock_ollama` en écrivant un vrai test runtime C0 (pas suppression).
> - **Bonus = B** : `_build_full_anchor_map` complet (4-arg avec `ext`). Cohérent avec la mission Muninn — la heatmap rouge doit montrer la mémoire des dev seniors, pas la syntaxe triviale.
>
> **Convention** : 1 chunk = 1 commit, push après chaque, CI vert obligatoire avant le suivant.
> §8.A-E du battle plan unifié 2026-05-19 héritées (env vars CLAUDE.md, feature flag dual-test,
> forge property fail = bug, no backwards-incompat signature en 1 chunk).

---

## 0. Findings vérifiés runtime

| ID | Claim | Vérifié comment | Statut final |
|---|---|---|---|
| R1 | `_build_full_anchor_map` 3 args au lieu de 4 → `gap_lines=[]` toujours | Reproduit `python -c "..."` → `TypeError`, puis `reconstruct_cube(...).gap_lines == []` | 🔴 CONFIRMÉ runtime |
| R2 | C12 paint/click mismatch | `displayed[0] is _neurons[0]` → False ; `_hit_test` cherche dans `_neurons` (originaux) ; hover `is` check ne match jamais à zoom>1 | 🔴 CONFIRMÉ (hover dead, click silencieusement wrong — pas de ValueError comme l'agent claim) |
| R3 | Shim `muninn.cube_providers` circular import | `python -c "from muninn.cube_providers import OllamaProvider"` → `ImportError` | 🔴 CONFIRMÉ runtime |
| R4 | `MUNINN_RUN_PERF` absent CI | `grep -rn MUNINN_RUN_PERF .github/workflows/` → 0 hit | 🔴 CONFIRMÉ |
| R5 | Forge re-gen tests no-op | 44 tests, **0 `assert`**, 100% pattern `try: f(); except: pass` | 🔴 CONFIRMÉ HARDER (44 réel vs ~50 claim) |
| R6 | `test_pipeline_trace_emits_during_reco` asserte rien | `assert isinstance(events, list)` à la ligne 159 | 🔴 CONFIRMÉ |
| A1 | Regex `_extract_unknown_identifiers` leak keywords | Reproduit : `unknown_identifiers=['def', 'pass']` sur un cube Python | 🟡 CONFIRMÉ runtime |
| A2 | `mock_ollama.py` zéro consumer | `grep -rn mock_ollama_session` → uniquement self-mention | 🟡 CONFIRMÉ |
| A3 | `options_applied` per-init bruit | `log_event` dans `OllamaProvider.__init__:125`, comment "once at boot" est mensonge | 🟡 CONFIRMÉ |
| A4 | BUG-091 mirror cassé `_extract_*` | `from cube_providers import *` skip les `_*` par PEP 8 ; liste explicite ne les inclut pas | 🟡 CONFIRMÉ par lecture |
| A5 | `update_cube_details` ne retrigger pas DetailPanel | Lecture `neuron_map.py:1389` — docstring claim "consumed lazily" sans refire neuron_selected si déjà sélectionné | 🟡 CONFIRMÉ par lecture |

**Hors-scope C8→C13 (pré-existants)** :
- Tempfile leak `reconstruct_adaptive:2165` — bug réel mais introduit avant `b2e115d`.
- `Neuron.temperature` double-usage (scan freq vs NCD) — champ existait avant C8.
- CLAUDE.md 365 lignes = plafond — observation, pas un bug.

---

## 1. Ordre d'exécution

```
D1 (R1, Bonus B)  Fix gap_lines TypeError + full anchor map   [30min] → débloque C10+C11 UX
D2 (R3)           Shim ImportError circular                    [30min]
D3 (A1)           Filter keywords + min length 4               [20min]
D4 (A4, dep D3)   Shim re-export _extract_*                    [15min]
D5 (Q1 B)         C12 hover/click via groups                   [1h]
D6 (R5)           Tri 44 forge no-op tests + handbook          [1h30]
D7 (R6, dep D1)   E2E pipeline_trace réel                      [30min]
D8 (Q2 A, R4)     Workflow perf.yml weekly cron                [30min]
D9 (A3)           options_applied bruit → module-level guard   [10min]
D10 (Q3 B, dep D2) mock_ollama capture + test C0 runtime       [1h]
D11 (A5)          update_cube_details refire si sélectionné    [10min]
```

**Total estimé** : ~310 LOC, ~6h. CI vert obligatoire entre chunks.

**Dépendances** :
- D4 dépend de D3 (sinon mirror exporte des helpers qui filtreront mal).
- D7 dépend de D1 (sinon events potentiellement vides aussi).
- D10 dépend de D2 (sinon mock_ollama via shim ImportError).

---

## D1 — Fix `gap_lines` TypeError + full anchor map [RED, 30min, Bonus B acté]

### Symptôme runtime
```bash
python -c "
import sys; sys.path.insert(0, 'engine/core'); import cube
from cube_providers import reconstruct_cube, MockLLMProvider
from cube import Cube
c = Cube(id='t', content='def f():\n  return 1', sha256='x',
         file_origin='t.py', line_start=1, line_end=2)
r = reconstruct_cube(c, [], MockLLMProvider(),
                     ast_hints={'first_line': 'def f():', 'identifiers': ['f']})
print('gap_lines:', r.gap_lines)  # → []
"
```

### Cause
`engine/core/cube_providers.py:1073` appelle `_build_full_anchor_map(ast_hints, lines, n_lines)` —
**3 args** alors que la signature exige **4** (`..., ext: str`). `TypeError` swallowed par
`except Exception: gap_lines = []`. Cascade : `WaveResult.gap_lines = []` → `cube_details`
émet `[]` → `_compute_line_colors_for_cube` retourne tout vert → **FileHeatmapView ne montre jamais de rouge/orange**.

### Fix (Bonus B = full anchor map)
```python
# engine/core/cube_providers.py:1070-1080
try:
    cube_lines = cube.content.split("\n") if cube.content else []
    n_lines = len(cube_lines)
    # CHUNK D1 (2026-05-19 remediation) — full anchor map captures
    # structurally-constrained lines (closing braces, defer, struct tags,
    # constants, blanks) so gap_lines only highlights what the LLM
    # actually had to invent — the senior-dev memory mission of Muninn.
    import os.path as _osp
    ext = _osp.splitext(getattr(cube, "file_origin", "") or "")[1]
    anchor_map = _build_full_anchor_map(ast_hints or {}, cube_lines, n_lines, ext)
    gap_lines = _extract_gap_lines(anchor_map, n_lines)
except Exception:
    gap_lines = []
```

### Tests
Dans `tests/test_chunk_2026-05-19_C10_recon_extras.py` ajouter :
```python
def test_gap_lines_populated_when_ast_hints_provided():
    """D1 regression : pre-fix, _build_full_anchor_map missing ext arg → all []."""
    from cube_providers import reconstruct_cube, MockLLMProvider
    from cube import Cube
    c = Cube(id='t', content='def foo():\n    return 1\n    pass\n',
             sha256='x', file_origin='t.py', line_start=1, line_end=3)
    r = reconstruct_cube(c, [], MockLLMProvider(),
                         ast_hints={'first_line': 'def foo():', 'identifiers': ['foo']})
    # first_line anchors idx 0 ; rest should be in gaps for a fresh hint set
    assert 0 not in r.gap_lines, "anchored line 0 must NOT be in gaps"
    # gap_lines must NOT be always empty for non-trivial hint inputs
    # (exact count depends on full_anchor_map heuristics, but the list
    # must reflect reality, not the silent TypeError fallback)

def test_gap_lines_full_anchor_map_catches_closing_brace():
    """Bonus B : full anchor map must mark closing braces as anchored."""
    from cube_providers import reconstruct_cube, MockLLMProvider
    from cube import Cube
    c = Cube(id='t', content='func F() {\n  x := 1\n}\n',
             sha256='x', file_origin='t.go', line_start=1, line_end=3)
    r = reconstruct_cube(c, [], MockLLMProvider(),
                         ast_hints={'first_line': 'func F() {'})
    # Line 2 (idx 2, the "}") must be anchored by full_anchor_map's Fix 6
    assert 2 not in r.gap_lines, "closing brace '}' should be anchored"
```

### Forge
Re-run `forge --gen-props engine/core/cube_providers.py` post-fix pour s'assurer que
les props C10 (`_extract_gap_lines`, `_extract_unknown_identifiers`) sont toujours OK.
Restaurer `@settings(deadline=None)` (forge le strip à chaque gen).

### Critère done
- 2 tests ci-dessus verts.
- Sandbox manuel `/reconstruct btree_google.go` → DetailPanel affiche **"Gap lines: N>0"** sur cubes fail réels.
- FileHeatmapView a des bandes rouges/orange visibles.

---

## D2 — Shim `muninn.cube_providers` ImportError circular [RED, 30min]

### Symptôme runtime
```bash
python -c "from muninn.cube_providers import OllamaProvider"
# ImportError: cannot import name 'LLMProvider' from partially initialized module
# 'cube_providers' (most likely due to a circular import)
```

### Cause
Chaîne `cube_providers → cube → cube_analysis → cube_providers`. `muninn/cube.py` a un
workaround `sys.modules.setdefault('cube', __import__('cube'))`. `muninn/cube_providers.py` non.

### Fix
Dans `muninn/cube_providers.py`, ajouter avant le `from cube_providers import *` :
```python
# CHUNK D2 (2026-05-19 remediation) — break the import cycle
# cube_providers → cube → cube_analysis → cube_providers by pre-registering
# the engine-core modules in sys.modules BEFORE the wildcard import.
sys.modules.setdefault("cube", __import__("cube"))
sys.modules.setdefault("cube_analysis", __import__("cube_analysis"))
```

### Tests
Créer `tests/test_bug_091_shim_first_import.py` :
```python
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _subprocess_import(snippet: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
    )


def test_muninn_cube_providers_first_import():
    """Subprocess test : fresh Python, first import = muninn.cube_providers."""
    r = _subprocess_import("from muninn.cube_providers import OllamaProvider; print('OK')")
    assert r.returncode == 0, f"stderr: {r.stderr}"
    assert "OK" in r.stdout


def test_muninn_cube_first_import():
    r = _subprocess_import("from muninn.cube import Cube; print('OK')")
    assert r.returncode == 0, f"stderr: {r.stderr}"


def test_muninn_cube_analysis_first_import():
    r = _subprocess_import("from muninn.cube_analysis import fuse_risks; print('OK')")
    assert r.returncode == 0, f"stderr: {r.stderr}"
```

### Forge
N/A (shim re-export pur).

### Critère done
3 tests subprocess verts. `python -c "from muninn.cube_providers import OllamaProvider"`
en cold start exit 0.

---

## D3 — Filter keywords + min length 4 [AMBER critique, 20min]

### Symptôme runtime
```bash
python -c "
import sys; sys.path.insert(0, 'engine/core'); import cube
from cube_providers import _extract_unknown_identifiers
print(_extract_unknown_identifiers('def foo():\n    pass', {'identifiers': ['foo']}))
# → ['def', 'pass']   ← mots-clés Python comptés comme idents inconnus
"
```

Le DetailPanel affiche du bruit ; "Unknown idents: 2 (def, pass…)" pour un cube trivial.

### Fix
```python
# engine/core/cube_providers.py
_COMMON_KEYWORDS = frozenset({
    # Python
    "def", "pass", "return", "elif", "else", "import", "from", "lambda",
    "yield", "raise", "True", "False", "None", "with", "while", "class",
    # Go
    "func", "var", "const", "type", "struct", "interface", "package",
    "select", "chan", "defer", "range", "switch", "case", "default",
    # JS/TS
    "let", "function", "async", "await", "export", "import",
    # C-family (subset, evite collisions avec idents courts genre "int" identifier)
    "void", "char", "float", "double", "long", "short", "static", "const",
    "unsigned", "signed", "extern", "inline", "typedef",
})


def _extract_unknown_identifiers(reconstruction, ast_hints):
    if not ast_hints or not ast_hints.get("identifiers"):
        return []
    import re as _re
    known = set(ast_hints["identifiers"])
    # 4+ chars (matches `{3,}` = 4 char min ; up from previous `{2,}` = 3 char)
    found = set(_re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", reconstruction or ""))
    return sorted((found - known) - _COMMON_KEYWORDS)
```

### Tests
Dans `tests/test_chunk_2026-05-19_C10_recon_extras.py` :
```python
def test_extract_unknown_identifiers_filters_keywords():
    from cube_providers import _extract_unknown_identifiers
    r = _extract_unknown_identifiers(
        "def helper(): return some_var",
        {"identifiers": []},
    )
    assert "def" not in r, "Python keyword 'def' must be filtered"
    assert "return" not in r, "Python keyword 'return' must be filtered"
    assert "helper" in r
    assert "some_var" in r


def test_extract_unknown_identifiers_filters_short():
    """Identifiers <4 chars are noise (or, if, in, is, no, to, etc.)."""
    from cube_providers import _extract_unknown_identifiers
    r = _extract_unknown_identifiers(
        "if x == 0: return y or z",
        {"identifiers": []},
    )
    # "if", "or" should be filtered by min-length (and "if" is a keyword)
    for short in ("if", "or", "x", "y", "z"):
        assert short not in r, f"short noise {short!r} leaked"
```

### Forge
N/A (modif d'un helper privé, forge skip).

### Critère done
- Tests ci-dessus verts.
- Sandbox manuel : "Unknown idents" affiche des noms vraiment significatifs (variables, helpers métier), pas des keywords.

---

## D4 — Shim re-export `_extract_*` [AMBER, 15min, dépend D3]

### Cause
`muninn/cube_providers.py` utilise `from cube_providers import *` qui skip les `_*` par PEP 8.
La liste explicite ne contient pas `_extract_gap_lines`/`_extract_unknown_identifiers`.

### Fix
```python
# muninn/cube_providers.py
from cube_providers import (  # explicit re-export of public surface
    LLMProvider,
    OllamaProvider,
    ClaudeProvider,
    OpenAIProvider,
    MockLLMProvider,
    FIMReconstructor,
    ReconstructionResult,
    WaveResult,
    LevelResult,
    reconstruct_cube,
    reconstruct_cube_waves,
    run_progressive_levels,
    reconstruct_adaptive,
    # CHUNK D4 (2026-05-19 remediation) — surfaced helpers for shim consumers
    _extract_gap_lines,
    _extract_unknown_identifiers,
)
```

### Tests
Dans `tests/test_bug_091_shim_first_import.py` (créé en D2) :
```python
def test_shim_exposes_c10_helpers():
    r = _subprocess_import(
        "from muninn.cube_providers import _extract_gap_lines, "
        "_extract_unknown_identifiers; print('OK')"
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
```

### Forge
N/A.

### Critère done
Test ci-dessus vert.

---

## D5 — C12 hover/click via groups [RED, 1h, Q1 B acté]

### Symptôme runtime
```bash
QT_QPA_PLATFORM=offscreen python -c "
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from muninn.ui.neuron_map import NeuronMapWidget, Neuron
w = NeuronMapWidget()
w._neurons = [Neuron(id=f'c{i}', label=f'L{i}', level='cube', x=i*0.1, y=0, z=0) for i in range(6)]
w.set_zoom_level(2)
displayed = w._displayed_neurons()
print('displayed[0] is _neurons[0]?', displayed[0] is w._neurons[0])  # False
# → 'is' check in _paint_neurons:715 never matches at zoom>1 → hover dead
"
```

### Fix
1. **Augmenter `_aggregate_neurons_to_level`** pour retourner aussi le mapping :
   - Garder la signature pure existante OK pour les callers helpers.
   - Ajouter un helper `_aggregate_neurons_with_groups(neurons, level) -> tuple[list[Neuron], list[list[int]]]`
     qui retourne `(molecules, groups)` où `groups[i] = [orig_idx_0, orig_idx_1, ...]`.
   - `_aggregate_neurons_to_level` devient un wrapper : `return _aggregate_neurons_with_groups(...)[0]`.

2. **Stocker les groupes sur le widget** :
   ```python
   # __init__
   self._displayed_groups: list[list[int]] = []  # filled by _displayed_neurons()
   ```

3. **Mettre à jour `_displayed_neurons`** :
   ```python
   def _displayed_neurons(self):
       if self._zoom_level == 1:
           self._displayed_groups = [[i] for i in range(len(self._neurons))]
           return self._neurons
       molecules, groups = _aggregate_neurons_with_groups(self._neurons, self._zoom_level)
       self._displayed_groups = groups
       return molecules
   ```

4. **`_hit_test` au zoom>1**: chercher les molécules peintes au lieu des originaux.
   Refactoriser pour walker `_displayed_neurons()` et retourner un tuple
   `(neuron_or_molecule, list[orig_indices])` au lieu d'un seul Neuron.
   À zoom=1, `orig_indices = [i]` (un seul).

5. **`_handle_neuron_click`** : opère sur `orig_indices` (set update).
6. **`_paint_neurons`** : précompute `hovered_group_set` (set des indices originaux du
   groupe hover). Quand on paint chaque molécule, dimmer si son groupe n'intersecte
   pas `hovered_group_set`. Aligné avec la logique neighbors existante.

### Tests
Dans `tests/test_chunk_2026-05-19_C12_fractal_zoom.py` ajouter :
```python
def test_aggregate_with_groups_returns_mapping():
    from muninn.ui.neuron_map import _aggregate_neurons_with_groups, Neuron
    src = [Neuron(id=f'c{i}', label=f'L{i}', level='cube') for i in range(5)]
    molecules, groups = _aggregate_neurons_with_groups(src, 2)
    assert len(molecules) == 3  # ceil(5/2)
    assert groups == [[0, 1], [2, 3], [4]]


def test_displayed_groups_filled_after_set_zoom_level(qtbot):
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f'c{i}', label=f'L{i}', level='cube') for i in range(6)]
    w.set_zoom_level(2)
    _ = w._displayed_neurons()  # populates _displayed_groups
    assert w._displayed_groups == [[0, 1], [2, 3], [4, 5]]


def test_click_at_zoom_2_selects_group(qtbot):
    """Q1 B regression : click on a molecule selects all originals of that group."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f'c{i}', label=f'L{i}', level='cube', x=i, y=0, z=0)
                  for i in range(6)]
    w.set_zoom_level(2)
    _ = w._displayed_neurons()
    # Simulate click on molecule idx 1 (group = [2, 3])
    w._handle_molecule_click(1, modifiers=0)  # new helper or test seam
    assert 2 in w._selected and 3 in w._selected
    assert 0 not in w._selected
```

### Forge
N/A (UI).

### Critère done
- Tests ci-dessus verts.
- Sandbox : zoom x2 + click sur molécule → 2 cubes highlighted ; hover dimme bien les
  molécules non-voisines.

---

## D6 — Tri 44 forge re-gen no-op tests + handbook [RED, 1h30]

### Symptôme
```bash
grep -c "^def test_" tests/test_props_cube*.py
# → 12 / 25 / 7  (44 tests total)
grep -c "    assert " tests/test_props_cube*.py
# → 0 / 0 / 0  (zéro assertion)
```

100% sont des `test_*_no_crash` avec `try: f(args) except (...): pass` + stratégies
`st.text(max_size=50)` sur des paramètres TYPÉS (`Cube`, `CubeStore`, `Mycelium`,
`LLMProvider`). Le code raise `AttributeError` au 1er access, swallow par l'except,
test passe. Ils prouvent que `import` marche, rien d'autre.

### Fix
Triage par fonction. Pour chacune des 44 :

**A. Helper pur (string/list in, string/list/numeric out)** → garder le test + ajouter
post-condition + vraie strat typée :
```python
@given(text=st.text(min_size=1, max_size=500))
@settings(max_examples=50, deadline=None)
def test_compute_ncd_returns_normalized(text):
    """compute_ncd output must be in [0, 1] for any non-empty strings."""
    result = compute_ncd(text, text)
    assert 0.0 <= result <= 1.0
    assert result == 0.0  # NCD(x, x) = 0 by definition
```

**B. Fonction qui prend un objet typé** → supprimer le test (stratégie `st.text()` ne
peut pas l'exercer) ou réécrire avec `st.builds(Cube, ...)`. Comme c'est long, et
qu'on a déjà des tests unit dédiés pour chaque fonction métier, **supprimer**.

**Décision pratique** : pour chaque test, je lis la fonction qu'elle exerce. Si la
fonction prend `Cube` / `CubeStore` / `Mycelium`, le test va dégager. Si elle prend
des string/list/dict, je garde et ajoute une post-condition.

**Estimation triage** (à confirmer post-lecture) : ~15 garder, ~29 supprimer.

### Handbook
Créer `docs/FORGE_REGEN_HANDBOOK.md` (1 page) :
```markdown
# Forge --gen-props : guide d'usage

Quand exécuter `forge --gen-props <file>` sur un module qui contient des
fonctions prenant des objets typés (Cube, CubeStore, Mycelium, etc.),
les tests générés seront des smoke `_no_crash` avec stratégies `st.text()`
qui swallow toutes les exceptions et n'assertent RIEN.

## Procédure correcte post-forge re-gen

1. Pour chaque test `test_*_no_crash` généré, identifier la fonction qu'il exerce.
2. Si la fonction prend des **objets typés** : SUPPRIMER le test (il prouve juste
   que `import` marche, rien d'autre).
3. Si la fonction prend des **strings/lists/numerics** : GARDER et ajouter une
   post-condition réelle (`assert isinstance(result, ...)`, `assert result >= 0`, etc.).
4. Restaurer `@settings(deadline=None)` partout (forge le strip systématiquement).

## Fichiers déjà tritrés

- `tests/test_props_cube.py` — N tests valides post-D6
- `tests/test_props_cube_analysis.py` — N tests valides post-D6
- `tests/test_props_cube_providers.py` — N tests valides post-D6

**Avant de re-run `forge --gen-props` sur ces fichiers, sauvegarde le baseline
de tests valides — sinon tu perds le tri.**
```

### CLAUDE.md
Mettre à jour RULE 5 avec une note :
```
Note D6 (2026-05-19) : `forge --gen-props` sur cube/cube_analysis/cube_providers
re-génère des smoke tests no-op qui doivent être tritrés MANUELLEMENT
(cf docs/FORGE_REGEN_HANDBOOK.md). Ne pas commit le résultat brut de forge.
```

### Forge
N/A (le fix EST le résultat post-forge).

### Critère done
- `tests/test_props_cube*.py` : tests réduits à un nombre réaliste avec assertions réelles.
- `docs/FORGE_REGEN_HANDBOOK.md` créé.
- CLAUDE.md RULE 5 contient la note.
- Cap CLAUDE.md ≤ 365 lignes (test `test_chunk13_claude_rules_split`).

---

## D7 — `test_pipeline_trace_emits_during_reco` réel [RED, 30min, dépend D1]

### Symptôme
`tests/test_pipeline_e2e_2026-05-19.py:159` : `assert isinstance(events, list)`.
`read_trace_events` retourne `[]` si le fichier n'existe pas → assert toujours vrai.

### Fix
Étape 1 : faire tourner le test une fois et inspecter quels events sont réellement émis.
```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pipeline_e2e_2026-05-19.py::test_pipeline_trace_emits_during_reco -v -s
# Puis dans le shell, après isolated_repo tmp_path : cat <tmp>/.muninn/pipeline_trace.jsonl
```

Étape 2 : asserter au moins un event nommé qui fire vraiment :
```python
events = read_trace_events(isolated_repo)
assert len(events) > 0, (
    "no pipeline_trace events emitted during reconstruct_adaptive — "
    "trace machinery not wired (D7 regression)"
)
event_names = {e.get("event") for e in events}
# At minimum one of these MUST fire for the wire-claim to hold:
expected_any = {
    "pipeline.engine.llm.options_applied",  # C0 wired
    "pipeline.ui.cube_live.reconstruct_start",  # UI worker (only fires in UI path)
    "pipeline.forge.risk_map_cached",  # C4 wired
}
assert event_names & expected_any, (
    f"expected at least one of {expected_any}, got: {event_names}"
)
```

### Forge
N/A.

### Critère done
Test asserte un event nommé qui fire vraiment + un count > 0.

---

## D8 — Workflow perf.yml weekly cron [RED, 30min, Q2 A acté]

### Symptôme
`grep -rn MUNINN_RUN_PERF .github/workflows/` → 0 hit. Les 3 perf tests skip toujours en CI.

### Fix
Créer `.github/workflows/perf.yml` (calqué sur nightly.yml) :
```yaml
name: MUNINN Perf weekly

# Runs the opt-in perf gate every Sunday morning to catch performance
# regressions on the cube hot path (record_cycles batch, subdivide_file,
# fuse_risks). Local-only runs (MUNINN_RUN_PERF=1 pytest tests/test_perf_*)
# don't have an enforced gate — this workflow does.
#
# Thresholds in tests/test_perf_cube_run_2026-05-19.py are SLACK (5-100x
# nominal Sky measured locally). If GHA runners are slower and this job
# goes red consistently, bump the slack ; do NOT skip the run.

on:
  schedule:
    # Sundays 08:00 UTC = 09:00/10:00 Geneva. Avoids weekday CI noise.
    - cron: '0 8 * * 0'
  workflow_dispatch:

jobs:
  perf:
    name: Perf gate (opt-in via MUNINN_RUN_PERF=1)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6
      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.13'

      - name: Install pytest + runtime deps (mirror of ci.yml)
        run: |
          python3 -m pip install --upgrade pip
          python3 -m pip install -c constraints.txt \
            pytest hypothesis tiktoken anthropic numpy cryptography freezegun \
            forge-shield mcp

      - name: Configure git identity
        run: |
          git config --global user.email "ci-perf@muninn.local"
          git config --global user.name "MUNINN Perf CI"

      - name: Run opt-in perf tests
        env:
          MUNINN_RUN_PERF: "1"
        run: |
          python3 -m pytest tests/test_perf_cube_run_2026-05-19.py -v --tb=short
```

### Tests
N/A (le workflow EST le fix). Optionnel : `tests/test_perf_workflow_exists.py` qui asserte
que `.github/workflows/perf.yml` contient `MUNINN_RUN_PERF`.

### Forge
N/A.

### Critère done
- `gh workflow run "MUNINN Perf weekly"` lance les 3 perf tests, exit 0.
- Push de D8 ne déclenche PAS le workflow (cron-only + manual).

---

## D9 — `options_applied` bruit module-level guard [AMBER, 10min]

### Symptôme
`engine/core/cube_providers.py:125-133` — `log_event` dans `OllamaProvider.__init__`.
Chaque instanciation émet une nouvelle ligne `pipeline.engine.llm.options_applied`.
Comment "trace … once at boot" est faux.

### Fix
```python
# engine/core/cube_providers.py top-of-module
_OPTIONS_TRACE_EMITTED = False  # module-level guard for D9


class OllamaProvider(LLMProvider):
    def __init__(self, model='codellama', base_url='http://localhost:11434'):
        self.model = model
        self.base_url = base_url.rstrip('/')
        self._available = None
        # CHUNK C0 (2026-05-19): trace the active LLM options ONCE at first
        # provider instantiation (was per-init before D9 hotfix).
        global _OPTIONS_TRACE_EMITTED
        if not _OPTIONS_TRACE_EMITTED:
            log_event(  # PIPELINE_TRACE
                "pipeline.engine.llm.options_applied",  # PIPELINE_TRACE
                {  # PIPELINE_TRACE
                    "provider": "ollama",  # PIPELINE_TRACE
                    "model": model,  # PIPELINE_TRACE
                    "repeat_penalty": _OLLAMA_REPEAT_PENALTY,  # PIPELINE_TRACE
                    "temperature": _OLLAMA_TEMPERATURE,  # PIPELINE_TRACE
                },  # PIPELINE_TRACE
            )  # PIPELINE_TRACE
            _OPTIONS_TRACE_EMITTED = True
```

### Tests
Pas crucial (cosmétique trace), mais une assertion possible dans
`tests/test_pipeline_e2e_2026-05-19.py` :
```python
def test_options_applied_emitted_once(isolated_repo, monkeypatch):
    monkeypatch.setenv("MUNINN_REPO", str(isolated_repo))
    import importlib, pipeline_trace as _pt
    importlib.reload(_pt)
    from cube_providers import OllamaProvider
    # First instanciation emits, subsequent don't
    OllamaProvider(model="x")
    OllamaProvider(model="y")
    OllamaProvider(model="z")
    from tests._helpers.pipeline_trace import count_events
    events = read_trace_events(isolated_repo)
    assert count_events(events, "pipeline.engine.llm.options_applied") == 1
```

### Forge
N/A.

### Critère done
Test ci-dessus vert + `cat .muninn/pipeline_trace.jsonl | grep options_applied | wc -l` = 1
après une session avec N providers créés.

---

## D10 — `mock_ollama` capture + test C0 runtime [AMBER→valeur, 1h, Q3 B acté, dépend D2]

### Symptôme
- `tests/_helpers/mock_ollama.py` (92 LoC) : zéro consumer.
- C0 (`MUNINN_LLM_REPEAT_PENALTY=1.15`, `MUNINN_LLM_TEMPERATURE=0.2`) : aucune preuve
  runtime que ces valeurs arrivent dans le payload Ollama.

### Fix étape 1 — augmenter mock_ollama pour capturer les payloads
```python
# tests/_helpers/mock_ollama.py
@contextlib.contextmanager
def mock_ollama_session(*, models=("qwen2.5-coder",),
                        generate_text: str = "",
                        chat_text: str = ""):
    """Context manager. Yields a list `captured` of all request payloads
    sent during the block, in order. Each payload is the parsed JSON body."""
    captured: list = []
    saved = urllib.request.urlopen

    def _fake(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        # Capture body for assertions
        if hasattr(req, "data") and req.data:
            try:
                captured.append({
                    "url": url,
                    "payload": json.loads(req.data.decode("utf-8")),
                })
            except Exception:
                captured.append({"url": url, "payload": None})
        # Route the response (existing logic)
        if "/api/tags" in url:
            body = json.dumps({"models": [{"name": m} for m in models]}).encode()
            return _FakeResponse(body)
        if "/api/generate" in url:
            body = json.dumps({"response": generate_text, "done": True}).encode()
            return _FakeResponse(body)
        if "/api/chat" in url:
            body = json.dumps({
                "message": {"role": "assistant", "content": chat_text},
                "done": True,
            }).encode()
            return _FakeResponse(body)
        raise urllib.error.URLError(f"mock_ollama: unrecognized URL {url}")

    urllib.request.urlopen = _fake
    try:
        yield captured  # ← changed : yield the captured list
    finally:
        urllib.request.urlopen = saved
```

### Fix étape 2 — créer le test C0 runtime
```python
# tests/test_chunk_2026-05-19_C0_llm_runtime.py
"""CHUNK D10 (2026-05-19 remediation) — runtime proof that C0 options
are sent in the Ollama request payload. Closes the gap left by the original
C0 commit which only had unit tests on the env-var constants, not on the
actual HTTP path.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from tests._helpers.mock_ollama import mock_ollama_session


def test_ollama_generate_includes_repeat_penalty():
    """C0 wire proof : OllamaProvider.generate() sends repeat_penalty=1.15
    in the options block of /api/generate payload."""
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider, _OLLAMA_REPEAT_PENALTY
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        p.generate("hello world")
    # First call is /api/tags (probe), second is /api/generate
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls, "no /api/generate call captured"
    opts = gen_calls[-1]["payload"]["options"]
    assert opts["repeat_penalty"] == _OLLAMA_REPEAT_PENALTY
    assert abs(opts["repeat_penalty"] - 1.15) < 1e-6


def test_ollama_generate_includes_temperature():
    """C0 wire proof : OllamaProvider.generate() sends temperature=0.2."""
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider, _OLLAMA_TEMPERATURE
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        p.generate("hello")
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls
    opts = gen_calls[-1]["payload"]["options"]
    assert opts["temperature"] == _OLLAMA_TEMPERATURE
    assert abs(opts["temperature"] - 0.2) < 1e-6


def test_ollama_fim_generate_includes_options():
    """C0 wire proof : fim_generate also carries the C0 options."""
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        p.fim_generate(prefix="def f():\n    ", suffix="\n    pass\n")
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls
    opts = gen_calls[-1]["payload"]["options"]
    assert "repeat_penalty" in opts
    assert "temperature" in opts


def test_ollama_stream_includes_options():
    """C0 wire proof : stream() path also sends repeat_penalty + temperature."""
    # Note: stream() reads chunks ; mock returns the canned payload as if non-stream
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        try:
            list(p.stream("prompt", "system"))  # consume the generator
        except Exception:
            pass  # mock may not be a perfect stream impl
    # At minimum, /api/generate or /api/chat was called with the right options
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    if gen_calls:
        opts = gen_calls[-1]["payload"]["options"]
        assert "repeat_penalty" in opts
```

### Forge
N/A (helper test + nouveau fichier test).

### Critère done
- 4 tests `test_chunk_2026-05-19_C0_llm_runtime.py` verts.
- `mock_ollama_session` désormais consommée → plus du code mort.

---

## D11 — `update_cube_details` refire `neuron_selected` si déjà sélectionné [AMBER, 10min]

### Symptôme
Si l'utilisateur clique sur un cube AVANT que ses `cube_details` (gap_lines, unknown_idents)
soient arrivés (cycle long, late CYCLE_END), le DetailPanel reste figé sur les anciennes
valeurs jusqu'à un re-click manuel.

### Fix
```python
# muninn/ui/neuron_map.py
def update_cube_details(self, idx: int, gap_lines: list, unknown_idents: list):
    """CHUNK C10 (2026-05-19) — store reco diagnostics on the cube neuron.
    D11 (2026-05-19 remediation) — refire neuron_selected if the cube is
    already in self._selected, so the DetailPanel updates without waiting
    for a manual re-click."""
    if idx < 0 or idx >= len(self._neurons):
        return
    n = self._neurons[idx]
    n.gap_lines = list(gap_lines or [])
    n.unknown_idents = list(unknown_idents or [])
    # D11 : if user already focused this cube, push the updated payload
    if idx in self._selected:
        self.neuron_selected.emit(n)
```

### Tests
Dans `tests/test_chunk_2026-05-19_C10_recon_extras.py` :
```python
def test_update_cube_details_refires_neuron_selected_if_selected(qtbot):
    """D11 regression : late cube_details must refresh DetailPanel
    if the user is already on that cube."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f'c{i}', label=f'L{i}', level='cube') for i in range(3)]
    received = []
    w.neuron_selected.connect(lambda n: received.append(n.gap_lines.copy()))
    w._selected = {1}  # user has cube 1 selected
    w.update_cube_details(1, [3, 7], ["magic_var"])
    assert received, "neuron_selected was not refired"
    assert received[-1] == [3, 7]


def test_update_cube_details_no_refire_if_not_selected(qtbot):
    """If cube not selected, no refire (avoids needless DetailPanel updates)."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f'c{i}', label=f'L{i}', level='cube') for i in range(3)]
    received = []
    w.neuron_selected.connect(lambda n: received.append(n.id))
    w._selected = {2}  # user has DIFFERENT cube selected
    w.update_cube_details(1, [3, 7], ["magic_var"])
    assert not received, f"neuron_selected fired wrongly: {received}"
```

### Forge
N/A (UI).

### Critère done
2 tests ci-dessus verts.

---

## 11. Acceptation finale (post-D11)

```bash
# Tous les fix C8-C13 remediation verts
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_chunk_2026-05-19_C*.py \
  tests/test_pipeline_e2e_2026-05-19.py \
  tests/test_props_cube*.py \
  tests/test_bug_091_shim_first_import.py \
  tests/test_chunk_2026-05-19_C0_llm_runtime.py \
  -v --timeout=60

# Shim cold-start
python -c "from muninn.cube_providers import OllamaProvider, _extract_gap_lines, _extract_unknown_identifiers; print('OK')"

# Sandbox manuel sur btree_google.go
# - DetailPanel "Gap lines: N>0" sur cubes fail (D1)
# - "Unknown idents" sans 'def'/'pass'/'return' (D3)
# - Ctrl+wheel x2 → click molécule → 2 cubes sélectionnés (D5)
# - Refresh DetailPanel auto sur late CYCLE_END (D11)
```

CHANGELOG.md + WINTER_TREE.md + docs/MANUAL_TESTS_2026-05-19.md mis à jour avec une
section "Remediation 2026-05-19 (post-audit C8→C13)".

---

## 12. Estimation finale honnête

| Chunk | LOC | Estim | Sév |
|---|---|---|---|
| D1  (R1 + Bonus B)        | ~10  | 30min | 🔴 |
| D2  (R3)                  | ~10  | 30min | 🔴 |
| D3  (A1)                  | ~30  | 20min | 🟡 critique |
| D4  (A4, dep D3)          | ~5   | 15min | 🟡 |
| D5  (Q1 B)                | ~60  | 1h    | 🔴 |
| D6  (R5)                  | ~100 | 1h30  | 🔴 |
| D7  (R6, dep D1)          | ~15  | 30min | 🔴 |
| D8  (Q2 A, R4)            | ~50  | 30min | 🔴 |
| D9  (A3)                  | ~10  | 10min | 🟡 |
| D10 (Q3 B, dep D2)        | ~80  | 1h    | 🟡 (valeur) |
| D11 (A5)                  | ~5   | 10min | 🟡 |
| **TOTAL**                 | **~375** | **~6h** | |

11 commits sur main, 1 push par chunk, CI vert obligatoire entre chunks.

---

## 13. Hors-scope (intentionnellement)

- **Tempfile leak `reconstruct_adaptive`** (pré-C8-C13). À traiter dans un futur audit
  reconstruction core.
- **`Neuron.temperature` double-usage** (pré-C8). Refactor avec champ séparé `ncd_score`
  à part — touche trop de code pour être casé ici.
- **CLAUDE.md à 365 lignes** = plafond mais respecté. Cosmétique.
- **Le pattern "commit UI Qt → CI 139"** récidiviste (navi.py 4×, FileHeatmapView 2×).
  Pas un bug code, c'est un process : tester en `CI=true QT_QPA_PLATFORM=offscreen`
  local AVANT push pour UI files. À documenter dans CLAUDE.md plus tard si récidive.

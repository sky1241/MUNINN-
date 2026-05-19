# Forge `--gen-props` : handbook anti-no-op (post-D6)

> Comment exécuter `forge --gen-props` sans réintroduire les 44 no-op
> tests que D6 (2026-05-19 remediation) a virés.

## Le piège

`forge --gen-props <file>` scanne les fonctions publiques d'un module
Python et génère pour chacune un test Hypothesis :

```python
@given(arg1=st.text(max_size=50), arg2=st.text(max_size=50))
@settings(max_examples=50)
def test_X_no_crash(arg1, arg2):
    """Smoke: X() does not crash on arbitrary input"""
    try:
        X(arg1, arg2)
    except (ValueError, TypeError, KeyError, IndexError,
            OSError, AttributeError, RuntimeError, SyntaxError,
            LookupError, ArithmeticError, AssertionError,
            SystemExit, Exception):
        pass  # Expected rejections are OK
```

**Le problème** : si `X` prend des objets typés (`Cube`, `CubeStore`,
`Mycelium`, etc.), passer un `str` produit `AttributeError` au 1er accès
→ swallowed par l'except → **le test passe sans rien tester**. Il prouve
que `import X` marche, rien d'autre.

L'audit C8-C13 2026-05-19 a trouvé 44 tests dans ce cas dans
`tests/test_props_cube*.py` (0 `assert` statement sur 44 tests).

## La procédure correcte post-`forge --gen-props`

### Sur les 3 modules cube/cube_analysis/cube_providers

Ces modules ont des fonctions à signature typée (`Cube`, `CubeStore`,
`Mycelium`). **Ne jamais commit le résultat brut de forge.**

```bash
# Étape 1 : exécuter forge
forge --gen-props engine/core/cube_providers.py

# Étape 2 : trier MANUELLEMENT chaque test généré.
#   Pour chaque test test_X_no_crash :
#     A. Lire la signature de X dans engine/core/cube_providers.py
#     B. Si X prend des objets typés (Cube, CubeStore, ...) :
#        SUPPRIMER le test (st.text() ne le teste pas).
#     C. Si X prend des strings/numerics/lists basiques :
#        - GARDER le test
#        - Ajouter une vraie post-condition (assert isinstance(...), ranges, etc.)
#        - Restaurer @settings(max_examples=50, deadline=None)
#          (forge strip deadline=None systématiquement).

# Étape 3 : vérifier que pytest a un compte réaliste, pas gonflé :
pytest tests/test_props_cube*.py -v
```

### Sur les autres modules engine/core

Si le module ne contient QUE des helpers purs (regex, normalize_text,
compute_metric, etc.), `forge --gen-props` produit des tests utiles.
Tu peux les commit. Mais :

1. **Toujours restaurer `@settings(deadline=None)`** (forge le strip).
2. **Toujours ajouter au moins une post-condition** par test (sinon
   c'est un import test déguisé).

## Tests gardés post-D6 (référence)

Après D6 (commit à venir post-D6 acceptance), les 3 fichiers props
contiennent :

- `tests/test_props_cube_providers.py` : 4 tests (compute_ncd bounded
  + symmetric, compute_ncd self=0, validate_reconstruction bool +
  reflexive).
- `tests/test_props_cube.py` : 4 tests (normalize_content returns str
  + idempotent, sha256_hash hex64 + deterministic).
- `tests/test_props_cube_analysis.py` : 0 test (toutes fonctions
  prennent objets typés — out of scope D6).

## Re-baseline le triage

Si un futur changement ajoute des fonctions purement-fonctionnelles
à un de ces 3 modules, **ajoute le test à la main** dans le fichier
correspondant. Ne fais pas confiance à `forge --gen-props` pour
distinguer "fonction pure utile" de "fonction objet-typé inutile".

CLAUDE.md RULE 5 dit : "Hypothesis falsifying example is your next test".
C'est vrai pour les `_no_crash` qui CRASHENT, pas pour les `_no_crash`
qui passent par swallow.

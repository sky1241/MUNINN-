# Phase B Brick 19 — Dead Code Audit (engine/core/)

Generated: 2026-04-11
Method: pure-Python AST scan, two-pass with cross-tree reference resolution

## Method

1. Walk every `.py` file under `engine/core/` via `ast.parse()`
2. Collect:
   - All top-level public function definitions
   - All function call sites (`Call` and `Attribute` nodes)
   - All `from X import Y` import targets (catches "imported by name")
   - All `__all__` exports
   - All class methods (which are not "dead" — called via instance)
3. A function is a "dead candidate" if:
   - It's defined at module top-level
   - Not in `__all__`
   - Not also a class method
   - Not in `ENTRY_POINTS` (`main`, `cli_run`)
   - Doesn't contain `hook`
   - Not imported anywhere else
   - Not called anywhere else

## First-pass result (in-tree references only): 17 candidates

After adding `from X import Y` resolution: **11 candidates**.

## Second-pass result (cross-tree check including tests/, tools/, muninn/)

**0 truly dead functions.** Every one of the 11 candidates is referenced
from at least one test file. They are well-tested public APIs that just
aren't called from inside `engine/core/` itself.

| Function | Where it's actually used |
|----------|--------------------------|
| `dedup.dedup_paragraphs` | `tests/test_brick2_dedup.py` (3 refs) |
| `dedup.similar` | 69 raw matches across the repo |
| `scanner.ast_analyzer.analyze_findings` | `tests/scanner/test_scan_b08.py` |
| `scanner.bible_validator.validate_against_code` | `tests/scanner/test_scan_b03.py` |
| `scanner.bible_validator.validate_against_code_with_mn` | `tests/scanner/test_scan_b03.py` |
| `scanner.bible_validator.validate_all` | `tests/scanner/test_scan_b03.py` |
| `scanner.llm_scanner.estimate_cost` | `tests/scanner/test_scan_b06.py` |
| `scanner.llm_scanner.scan_batch` | `tests/scanner/test_scan_b06.py` |
| `scanner.propagation.influence_minimization` | `tests/scanner/test_scan_b10.py` |
| `scanner.report.to_markdown` | `tests/scanner/test_integration_bugfixes.py`, `test_scan_b13.py` |
| `sync_backend.sync_metrics` | `tests/test_phase6_scale.py` |

## Conclusion

`engine/core/` has **no dead public functions** as of 2026-04-11. The
audit found 17 in-tree candidates which all reduced to 0 after cross-
referencing tests/, tools/, and muninn/.

The 17 in-tree candidates are public APIs that are exposed for external
callers (tests, future modules, tools). They form the documented API
surface of `engine/core/` even though they're not consumed by other
files inside `engine/core/` itself. This is a normal pattern for a
library — the public API exists for OUTSIDE callers, not for internal
consumption.

## Honest caveats

1. **Class methods are not audited**. The scan focuses on top-level
   functions. Methods inside classes (`Mycelium.spread_activation`,
   `MyceliumDB.compute_idf`, etc.) could in principle be dead but the
   scan doesn't catch them because Python class method dispatch is
   dynamic and impossible to resolve statically.

2. **Reflection / `getattr` calls are not detected**. If a function
   is called via `getattr(module, "name")()` or `globals()["name"]()`,
   the scan misses both the call site and the dead-ness.

3. **`muninn/` package not separately scanned**. It's a mirror of
   `engine/core/` (BUG-091) so the same audit applies — but the
   mirror could in principle drift if any function is added to one
   tree and not the other.

4. **Cross-repo callers not checked**. If Sky uses any of these
   functions from `c:/Users/ludov/.infernal_wheel/` or
   `c:/Users/ludov/3d-printer/`, they may be referenced there.

## Action items

- None. Audit clean.
- The pin test `tests/test_brick19_dead_code_audit.py` runs the same
  scan and asserts the count is exactly 11 (the documented set). If a
  NEW dead function is added, the test fails and forces a manual
  review (either delete it or add it to the documented set).

## How to reproduce

```bash
cd c:/Users/ludov/MUNINN-
python tests/test_brick19_dead_code_audit.py
# OR
python -m pytest tests/test_brick19_dead_code_audit.py -v
```

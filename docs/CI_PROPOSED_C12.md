# CHUNK C12 — Proposed CI extension (manual merge required)

The OAuth token used by the agent that opened this PR does not carry
the `workflow` GitHub scope, so `.github/workflows/ci.yml` cannot be
modified through the API push. Apply the diff below manually
(`git push` from a local checkout, or edit through the GitHub web UI).

## Diff to apply

Insert these lines at the top of `.github/workflows/ci.yml` (after `on:`
block) and add a new `pytest` job before `validate`:

```yaml
# CHUNK C12 (2026-05-08): explicit least-privilege permissions.
permissions:
  contents: read

jobs:
  pytest:
    runs-on: ubuntu-latest
    name: pytest (chunked, no slow / no real-API)

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies (pinned via constraints.txt)
        run: |
          python -m pip install --upgrade pip
          # CHUNK C1: use constraints.txt for reproducibility
          pip install -c constraints.txt -e '.[all]'
          pip install pytest pytest-xdist hypothesis

      - name: Run pytest suite (skip slow + real-API)
        env:
          MUNINN_RUN_REAL_API_TESTS: "0"
          MUNINN_RUN_REAL_LLM_TESTS: "0"
        run: |
          # CHUNK C12: standard pytest collection, skip slow markers
          pytest tests/ -m "not slow" --tb=short \
            --ignore=tests/test_l9_full.py \
            --ignore=tests/test_cube_real_api.py \
            --ignore=tests/test_cube_real_llm.py \
            --ignore=tests/test_ui_window.py \
            --ignore=tests/test_ui_tree_view.py \
            --ignore=tests/test_ui_terminal.py \
            --ignore=tests/test_ui_theme.py \
            --ignore=tests/test_ui_shortcuts.py \
            --ignore=tests/test_ui_keymap_hotkey.py \
            --ignore=tests/test_ui_neuron_view.py \
            --ignore=tests/test_ui_search_bar.py \
            --ignore=tests/test_ui_text_panel.py \
            --ignore=tests/test_ui_smoke.py \
            --ignore=tests/test_ui_theme_dark.py \
            --ignore=tests/test_ui_focus_chain.py \
            --ignore=tests/test_ui_repaint_locality.py \
            -q
```

The existing `validate` job remains unchanged.

## Why these choices

- `permissions: contents: read` — least privilege; default has been
  read since 2023 but explicit is auditable.
- `pytest tests/ -m "not slow"` — skips the API-cost markers
  (`test_cube_real_api`, `test_cube_real_llm`, `test_l9_full`).
- `MUNINN_RUN_REAL_API_TESTS=0` env — second guard for `pytest.mark.skipif`
  conditions in the real-API test files.
- `--ignore=tests/test_ui_*` — those need PyQt6 headless setup; out
  of scope for now (covered by `pytest.skip` in the files themselves
  but `--ignore` saves collection time).
- `pip install -c constraints.txt` — CHUNK C1 reproducibility.

## After merge

Once the workflow is in place, the test
`tests/test_chunk_c12_ci_workflow.py` (already shipped) will turn
green automatically. It currently `pytest.skip()`s with the message
"workflow change not merged yet (CHUNK C12 doc)".

# CHUNK D8 — Proposed CI step: forge --gen-props per engine/core module

Same constraint as C12: the agent token is missing the `workflow`
GitHub scope, so `.github/workflows/ci.yml` cannot be modified through
the API push. Apply the diff below manually.

## Why

CHUNK B9 / RULE 5 require running `python forge.py --gen-props
engine/core/X.py` after every engine module touch. Today this is
manual discipline. A CI step that calls forge on a matrix of modules
catches the case where someone adds an unprotected destructive
function and the property tests would crash.

## Diff to apply

Append a new job to `.github/workflows/ci.yml` (after the existing
`pytest` and `validate` jobs):

```yaml
  forge_smoke:
    runs-on: ubuntu-latest
    name: forge.py --gen-props (smoke per engine/core module)
    needs: [pytest]   # only run if pytest passed

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -c constraints.txt -e '.[all]'
          pip install pytest hypothesis

      - name: Generate property tests for every engine/core module
        run: |
          # Iterate over each public engine/core module and run forge.
          # Failure on any single module fails the job.
          for f in engine/core/muninn_tree.py \
                   engine/core/muninn_layers.py \
                   engine/core/muninn_feed.py \
                   engine/core/mycelium_db.py \
                   engine/core/mycelium.py \
                   engine/core/_secrets.py \
                   engine/core/cube.py \
                   engine/core/cube_providers.py \
                   engine/core/sync_backend.py \
                   engine/core/sync_tls.py \
                   engine/core/_hook_logger.py
          do
              echo "::group::forge --gen-props $f"
              python forge.py --gen-props "$f" || exit 1
              echo "::endgroup::"
          done

      - name: Run all generated property tests
        run: |
          pytest tests/test_props_*.py -q --tb=short
```

## Why this matters

Without this CI step, RULE 5 is enforced only by Sky's discipline.
With it, a regression in the destructive-function detector OR a new
unprotected destructive function silently lands on main, but the
forge_smoke job fails immediately so the PR can't merge.

## Test guard

`tests/test_chunk_d8_ci_forge.py` ships a skip-when-not-merged check
that flips to PASSED automatically once Sky pushes the workflow diff
above (with a token that has the `workflow` scope).

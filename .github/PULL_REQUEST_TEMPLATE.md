<!--
Thanks for the PR. Please fill in the sections below — checked items help us
merge faster. Delete sections that don't apply.
-->

## Summary

<!-- One or two sentences. Link to the issue this closes if any: "Closes #123". -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (existing behavior changes)
- [ ] Documentation only
- [ ] Test / CI infrastructure
- [ ] Refactor (no behavior change)

## Test plan

<!-- How did you verify this? Paste verbatim output of relevant pytest runs. -->

```
$ pytest tests/<file> -v
...
```

## Checklist

- [ ] `pytest tests/ -q` green locally
- [ ] `pre-commit run --all-files` green
- [ ] New/changed public API has type hints + docstring
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] No secrets, API keys, or `.env` files added
- [ ] If touching hooks: re-ran `muninn upgrade-hooks` and regenerated the
      `hooks.sha256sum` manifest

## Notes for reviewers

<!-- Anything tricky? Trade-offs you considered? Things explicitly out of scope? -->

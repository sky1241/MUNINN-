---
paths:
  - "**/.gitignore"
  - "**/.gitattributes"
  - "**/.git/**"
---

<!-- ================================================================ -->
<!-- Path-scoped rules: only loaded when Claude touches git config or -->
<!-- when running git operations. EXTENDS CLAUDE.md RULES 2 and 3.    -->
<!-- ================================================================ -->

# Git rules for the MUNINN- repo

Loaded by Claude Code when Claude touches `.gitignore`, `.gitattributes`,
or anything inside `.git/`. The PreToolUse hooks (chunk 12) provide
real-time enforcement on Bash commands; this file documents the WHY.

## RULE 2 extended — destructive git operations

CLAUDE.md RULE 2 says "confirm before destructive actions". For git:

**Always blocked by `pre_tool_use_bash_destructive.py` hook:**
- `git push --force` / `git push -f` / `git push --force-with-lease`
- `git reset --hard`
- `git branch -D <name>` (force delete)
- `git push --delete origin <branch>`
- `git commit --no-verify` (skips hooks)
- `git rebase -i` (interactive, not supported in headless mode)

**Workflow when Sky asks for one of these:**
1. The hook will exit 2 and Claude sees "Blocked destructive Bash command"
2. Stop. Read the hook's stderr message to Sky verbatim.
3. Ask Sky in chat: "This will <effect>. Confirm?"
4. Wait for Sky to type a clear confirmation
5. Only then re-attempt the command

**Never:**
- Try to bypass the hook by chaining commands (`git push --force; echo done`)
- Re-run the same blocked command without an explicit Sky confirmation
- Argue with the hook in stderr — it is the policy, not a suggestion

## Safe git defaults in this repo

- Always `git add` specific files by name. Avoid `git add -A` and `git add .`
  because they can pull in `.env`, credentials, large binaries.
- Commit messages use the format documented in this repo's CLAUDE.md
  conventions (HEREDOC for multi-line, `Co-Authored-By` line at the bottom).
- `git push origin main` is fine without confirmation (non-destructive).
- Sky uses `gh` CLI for GitHub PR/issue operations — prefer it over the
  web UI URL guessing.

## RULE 3 extended — secrets in git context

CLAUDE.md RULE 3 says never display secrets. For git:
- Never `cat .env` or any file in `.gitignore` that smells like creds.
- Never log a token to a commit message, even truncated.
- If you suspect a secret was committed, don't print it — refer Sky to
  `git rev-list --objects --all | grep <pattern>` or similar history-aware
  tools, and recommend `git filter-repo` for purge.
- The repo's `.gitignore` already covers `.env`, `*.key`, `credentials.*`,
  `.muninn/` (which contains the API call reports). Don't add files that
  override these patterns.

## Pre-commit safety checklist

Before running `git commit` for Sky, mentally verify:
- [ ] No secret in any staged file (you should have run `vault.py scrub`
      or equivalent if there was any risk)
- [ ] No `.env` or credential file accidentally staged
- [ ] No large binary file (>1MB) staged unless explicitly asked
- [ ] Commit message describes the WHY, not just the WHAT
- [ ] Co-Authored-By line present
- [ ] No `--no-verify`, no `--amend` of pushed commits, no force push

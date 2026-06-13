---
name: ship-changes
description: 'Ship the current working-tree changes as a pull request. Use when asked to commit and push, open a PR, ship/submit changes, create a feature branch and PR, or "make a PR for this". Creates a feature branch if on the default branch, crafts a Conventional Commits message, commits with DCO sign-off and GPG signing, pushes, and opens a GitHub PR with a Conventional Commits title.'
argument-hint: 'Optional: PR type/scope, target branch, or extra context for the commit/PR'
---

# Ship Changes as a Pull Request

Take the current changes from working tree to an open GitHub pull request:
branch → gates (`make check`) → commit (signed-off + GPG-signed) → push → PR.

## When to Use

- "Commit and push this", "open a PR", "ship these changes", "submit this"
- "Create a feature branch and PR for this"
- After finishing a unit of work that should become a pull request

## Prerequisites (verify, don't assume)

- `gh` CLI is installed and authenticated (`gh auth status`). If missing, fall
  back to pushing and printing the compare URL instead of `gh pr create`.
- Commit signing is configured. This repo policy requires **both**:
  - DCO sign-off via `git commit -s` (adds `Signed-off-by:`)
  - GPG/SSH signature (verified signatures). Check
    `git config --get commit.gpgsign`; if not `true`, pass `-S` explicitly.

## Procedure

### 1. Inspect the changes

```bash
git status
git --no-pager diff --stat HEAD
git branch --show-current
```

Read the actual diff (`git --no-pager diff HEAD`) enough to understand what
changed — you need this to pick the right Conventional Commit `type`/`scope` and
write an accurate message. Never invent changes you didn't verify.

### 2. Decide the branch

- **On the default branch** (`main`): create a feature branch. Derive the name
  from the change: `<type>/<short-kebab-summary>` (e.g. `fix/firewall-rule-sync`,
  `chore/bump-ruff`).

  ```bash
  git switch -c <branch-name>
  ```

- **Already on a feature branch**: check whether the branch name AND existing
  commits fit the new changes.
  - If they fit → stay and add a commit.
  - If the branch name is now misleading (e.g. named `fix/x` but the work became
    a feature) → ask the user whether to rename
    (`git branch -m <new-name>`) or create a new branch. Do not silently rename a
    pushed branch.

### 3. Stage

Stage the relevant changes. Prefer explicit paths over `git add -A` when only a
subset is intended. Confirm with the user if it's ambiguous which files belong
to this change.

```bash
git add <paths>   # or: git add -A
```

### 4. Run the quality gates

Before committing, mirror what CI enforces so failures are caught locally:

```bash
make check       # make lint (ruff + ty) then make test (pytest, coverage ≥ 80%)
```

Fix anything that fails before continuing — for lint, prefer
`uv run ruff check --fix` / `uv run ruff format`; for `ty` errors fix the
annotations rather than suppressing; for coverage below 80%, add tests under
`tests/`. (`pre-commit` also runs ruff/gitleaks/markdownlint on commit.)

### 5. Craft the commit message (Conventional Commits)

Format: `<type>[optional scope]: <description>`

- **type**: `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`,
  `build`, `ci`, `style`, `revert`.
- **scope**: optional, lowercase, matches the area touched (e.g. `firewall`,
  `cloudflare`, `config`, `deps`, `ci`, `docker`).
- **description**: imperative mood, lowercase start, no trailing period,
  ≤ ~72 chars on the subject line.
- Add a body (blank line then prose, wrapped ~72 cols) when the *why* isn't
  obvious from the subject. Add `Fixes #<n>` / `Closes #<n>` footers when an
  issue applies.

Examples: `fix(firewall): resolve rule sync issue`,
`chore(deps): bump ruff to v0.14.6`, `ci(docker): pin scout action version`.

### 6. Commit (sign-off + GPG-signed)

```bash
git commit -s -S -m "<type>(<scope>): <subject>" [-m "<body>"]
```

- `-s` adds the DCO `Signed-off-by:` line (required).
- `-S` GPG-signs the commit. If `commit.gpgsign` is already `true` you may omit
  `-S`, but passing it is harmless and explicit.
- After committing, verify: `git --no-pager log --show-signature -1` shows a
  `Signed-off-by:` line and a good signature.

### 7. Push

```bash
git push -u origin <branch-name>
```

If the branch was already pushed, a plain `git push` is enough (use
`--force-with-lease` only if you intentionally rewrote history and the user
agreed).

### 8. Open the pull request

Use a Conventional Commits **PR title** (same format as the commit subject).
Fill the repo's PR template, but keep it lean and honest:

- Write the prose sections (Description, Motivation, Changes Made) accurately.
- **Don't pre-tick the template's checkboxes.** Those are the *author's*
  self-certification, and GitHub already verifies the DCO sign-off, signature,
  and Conventional Commits title — so leave the boxes unchecked for the human to
  confirm rather than asserting them on their behalf.
- Report what you actually ran in prose under Testing (e.g. "`make check` —
  56 passed, 100% coverage") instead of ticking boxes.
- Drop sections that don't apply rather than padding them.

```bash
gh pr create \
  --base main \
  --title "<type>(<scope>): <subject>" \
  --body "$(cat <<'EOF'
## Description
<summary>

## Changes Made
- <change 1>
- <change 2>

## Testing
<what you ran and the result, e.g. `make check` — 56 passed, 100% coverage>
EOF
)"
```

If `gh` is unavailable or PR creation fails, print the push result and the
compare URL: `https://github.com/jkreileder/cf-ips-to-hcloud-fw/compare/main...<branch>`.

## Completion Checklist

- [ ] On a feature branch (never committed straight to `main`).
- [ ] Commit message is valid Conventional Commits, accurately describes the diff.
- [ ] Commit has a `Signed-off-by:` line (DCO) and a verified GPG/SSH signature.
- [ ] Branch pushed to `origin`.
- [ ] PR opened with a Conventional Commits title and a filled-out body.
- [ ] Reported the PR URL back to the user.

## Notes & Gotchas

- This repo enforces verified signatures and DCO via branch protection — an
  unsigned or un-signed-off commit will be rejected on push/merge.
- Don't reflow or reformat unrelated code just to commit; commit only the
  intended change.
- PR titles, like commits, must follow Conventional Commits (repo policy).

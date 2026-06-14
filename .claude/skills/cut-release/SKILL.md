---
name: cut-release
description: 'Cut a new release of cf-ips-to-hcloud-fw. Use when asked to release, cut a release, bump the version, tag a release, ship a version, or publish to PyPI/Docker. Bumps the version in pyproject.toml, finalizes the CHANGELOG entry, builds locally, commits (DCO sign-off + GPG-signed), creates a signed annotated v* tag, and pushes so CI builds, signs, and publishes to PyPI/Docker and drafts the GitHub release.'
argument-hint: 'Target version (e.g. 1.3.0) or bump type (major/minor/patch)'
---

# Cut a Release

Releases are **tag-driven**: pushing a `v*` tag triggers CI
(`python-package.yaml` + `docker.yaml`) to build, lint, test, sign, publish to
PyPI + TestPyPI, build multi-arch Docker images, and **draft** a GitHub release.
Your job here is the local prep (via a PR, since `main` is protected) + the tag.

## When to Use

- "Release 1.3.0", "cut a release", "bump the version and tag"
- "Ship a new version", "publish to PyPI"

## Prerequisites (verify, don't assume)

- Clean working tree, and `main` up to date with `origin/main`.
- **`main` is protected: direct pushes are rejected.** All commits (the release
  bump and the post-release dev-cycle bump) MUST land via a PR that is merged.
  Only the tag is pushed directly to a ref.
- Commit/tag signing configured (this repo requires verified signatures + DCO).
  Check `git config --get commit.gpgsign`; tags are signed with `git tag -s`.
- `gh` CLI authenticated (used to open the PR and view/publish the draft release).

## Procedure

### 1. Determine the target version

Read the current version:

```bash
grep '^version = ' pyproject.toml
```

- The dev version looks like `1.3.0.dev1` → the release version is `1.3.0`.
- Otherwise apply the requested bump (`major`/`minor`/`patch`) per SemVer.
- Confirm the chosen version with the user if it isn't explicit.

### 2. Pre-flight checks

```bash
git switch main && git pull --ff-only
git status                      # must be clean
make lint && make test          # gates must pass
```

### 3. Bump the version

Edit `pyproject.toml` `version = "..."` to the release version (drop any
`.devN` suffix). This is the single source of truth (`uv_build` reads it).

### 4. Finalize the CHANGELOG

In `CHANGELOG.md`, update the top entry:

- Change `## [vX.Y.Z] – Unreleased` to `## [vX.Y.Z] – YYYY-MM-DD` (today's date).
- Ensure the bullets accurately describe user-facing changes since the last tag.
  Cross-check with `git --no-pager log --oneline vLAST..HEAD`.
- Mark breaking changes with a leading `**Breaking:**` and security items with
  `**Security:**`, matching existing style.
- Keep prose wrapped at ~100 cols (repo Markdown style); don't reflow code/URLs.

### 4b. Bump the pinned version in docs/templates

Several files reference the previous **released** version (not `.devN`) and must
be bumped to the new `X.Y.Z`:

- `README.md` — the pinned Docker image tag examples
  (e.g. `jkreileder/cf-ips-to-hcloud-fw:X.Y.Z`, the `- \`X.Y.Z\`: ...` bullet,
  the Kubernetes `image:` line) and the attestation example `VERSION=X.Y.Z`.
- `.github/ISSUE_TEMPLATE/bug_report.md` — the example version
  `- cf-ips-to-hcloud-fw version: [e.g. X.Y.Z]`.

Find every occurrence of the old release version to be thorough (the `:latest`
and `:main` tags stay as-is — only the pinned numeric tag changes):

```bash
git --no-pager grep -nF "<old-version>" -- README.md .github/ISSUE_TEMPLATE/bug_report.md
```

`-F` matches the version literally — without it the dots in `1.2.3` are regex
wildcards and can overmatch.

If you renamed/added/removed a README section, also update the manually
maintained table of contents.

### 5. Build locally (sanity check)

```bash
make build      # rm -rf dist && uv build
ls dist         # expect a wheel + sdist for the new version
```

### 6. Open the release PR (the bump cannot go straight to `main`)

`main` is protected, so commit on a branch and open a PR:

```bash
git switch -c release/vX.Y.Z
git add pyproject.toml CHANGELOG.md README.md .github/ISSUE_TEMPLATE/bug_report.md
git commit -s -S -m "chore(release): vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --base main --title "chore(release): vX.Y.Z" \
  --body "Release vX.Y.Z. Bumps version and finalizes the changelog."
```

Use the `ship-changes` skill for this if you prefer. Wait for required checks,
get the PR merged, then continue.

### 7. Tag the merged release commit

After the PR is merged, tag **the exact merge commit** — don't just tag whatever
`main` points at, since another PR could land in the meantime and advance `main`
past the release. Capture the release PR's merge SHA and tag that commit.

```bash
release_sha="$(gh pr view <release-pr-number> --json mergeCommit --jq .mergeCommit.oid)"
git fetch origin
git show "$release_sha:pyproject.toml" | grep '^version = '   # confirm X.Y.Z
git tag -s vX.Y.Z "$release_sha" -m "vX.Y.Z"
git --no-pager tag -v vX.Y.Z                                  # verify signature
```

### 8. Push the tag

Tag refs are not blocked by the branch protection on `main`, so the tag can be
pushed directly:

```bash
git push origin vX.Y.Z
```

Pushing the tag starts the publish pipeline. Report the Actions URL:
`https://github.com/jkreileder/cf-ips-to-hcloud-fw/actions`.

> If pushing the tag is also rejected, the tag must be created via a release on
> the merged commit instead — pause and tell the user; do not force anything.

### 9. Publish the draft release

CI creates a **draft** GitHub release with provenance/SBOM/attestations.
Once the workflows succeed, review and publish it:

```bash
gh release view vX.Y.Z
gh release edit vX.Y.Z --draft=false   # after verifying notes & assets
```

### 10. Start the next dev cycle (via a second PR)

Once the release is published, open another PR (again, not a direct push to
`main`): bump `pyproject.toml` to the next dev version — **default to the next
patch** (e.g. after releasing `1.3.0`, use `1.3.1.dev1`; escalate to a
minor/major dev version later only if the work warrants it) — and add a fresh
`## [vNEXT] – Unreleased` heading at the top of `CHANGELOG.md` with a
`- Start new development cycle` bullet.

```bash
git switch -c chore/start-vNEXT-dev-cycle
# edit pyproject.toml + CHANGELOG.md
git commit -s -S -am "chore: start new development cycle"
git push -u origin chore/start-vNEXT-dev-cycle
gh pr create --base main --title "chore: start new development cycle" \
  --body "Begin vNEXT development."
```

Merge it (use the `ship-changes` skill if helpful).

## Completion Checklist

- [ ] `pyproject.toml` version set to the release version (no `.devN`).
- [ ] CHANGELOG top entry dated and accurate.
- [ ] Pinned version bumped in `README.md` and
      `.github/ISSUE_TEMPLATE/bug_report.md` (no stale old version remains).
- [ ] `make lint` and `make test` pass; `make build` produced dist artifacts.
- [ ] Release bump landed via a **merged PR** (not a direct push to `main`).
- [ ] Release commit is signed-off + GPG-signed.
- [ ] Annotated tag `vX.Y.Z` created on the merged commit, GPG-signed, verifies.
- [ ] Tag pushed; publish workflows green.
- [ ] Draft GitHub release reviewed and published.
- [ ] Next dev cycle started via a **second merged PR**
      (`pyproject.toml` + `CHANGELOG.md`).

## Gotchas

- `main` is protected — direct pushes are rejected. Both the release bump and
  the dev-cycle bump go through PRs; only the tag is pushed directly.
- Never publish PyPI manually — CI owns publishing on tag push.
- Tag the **merged** release commit, so the tagged tree's `pyproject.toml`
  version (`X.Y.Z`) matches the tag (`vX.Y.Z`).
- Branch protection rejects unsigned commits/tags; ensure signing works first.

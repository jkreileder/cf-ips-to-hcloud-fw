# cf-ips-to-hcloud-fw – Agent Instructions

## Quick Pitch

- CLI syncs Cloudflare IPv4/IPv6 CIDRs into Hetzner Cloud firewalls through
  official APIs.
- Python ≥3.11, src-layout package, Pydantic models; released to PyPI and Docker
  (linux/amd64 + arm64).

## Where Things Live

- `src/cf_ips_to_hcloud_fw/__main__.py` drives CLI: parse args → configure logging
  → fetch Cloudflare ranges → update firewalls.
- `cloudflare.py` wraps the Cloudflare SDK, validates with `CloudflareCIDRs`, and
  fails via `log_error_and_exit`.
- `firewall.py` edits Hetzner rules selected by `__CLOUDFLARE_IPS_*__` markers,
  then calls `client.firewalls.set_rules`; per-firewall API errors are recorded
  and the run continues, exiting non-zero at the end (see `ProjectOutcome`).
- `config.py` resolves `Project` models via `load_projects`: explicit `-c` file,
  else a default `config.yaml`, else `HCLOUD_TOKEN` + `HCLOUD_FIREWALLS` env vars
  (`_read_config` / `_read_config_from_env`); empty/invalid configs exit early.
- `models.py` defines Pydantic structures (`CloudflareCIDRs`, `Project`) used for
  validation and config.
- `custom_logging.py` handles logging setup and the error helpers: `log_error`
  (recoverable; logs and returns) and `log_error_and_exit` (logs then exits).
- Tests in `tests/` mirror modules with mocked SDK clients for fast runs.
- `.claude/skills/` holds the project skills (`cut-release`, `ship-changes`).

## Daily Flow

- `make venv` runs `uv sync --group dev --frozen` into `.venv/`; every other
  target re-syncs when `pyproject.toml` or `uv.lock` changes. The sync checks
  the locked deps against OSV's malware advisories, so it needs network access;
  set `UV_MALWARE_CHECK=0` to sync offline.
- `make lint` (ruff check, ruff format --check, ty) → `make test` (pytest,
  coverage ≥95%, writes `coverage.xml` + `htmlcov/`) → `make build` (`uv build`
  into a fresh `dist/`). `make` runs all three; `make check` runs lint + test.
- `make audit` runs `uv audit` against the lock file.
- `make clean` runs `git clean -xdf`, keeping only `config.yaml` and
  `.claude/settings.local.json`; it removes `.venv/` and all other untracked files.
- Run the CLI via `.venv/bin/cf-ips-to-hcloud-fw -c config.yaml`; `-d` enables
  debug logs, `-v` prints the packaged version. Config entries provide `token` +
  `firewalls` list.

## Dependency & Packaging Rules

- Dependencies live in `pyproject.toml`; `uv.lock` captures the resolved set. Use
  `make upgrade-deps` (`uv lock --upgrade`) for dependency bumps, and commit
  `uv.lock` only when it was changed on purpose.
- The Docker builder stage runs the same uv sync / lint / test / build steps;
  the final image installs from the lock file.
- `.dockerignore` whitelists the build context: `src/`, `tests/`, `LICENSE`,
  `pyproject.toml`, `README.md`, `uv.lock`. A file the image needs must be added
  there.
- `Dockerfile.rego` is a buildx build policy: every image the Dockerfile build
  pulls (base images, the `# syntax=` frontend, the SBOM generator) must come
  from its allowlisted repositories and be pinned by digest. A new image
  repository must be added there. CI tooling images (binfmt, the BuildKit
  driver) are outside it.

## CI & Quality Gates

- `python-package.yaml` runs uv sync / lint / test / build on CPython 3.11–3.15,
  uploads coverage, and builds the attested release dist via
  `build-and-attest-dist.yaml`.
- `docker.yaml` builds the multi-arch image via `docker-build.yaml`, scans it
  (Docker Scout + Grype), signs it, and attaches SLSA provenance. `rescan.yaml`
  rescans the released `:1` image daily.
- Also: CodeQL, dependency review, Scorecard, TruffleHog, pre-commit, PR-title
  check, pytest result publication, uv dependency submission, Docker Hub
  description sync.
- `auto-release.yaml` opens a release PR (as a GitHub App, auto-merge on) when
  a rebuilt `:main` image fixes Grype findings that the released `:1` image
  still has; `auto-release-publish.yaml` tags the merged commit, waits for the
  publish runs, publishes the GitHub release, and opens the dev-cycle PR. The
  edits come from `.github/scripts/auto_release.py`. Before cutting a release
  by hand, check for an open `auto-release/*` PR.

## Commits & PRs

- Commits need a DCO sign-off (`git commit -s`) and a cryptographic signature
  (GPG/SSH); branch protection rejects unsigned commits.
- Commit messages and PR titles follow Conventional Commits
  (`<type>[optional scope]: <description>`), e.g. `chore(deps): bump ruff to
  v0.14.6`. Merges are squash-only, so the PR title becomes the commit on `main`.
- A change users or operators would notice (CLI behavior, the container image or
  how it is built, a security fix, anything breaking) adds a bullet to the
  `## [vX.Y.Z] – Unreleased` section of `CHANGELOG.md` in the same PR. Match the
  existing entries, with `**Security:**` and `**Breaking:**` prefixes where they
  apply. CI-only, docs-only and dev-tooling changes need no entry, and neither do
  Renovate PRs: dependency and base-image bullets are written at release time.
- Work that calls for a minor or major release also bumps the dev version in
  `pyproject.toml` (and `uv.lock`) to that release, e.g. `1.6.0.dev1`. Automated
  security releases only cut patches and stop at such a version.
- pre-commit hooks (`pre-commit install` or `prek install`) run ruff, ty, the
  uv lock check, gitleaks, markdownlint-cli2, actionlint, zizmor, the Renovate
  config validator, and basic file hygiene checks.

## Gotchas

- Make recipes run under `bash -eu -o pipefail`; avoid zshisms.
- Missing wheels or odd installs? Remove `.venv/` (or `make clean`) then
  rerun `make venv`.
- Preserve the `__CLOUDFLARE_IPS_*__` description tokens; firewall matching
  logic depends on them.
- When editing `README.md`, update the table of contents if you add, remove,
  or rename sections. The TOC is manually maintained and marked with
  `<!-- omit in toc -->` for the title.
- Markdown style: When creating or editing Markdown files, aim for a
  maximum line width of 100 characters and wrap prose at sentence boundaries
  where practical. Do not reflow code blocks, tables, YAML snippets, or long
  URLs — those can exceed the limit. This matches the 100-column ruler in
  `.vscode/settings.json`.

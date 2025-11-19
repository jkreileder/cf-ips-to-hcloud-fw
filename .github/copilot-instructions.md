# cf-ips-to-hcloud-fw – Copilot Onboarding

## Quick Pitch
- CLI syncs Cloudflare IPv4/IPv6 CIDRs into Hetzner Cloud firewalls through official APIs.
- Python ≥3.10, src-layout package, Pydantic models; released to PyPI and Docker (linux/amd64 + arm64).

## Where Things Live
- `src/cf_ips_to_hcloud_fw/__main__.py` drives CLI: parse args → configure logging → fetch Cloudflare ranges → update firewalls.
- `cloudflare.py` wraps the Cloudflare SDK, validates with `CloudflareCIDRs`, and fails via `log_error_and_exit`.
- `firewall.py` edits Hetzner rules selected by `__CLOUDFLARE_IPS_*__` markers, then calls `client.firewalls.set_rules`.
- `config.py` loads YAML into `Project` models; empty/invalid configs exit early.
- `models.py` defines Pydantic structures (`CloudflareCIDRs`, `Project`) used for validation and config.
- `custom_logging.py` handles logging setup and exit routines (`log_error_and_exit`).
- Tests in `tests/` mirror modules with mocked SDK clients for fast runs.

## Daily Flow
- First bootstrap: `make venv` (calls `uv sync`, creates `.venv/`, installs default + dev groups from `uv.lock`). Later targets refresh the env when the lock or `pyproject.toml` changes.
- Default loop: `make lint` (ruff + pyright) → `make test` (pytest, coverage≥80, writes `coverage.xml` + `htmlcov/`) → `make build` (`uv build`). `make` runs all three.
- `make clean` wraps `git clean -xdf`; it nukes `.venv/` and every untracked artifact if you need a hard reset.
- Run the CLI via `.venv/bin/cf-ips-to-hcloud-fw -c config.yaml`; `-d` enables debug logs, `-v` prints the packaged version. Config entries provide `token` + `firewalls` list.

## Dependency & Packaging Rules
- Dependencies live in `pyproject.toml`; `uv.lock` captures the resolved set. Use `make upgrade-deps` (aka `uv lock --upgrade`) for dependency bumps.
- Expect churn in generated artifacts: `uv.lock`, `dist/`, coverage outputs. Commit only when intentionally rebuilt.
- Docker builder runs via `uv` (sync, lint, test, build) and the final image installs using the lock file.

## CI & Quality Gates
- `python-package.yaml` runs the uv sync/lint/test/build steps directly on CPython 3.10–3.14, uploads coverage, SBOM, and attestations.
- `docker.yaml` performs multi-arch builds, security scans (Docker Scout + Grype), signing, and SLSA provenance.
- Additional workflows cover CodeQL, dependency review, scorecard, and pytest result publication.

### Additional repo maintenance tools
- `.dockerignore` — present at the repository root and used by the `docker.yaml` workflow; it intentionally keeps the Docker build context small by whitelisting only project files needed for the container (the `src` package, `tests`, `LICENSE`, `pyproject.toml`, `README.md`, and `uv.lock`). See `.dockerignore` if you get container build surprises.
- `pre-commit` — a `.pre-commit-config.yaml` file is present and configured to run utilities like `ruff` and `gitleaks`. New contributors should install hooks with `pre-commit install` or `prek install`.
- Commit sign-offs — PRs require developer sign-off using `git commit -s`; you can see the PR checklist in `.github/pull_request_template.md`. This is the project DCO requirement. GitHub also enforces cryptographically-signed commits for this repository via branch protection — you must configure GPG/SSH commit signing locally or use the `-S` flag to sign commits if required. Note that package and image artifacts are also cryptographically signed during CI.
- Commit style — commit messages should follow Conventional Commits (type: scope: subject).

## Gotchas
- Python 3.14 emits a benign Pydantic V1 warning; CI accepts it.
- Make recipes run under `bash -eu -o pipefail`; avoid zshisms.
- Missing wheels or odd installs? Remove `.venv/` (or `make clean`) then rerun `make venv`.
- Preserve the `__CLOUDFLARE_IPS_*__` description tokens; firewall matching logic depends on them.

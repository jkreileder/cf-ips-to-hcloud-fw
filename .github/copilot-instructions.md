# cf-ips-to-hcloud-fw – Copilot Onboarding

## Quick Pitch
- CLI syncs Cloudflare IPv4/IPv6 CIDRs into Hetzner Cloud firewalls through official APIs.
- Python ≥3.10, src-layout package, Pydantic models; released to PyPI and Docker (linux/amd64 + arm64).

## Where Things Live
- `src/cf_ips_to_hcloud_fw/__main__.py` drives CLI: parse args → configure logging → fetch Cloudflare ranges → update firewalls.
- `cloudflare.py` wraps the Cloudflare SDK, validates with `CloudflareCIDRs`, and fails via `log_error_and_exit`.
- `firewall.py` edits Hetzner rules selected by `__CLOUDFLARE_IPS_*__` markers, then calls `client.firewalls.set_rules`.
- `config.py` loads YAML into `Project` models; empty/invalid configs exit early.
- Tests in `tests/` mirror modules with mocked SDK clients for fast runs.

## Daily Flow
- First bootstrap: `make venv` (creates `venv/`, installs hashed deps). Later targets auto-recreate the env if missing.
- Default loop: `make lint` (ruff + pyright) → `make test` (pytest, coverage≥80, writes `coverage.xml` + `htmlcov/`) → `make build` (refresh `requirements*-pep508.txt`, run `python -m build`). `make` runs all three.
- `make clean` wraps `git clean -xdf`; it nukes `venv/` and every untracked artifact.
- Run the CLI via `venv/bin/cf-ips-to-hcloud-fw -c config.yaml`; `-d` enables debug logs, `-v` prints the packaged version. Config entries provide `token` + `firewalls` list.

## Dependency & Packaging Rules
- Runtime deps live in `requirements.in`, dev deps in `requirements-dev.in`; regenerate hashes with `make regenerate-hashes` instead of editing `.txt` files.
- Expect churn in generated artifacts: `requirements*-pep508.txt`, `dist/`, coverage outputs. Commit only when intentionally rebuilt.
- Docker builder reuses hashed requirements and reruns lint/test/build before emitting the final Alpine image.

## CI & Quality Gates
- `python-package.yaml` runs `make venv lint test build` on CPython 3.10–3.14, uploads coverage, SBOM, and attestations.
- `docker.yaml` performs multi-arch builds, security scans (Docker Scout + Grype), signing, and SLSA provenance.
- Additional workflows cover CodeQL, dependency review, scorecard, and pytest result publication.

## Gotchas
- Python 3.14 emits a benign Pydantic V1 warning; CI accepts it.
- Make recipes run under `bash -eu -o pipefail`; avoid zshisms.
- Missing wheels or odd installs? Remove `venv/` (or `make clean`) then rerun `make venv`.
- Preserve the `__CLOUDFLARE_IPS_*__` description tokens; firewall matching logic depends on them.

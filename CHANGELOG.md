# Changelog

<!-- markdownlint-disable MD024 -->

## [v1.4.3] – 2026-09-05

- **Security:** The container image now ships Alpine's `util-linux` 2.42.3-r0, fixing four
  high-severity CVEs in the `libuuid` it installs — CVE-2026-76642, CVE-2026-78408,
  CVE-2026-78409 and CVE-2026-78410. The v1.4.2 image was built against 2.42.1-r0
- Updated the Cloudflare SDK to 5.7.0, Pydantic to 2.13.5 and anyio to 4.15.0, and refreshed the
  pinned base images (`python:3.14.7-alpine3.24`, `python:3.14.7-trixie`, `astral/uv` 0.12.10)
  and the Dockerfile frontend to 1.27.0

## [v1.4.2] – 2026-08-27

- **Security:** The container image now runs `apk upgrade` in its final stage, so Alpine
  security fixes reach the image without waiting for the next rebuild of the official
  `python:*-alpine` base. That base is rebuilt only on CPython and Alpine point releases,
  which had left the published image with a `libssl3`/`libcrypto3` Alpine had already
  patched — ten fixable CVEs, seven of them high. The upgrade covers the whole base going
  forward, not just openssl. It adds one build input outside the digest-pinned set
  (Alpine's package repo; apk still verifies package signatures), so rebuilding a given
  commit is byte-identical only while that repo has not moved in between. Release builds
  were already cache-free; `main` and pull-request builds now exclude the final stage from
  the layer cache, so the upgrade cannot replay a stale layer

## [v1.4.1] – 2026-08-17

- Container images are now reproducible: rebuilding a given commit yields
  byte-identical per-platform image manifests. `SOURCE_DATE_EPOCH` is taken from
  the source commit rather than the clock, and the image exporter runs with
  `rewrite-timestamp=true` — without the latter only the config, history and
  index timestamps are pinned, while file mtimes inside the layers still drift.
  One further source of variance was removed: `uv pip install` writes a
  `uv_cache.json` into the project's own `.dist-info` containing nothing but a
  wall-clock install timestamp (every other field is null or empty), and it has
  no runtime purpose, so it is now deleted along with its `RECORD` line. With
  that, two consecutive cache-free builds on the pinned BuildKit produce the
  same manifest digest. The multi-platform *index* digest still differs per
  build, because buildx provenance deliberately records each invocation
  (moby/buildkit#3421) — reproducibility is verifiable at the level of the image
  the attestations point at, which is the in-toto subject
- Container attestation moved out of the build job into its own `Attest` job in
  `docker-build.yaml`, so a transient Sigstore or GitHub outage during a release
  can be retried with "Re-run failed jobs" instead of re-running the build. The
  old layout made that retry unusable: re-running the job re-executed the push
  before it ever reached the attestation step, and a rebuild cannot reproduce
  the digest that was published — buildx provenance (`mode=max`) stamps a fresh
  `invocationId` and start/finish timestamps into every build, so the image
  index digest differs even from an identical context. That is deliberate
  upstream rather than a gap `SOURCE_DATE_EPOCH` could close: moby/buildkit#3421
  requested reproducible provenance and was closed as not planned, since
  provenance describes one invocation while it is the image it points at that is
  meant to be reproducible. The retry would therefore have retargeted the release
  tags to a second image. The attest job consumes only the digest the build job
  outputs, so it can never push an image itself. Both
  jobs still live in the same reusable workflow file, which is what the SLSA
  Build Level 3 `--signer-workflow` check pins, so published verification
  commands are unchanged

## [v1.4.0] – 2026-08-16

Security-hardening release. An agentic SAST sweep of the repository turned up a set of
issues across the CLI and the release pipeline; every finding is either fixed here or
recorded as accepted. The only behaviour change an existing deployment can notice is the
exit code for an empty config, called out first below.

- **Breaking:** A config file containing no projects now exits 1 instead of 0.
  `[]` is a valid YAML document, so a truncated file or a mis-rendered template
  validated cleanly and synced nothing — while the exit code told systemd, a
  Kubernetes CronJob, or a cron wrapper the run was healthy and the firewall
  rules quietly froze at their last-synced state. The environment-variable path
  already failed loudly for the same condition; the two now agree
- **Security:** Hetzner API tokens can no longer reach the log stream through
  third-party exception text. A token carrying a trailing newline — routine for
  a Kubernetes secret mounted as a file, or a YAML block scalar — made
  `requests` raise `InvalidHeader` with the whole `Authorization: Bearer …`
  value in its message, which the per-firewall error handlers logged verbatim
  so the run could continue. `InvalidHeader` is now reported by type only. It
  is the sole exception that quotes the header back, so every other failure —
  hcloud's own `APIException`/`ActionException`, and `requests`' connection,
  TLS, proxy and timeout errors — keeps its full message, which is where the
  detail that makes a failed sync diagnosable lives
- **Security:** Config file YAML parse errors no longer echo any part of the file into the
  log. PyYAML's error formatting embeds a snippet of the offending source line,
  which put the raw Hetzner API token into the log stream whenever the syntax
  error sat on or next to the `token:` line (an unterminated quote, a stray tab,
  an unclosed flow mapping); PyYAML also interpolates alias, anchor, and tag
  names into its own error text, so a stray `*` or `&` before the value leaked
  it too. Errors now report only the error type plus the line and column,
  matching the redaction already applied to config validation errors
- **Security:** Cloudflare CIDR responses are checked for routability, not just syntax. A
  range is rejected if it overlaps IANA special-purpose space (RFC 1918,
  loopback, link-local, CGNAT, multicast, reserved, documentation) or is
  broader than /8 for IPv4 or /16 for IPv6, instead of being written verbatim
  into firewall rules — so a broken or tampered response can no longer widen an
  allow list, whether by naming a reserved range outright (`10.0.0.0/8`) or by
  hiding it inside an aggregate (`0.0.0.0/0`, `128.0.0.0/1`, `8000::/1`). The
  prefix floors sit far below the /13 and /29 the published list bottoms out
  at, so a legitimately broader range from Cloudflare will not fail the run
- **Security:** The uv base-image provenance gate can no longer be satisfied by
  a Dockerfile comment. It grepped the whole file, so a well-formed
  `docker.io/astral/uv:…@sha256:…` reference on a comment line passed
  verification while the real `FROM` pointed anywhere — publishing an image
  built on an unattested base with the provenance check reported green.
  Comments are now stripped before matching, and every uv reference the file
  pulls must be digest-pinned, which also closes an unpinned
  `docker.io/astral/uv:latest` riding along unverified beside a pinned one.
  Tagless digest pins (`uv@sha256:…`) and images pulled by `COPY --from=` are
  covered too
- **Security:** A fork pull request can no longer steer the test-result
  publisher. GitHub runs the fork's copy of `python-package.yaml` for a fork PR,
  so the `event-file` artifact it uploaded was attacker-controlled — and the
  publishing action reads the target PR number straight out of that file, in
  preference to resolving it from the commit. A crafted event file therefore
  redirected the bot's comment onto any pull request in the repository. The
  event file is now written in the trusted job instead of downloaded, so the PR
  is resolved from the triggering run's own commit, and the artifact that made
  this possible is no longer produced. The report's base-commit comparison now
  comes from the GitHub API rather than that file
- Pinned the Cloudflare API base URL in code. The SDK falls back to the
  `CLOUDFLARE_BASE_URL` environment variable when no base URL is passed, so
  anything able to set an env var on the job — a CronJob spec, a compose file, a
  workflow env block — could point the IP fetch at its own server and dictate
  what the firewall rules end up allowing. That variable is now inert
- Config tokens are stripped of surrounding whitespace. A trailing newline is
  not part of the credential, and carrying it previously made *every* API
  request fail, since `requests` rejects a header value containing one
- GitHub Actions digest refreshes are no longer automerged. The 3-day
  `minimumReleaseAge` hold cannot gate them — the `github-tags` datasource ages
  a digest against the matched version's original release date, so an action tag
  force-pushed to new commits clears the check immediately. Image digests still
  automerge, since Docker Hub's `tag_last_pushed` restarts the hold
- Test-result publishing is no longer cancellable from a fork. The concurrency
  group was keyed on the triggering run's branch name alone, so a fork pull
  request from a branch called `main` shared a group with the base repository's
  own main-branch run — and `cancel-in-progress` let the fork's run cancel it,
  dropping the results for that push. The key now includes the head repository

## [v1.3.3] – 2026-08-13

- Switched the python base images from the `public.ecr.aws` mirror back to
  Docker Hub (`docker.io/library/python`): GitHub-hosted runners now ship an
  embedded rate-limit-free Docker Hub pull token, which the build already
  relies on for the uv/binfmt/buildkit pulls, and the ECR mirror was lagging
  behind Docker Hub on tag updates — this release's alpine base picks up the
  newer digest the mirror was missing
- Releases attach the signed attestation bundle (`multiple.intoto.jsonl`,
  covering the wheel and sdist) as a release asset again, restoring offline
  verification with `gh attestation verify --bundle` (see README.md); the
  bundles now carry `slsa.dev/provenance/v1` predicates and verify with `gh`
  rather than `slsa-verifier`

## [v1.3.2] – 2026-08-12

Provenance-migration release: the retired `slsa-github-generator` is fully replaced by
GitHub artifact attestations signed from dedicated reusable workflows (SLSA Build
Level 3). The CLI itself is unchanged from v1.3.1.

- Replaced the retired `slsa-github-generator` provenance for Python release
  artifacts with GitHub artifact attestations (the generator project is no
  longer maintained). Attestations were already published for every wheel and
  sdist and are the verification path documented in the README
  (`gh attestation verify`); releases no longer attach a `multiple.intoto.jsonl`
  asset
- Dropped the `slsa-github-generator` container provenance jobs for Docker Hub,
  Quay, and GHCR for the same reason, along with the smoke-test workflow that
  guarded the generator before releases. GitHub artifact attestations remain
  published for the image on all three registries (`push-to-registry`, verified
  with `gh attestation verify oci://…`), alongside the BuildKit inline SBOM and
  provenance
- Moved the Python build and attestation into a reusable workflow
  (`build-and-attest-dist.yaml`) so the artifact attestations qualify for SLSA
  Build Level 3 per GitHub's guidance; verifiers can require the signer with
  `gh attestation verify --signer-workflow
  jkreileder/cf-ips-to-hcloud-fw/.github/workflows/build-and-attest-dist.yaml`
- Moved the Docker build and attestation into a reusable workflow
  (`docker-build.yaml`) for the same SLSA Build Level 3 guarantee on the
  container images; verify with `gh attestation verify oci://… --signer-workflow
  jkreileder/cf-ips-to-hcloud-fw/.github/workflows/docker-build.yaml`
- **Security:** Enabled GitHub's "require actions to be pinned to a full-length
  commit SHA" repository policy, previously blocked by the generator's
  tag-referenced reusable workflows
- Maintenance: dependency and CI-tooling updates, and test-result publishing no
  longer reports failures for runs superseded by a newer push

## [v1.3.1] – 2026-08-12

- Hardened Hetzner firewall updates: the CLI now waits for each asynchronous
  `set_rules` action to finish (surfacing action failures and timeouts instead of
  reporting success at submission), applies a bounded connect/read timeout so a
  hung API call can no longer stall the run indefinitely, and records transport
  errors (connection/DNS/TLS failures) as per-firewall failures so the remaining
  firewalls and projects are still processed
- Guarded the release workflows against mistaken tags: a `v*` tag now fails the
  Python and Docker publish pipelines unless the tag matches the `pyproject.toml`
  version exactly and that version is a final `X.Y.Z` release (no `.dev`,
  pre-release, or local component), preventing a wrong or non-final version from
  reaching PyPI or producing mismatched Docker semver tags
- Maintenance: dependency updates and CI hardening — daily CVE rescans of the
  released Docker image, malware scanning of locked dependencies (plus a `make
  audit` target), and a smoke test that gates releases on the SLSA generator
  still working

## [v1.3.0] – 2026-06-14

- Added an environment-variable configuration mode for the common single-project
  case: when `-c/--config` is omitted, the tool uses a `config.yaml` in the
  working directory if present, otherwise builds one project from `HCLOUD_TOKEN`
  and a newline-separated `HCLOUD_FIREWALLS` list (one firewall name per line, so
  names may contain commas and spaces). Docker and Kubernetes users can
  now pass the token as a native secret without mounting a config file, and the
  container image's default command works for both file-mounted and env-var
  setups. Passing `-c` keeps that file as the sole source
- Made firewall syncing resilient to per-firewall failures: a Hetzner API error
  on one firewall (for example an expired token or a transient error) is now
  logged and recorded instead of aborting the run, so the remaining firewalls
  and projects are still processed. The CLI still exits with code 1 when any
  firewall failed or was skipped, now reporting both groups in a single message
  (`Some firewalls were not updated (failed: …; not found: …)`)
- Upgraded Docker build provenance attestations to use the stable SLSA v1 schema
- **Breaking:** Added POSIX config-permission checks that reject group/other
  writable config files while allowing common read-only Docker/Kubernetes
  secret mounts with a warning
- Replaced `pyright` with `ty` for type checking in the lint pipeline and
  removed the `ms-python.vscode-pylance` VS Code extension recommendation
- Migrated dependency automation from Dependabot to Renovate
  (`config:best-practices`, grouped updates, automerge for low-risk bumps, and
  digest pinning)
- Pinned the remaining build-tooling images (binfmt, BuildKit, uv) by digest so
  the signed multi-arch build is fully reproducible
- Bumped the final container image base to Alpine 3.24
- Streamlined CI and contributor tooling: prek-based pre-commit runner,
  concurrency limits and job timeouts, and fewer Docker Hub pulls / duplicate
  PR builds

## [v1.2.1] – 2026-05-30

Maintenance release with dependency and CI updates.

- Added SLSA attestation verification guidance for Python wheels/source
  distributions and container images, and added the SLSA badge to the README
  (#1026, #1028)
- Simplified Docker release attestations while keeping build provenance and image
  SBOM usage (#1028)
- Added artifact attestations for Python source tarballs (#1027)
- Clarified Docker image references for Docker Hub, Quay.io, and GHCR in the
  README (#1028)
- Refreshed runtime and development dependencies, plus GitHub Actions and
  pre-commit tooling updates across the release cycle (for example #1025,
  #1217, #1231)

## [v1.2.0] – 2025-12-07

Feature release with `uv` migration, improved API response validation, and enhanced error
handling.

- **Breaking:** Changed exit behavior when firewalls are not found—the CLI now exits with
  code 1 and reports all skipped firewalls instead of silently continuing
- Added validation to detect empty IPv4 or IPv6 CIDR lists from Cloudflare API responses to
  prevent incomplete firewall rules
- **Security:** Enabled strict Pydantic validation (`extra="forbid"`) on the configuration
  model to reject config typos and unknown fields, preventing silent misconfigurations
- Added `min_length=1` validation for the `firewalls` field to ensure at least one firewall
  is specified in configuration
- Adopted `uv` for dependency syncing, builds, and the Docker pipeline, including pinning
  image digests and link modes for reproducible containers (#960)
- Switched GitHub workflows to `astral-sh/setup-uv` so Python and uv are provisioned
  consistently (#960)
- Reworked version detection to rely on `importlib.metadata` with a tested fallback when
  package metadata is unavailable (#960)
- Ensured license files ship with the sdist, and documented the new tooling in contributor
  instructions (#960)
- Changed firewall module API and logging for better context and resilience
  - Added `project_index` context to logging and function calls across the firewall module
    (update_project, update_firewall, fw_set_rules, update_source_ips, update_firewall_rule)
  - `update_firewall_rule` now receives an `IPVersionTargets` NamedTuple (ipv4, ipv6)
    instead of separate boolean flags, simplifying the callsite and improving clarity
  - `update_project` and several helper functions were converted to keyword-only
    style for clearer call semantics and to reduce positional-argument confusion
  - Output and skipped-firewall messages now use repr(name) to safely represent
    firewall names that include quotes or special characters (new tests added)
  - **Breaking:** Function signatures were changed (see above). If you consume
    these functions externally, please update calls and review the docs or
    pin to an earlier release.

## [v1.1.0] – 2025-11-14

Feature release with CI hardening and new runtime guarantees.

- **Breaking:** Dropped Python 3.9 support; the tested range now spans CPython 3.10–3.14 (#926,
  #947, #955)
- Added a TruffleHog secret-scanning workflow to the GitHub Actions pipeline (#944)
- Documented Copilot onboarding instructions for contributors (#933)
- Updated test configuration and dependency mocks for better compatibility (#949)
- Standardized array formatting and adopted Dockerfile syntax 1.20 (#950, #951)
- Bumped Ruff, pip/pip-tools, and refreshed GitHub Actions and base images (#955, #954,
  #947, #945, #940, #935, #930, #956)

## [v1.0.17] – 2025-06-20

Fix StepSecurity policy

## [v1.0.16] – 2025-06-20

Maintenance release with dependency and CI updates.

- Updated Python and Docker base images
- Bumped ruff, codeql-action, and other dependencies
- Minor improvements to CI workflows

## [v1.0.15] – 2024-12-22

Maintenance release with updated dependencies.

## [v1.0.14] - 2024-11-07

Maintenance release with fix PyPi release workflow.

## [v1.0.13] - 2024-11-07

Maintenance release with updated dependencies.

## [v1.0.12] - 2024-07-15

Maintenance release with updated dependencies.

## [v1.0.11] - 2024-05-09

### Added

- SBOM uploads to GitHub releases (#300)
- Egress policies for PyPi releases (#299)
- SBOM and attestations for DockerHub, Quay, GitHub Container Registry (#297)
- SBOM generation after build (#295)
- Attestations for python artifacts and sbom (#294)
- GitHub artifact attestation across registries (#284)

### Changed

- Workflow action versions and naming (#301)
- SBOM output files naming (#298)
- Docker workflow security settings (#296)
- Various dependencies and actions bumped (Refer to commit history for detailed list)

## [v1.0.10] - 2024-04-12

### Added

- Allow api.securityscorecards.dev and api.deps.dev in egress policy (#218, #207)

### Changed

- Bump various dependencies and actions (Refer to commit history for detailed list)
- Update Python base images in Dockerfile (#219, #229)
- Update sbom generator to version 1.6.4 (#224)
- Remove CODECOV_TOKEN (#235)

## [v1.0.9] - 2024-03-16

### Added

- Pin sbom-generator to specific version and hash (#132)
- Optimize dependency hash regeneration (#123)

### Changed

- Update Python base image in Dockerfile (#193, #122)
- Bump various dependencies and actions (Refer to commit history for detailed list)
- Remove unneeded gdbm dependency with GPL-3.0 license (#131)
- Move constraint spec from pip-compile invocation to requirements-dev.in (#133)

## [v1.0.8] - 2024-02-08

### Added

- Added CODECOV_TOKEN to Codecov action and cli.codecov to allowed endpoints

### Changed

- Updated Python base image in Dockerfile
- Upgraded `pyright` to 1.1.350, `ruff` & `ruff-pre-commit` to v0.2.1, `pydantic`
  to 2.6.1, and pip to 24.0
- Updated `certifi`, `urllib3`, and pluggy versions
- Updated ruff and gitleaks pre-commit hooks and ruff configuration
- Bumped various GitHub actions and Docker actions
- Updated DOCKER_METADATA_ANNOTATIONS_LEVELS environment variable
- Bumped pytest from 7.4.4 to 8.0.0
- Bumped version to 1.0.8-dev

## [v1.0.7] - 2024-01-20

### Added

- Check passed arguments in test_main (#74)
- Add CPython implementation to classifiers (#61)
- Pin pre-commit hook versions (#59)
- Update Kubernetes CronJob API version (#54)
- Add SLSA3 workflows for Docker images (#50)

### Changed

- Update base image shas (#73)
- Bump ruff from 0.1.13 to 0.1.14 (#72)
- Update pyyaml hashes (#71)
- Bump docker/scout-action from 1.2.2 to 1.3.0 (#67)
- Bump python from `ee9a59c` to `247e70c` (#70)
- Bump actions/dependency-review-action from 3.1.5 to 4.0.0 (#68)
- Bump anchore/scan-action from 3.5.0 to 3.6.0 (#69)
- Bump actions/upload-artifact from 4.1.0 to 4.2.0 (#66)
- Bump github/codeql-action from 3.23.0 to 3.23.1 (#65)
- Refactor: Modularize Cloudflare, hcloud firewall, config and logging functionality
  into separate modules (#64)
- Update pyright to version 1.1.347 (#63)
- Update pyright to version 1.1.346 (#62)
- Bump actions/upload-artifact from 4.0.0 to 4.1.0 (#60)
- Bump ruff from 0.1.12 to 0.1.13 (#58)
- Bump ruff from 0.1.11 to 0.1.12 (#57)
- Bump python from `c805c5e` to `ee9a59c` (#55)
- Bump actions/download-artifact from 4.1.0 to 4.1.1 (#53)
- Bump github/codeql-action from 3.22.12 to 3.23.0 (#52)
- Bump anchore/scan-action from 3.4.0 to 3.5.0 (#51)

## [1.0.6] - 2024-01-08

### Added

- Test cases for command line arguments in `test_main.py` and `test_version.py` (#46)
- `objects.githubusercontent.com` to allowed hosts (#45)
- Upgrade instructions for pipx and pip
- Error handling for unreadable configuration files or directories (#37)
- Integration of SLSA provenance generation (#36)
- Recommended ignore rules for Ruff

### Changed

- Fixed PyPI badge link (#47)
- Updated `pyright` to version 1.1.345 (#43)
- Updated `docker/metadata-action` from 5.4.0 to 5.5.0 (#42)
- Updated badges in `README.md` (#40)
- Updated `cloudflare` from 2.15.1 to 2.16.0 (#38)
- Updated `actions/dependency-review-action` from 3.1.4 to 3.1.5 (#39)
- Updated `hcloud` to v1.33.2
- Updated `ruff` to v0.1.11
- Enabled more lint rules and adapted code to them

### Removed

- Scanning of context and builder for sbom (#44)
- Superfluous ruff target-version

### Security

- Updated `anchore/scan-action` from 3.3.8 to 3.4.0 (#34)

## [v1.0.5] - 2024-01-01

### Fixed

- Resolved issues with Docker image signing through a rebuild. This ensures the
  integrity and authenticity of the Docker images.

## [v1.0.4] - 2024-01-01

### Changed

- Improved log messages for better clarity and understanding.

### Performance Improvements

- Reduced Docker image size for faster download and deployment.

### Testing

- Added more tests to improve code coverage and reliability.

### Notes

- No functional changes were made in this release. The focus was on improvements
  and optimizations.

## [v1.0.3] - 2023-12-19

Remove caching from Docker build to work-around buildx bug.

## [v1.0.2] - 2023-12-19

No change rebuild to get Docker attestation rights.

## [v1.0.1] - 2023-12-16

No functional changes.

### Added

- Tests
- Coverage checks

## [v1.0.0] - 2023-12-09

- First release

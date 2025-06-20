# Changelog

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
- Upgraded `pyright` to 1.1.350, `ruff` & `ruff-pre-commit` to v0.2.1, `pydantic` to 2.6.1, and pip to 24.0
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
- Refactor: Modularize Cloudflare, hcloud firewall, config and logging functionality into separate modules (#64)
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

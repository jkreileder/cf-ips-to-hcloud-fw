# syntax=docker/dockerfile:1.27.0@sha256:bde3983e9c939224420ddaf6b784cc30e09b035a4dea01f581230c50809f372e
# check=experimental=all;error=true

FROM --platform=$BUILDPLATFORM docker.io/astral/uv:0.12.7-python3.14-trixie@sha256:a8433b4080bfc7d63c803189f90a026acb9b2c8d9a003868236194a839da9a6c AS uv-tools-trixie
FROM docker.io/astral/uv:0.12.7-python3.14-alpine3.23@sha256:1f178a7bcca4ada7464ca87f17a0a27a9f077ee1e22e47d8937259502871f074 AS uv-tools-alpine

FROM --platform=$BUILDPLATFORM docker.io/library/python:3.14.7-trixie@sha256:48651f00145ad01e9f83d468c57cec40fac72081950f9730205b87abc6087552 AS builder

WORKDIR /usr/src/app

# Resolve and install project + dev dependencies into .venv
RUN --mount=type=bind,from=uv-tools-trixie,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --link-mode copy --group dev --frozen --no-install-project

# Lint, test and build using the synced environment
RUN --mount=type=bind,from=uv-tools-trixie,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=target=src/cf_ips_to_hcloud_fw,source=/src/cf_ips_to_hcloud_fw \
    --mount=target=tests,source=/tests \
    --mount=target=LICENSE,source=/LICENSE \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=target=README.md,source=/README.md \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv <<EOF
    set -eux
    uv sync --link-mode copy --group dev --frozen
    uv run --no-sync ruff check --output-format=github
    uv run --no-sync ruff format --check --output-format=github
    uv run --no-sync ty check --output-format=github
    uv run --no-sync pytest
    uv build
EOF


FROM docker.io/library/python:3.14.7-alpine3.24@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc AS final-image

WORKDIR /usr/src/app

ENV PYTHONFAULTHANDLER=1 PYTHONDONTWRITEBYTECODE=1

# Drop the base image's bundled pip: uv creates .venv without pip and the app
# runs from .venv/bin, so nothing here imports it. pip ≥26.2 ships a CycloneDX
# SBOM of its vendored libraries (pip/_vendor/bom.cdx.json), which makes
# scanners report CVEs against vendored setuptools/msgpack that are never used.
RUN rm -rf /usr/local/lib/python3.*/site-packages/pip \
           /usr/local/lib/python3.*/site-packages/pip-*.dist-info \
           /usr/local/bin/pip*

# The official python image is rebuilt only on CPython and Alpine point
# releases, while Alpine's security repo moves between them. Pull in whatever
# package updates the repo has so a fixed CVE in the base (openssl, musl,
# busybox, ...) never waits for the next upstream rebuild. This is the one
# build input that isn't digest-pinned; apk still verifies every package
# against the Alpine signing keys shipped in the base image.
RUN apk upgrade --no-cache

# Resolve and install dependencies
RUN --mount=type=bind,from=uv-tools-alpine,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --link-mode copy --frozen --no-group dev --no-install-project

# Install wheel without dependencies
#
# uv pip install writes a uv_cache.json into the installed dist-info holding a
# wall-clock install timestamp (and otherwise only nulls and empty objects). It
# has no runtime purpose, and it was the single thing keeping this image from
# being byte-identical across rebuilds under SOURCE_DATE_EPOCH — every other
# file in every layer already matches. Drop it, and its RECORD line with it, so
# RECORD doesn't reference a file that isn't there. Only the project's own
# dist-info is touched; uv sync's packages never get one.
RUN --mount=type=bind,from=uv-tools-alpine,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=from=builder,target=/dist,source=/usr/src/app/dist \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv <<EOF
    set -eux
    uv pip install --link-mode copy --no-compile --force-reinstall --no-deps /dist/*.whl
    rm -f .venv/lib/python*/site-packages/cf_ips_to_hcloud_fw-*.dist-info/uv_cache.json
    sed -i '/\.dist-info\/uv_cache\.json,/d' \
        .venv/lib/python*/site-packages/cf_ips_to_hcloud_fw-*.dist-info/RECORD
EOF

USER 65534

# Smoke test: confirm the installed entry point runs in the final image before
# it is pushed, signed, and scanned. Runs per-arch during the buildx build.
RUN [".venv/bin/cf-ips-to-hcloud-fw", "--version"]

# No -c: the tool auto-detects ./config.yaml (mount it at /usr/src/app/config.yaml)
# and otherwise falls back to the HCLOUD_TOKEN / HCLOUD_FIREWALLS env vars.
CMD [".venv/bin/cf-ips-to-hcloud-fw"]

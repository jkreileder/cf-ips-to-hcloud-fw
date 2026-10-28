# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# check=experimental=all;error=true

FROM --platform=$BUILDPLATFORM docker.io/astral/uv:0.13.6-python3.15-trixie@sha256:f68dfb3eaf23a53afb5f74833bdacc0ce586d69f8063c48f9f3ebbe42e048e4a AS uv-tools-trixie
FROM docker.io/astral/uv:0.13.6-python3.15-alpine3.23@sha256:4de1eb2baffd7a44903a53b6cb112b2538232d56287bc37d18b66ae1f17108d4 AS uv-tools-alpine

FROM --platform=$BUILDPLATFORM docker.io/library/python:3.15.2-trixie@sha256:f680543cfd66b886345db09093f751bcf7efa3707380d59fa3630edce5ad0aa4 AS builder

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


FROM docker.io/library/python:3.15.2-alpine3.24@sha256:1656b7eaf309cadf99069ea9de335c7f67a8355789cfc6f1835a05818996f081 AS final-image

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

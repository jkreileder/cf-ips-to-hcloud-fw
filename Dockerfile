# syntax=docker/dockerfile:1.26.0@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32
# check=experimental=all;error=true

FROM --platform=$BUILDPLATFORM docker.io/astral/uv:0.12.0-python3.14-trixie@sha256:31a52487b980ba38c38ee1d1eb21f416f974978794ad834af493aa734926bb94 AS uv-tools-trixie
FROM docker.io/astral/uv:0.12.0-python3.14-alpine3.23@sha256:9c2e8c54545d6402b1b6995e6bfb3969afccf9f2380b1d5d0cec0756e8aec1a3 AS uv-tools-alpine

FROM --platform=$BUILDPLATFORM public.ecr.aws/docker/library/python:3.14.6-trixie@sha256:55dd7c1ea6c2b2c45a26d797187706eb9e5e0046f8e54fd759e38647b505c36b AS builder

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


FROM public.ecr.aws/docker/library/python:3.14.6-alpine3.24@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92 AS final-image

WORKDIR /usr/src/app

ENV PYTHONFAULTHANDLER=1 PYTHONDONTWRITEBYTECODE=1

# Resolve and install dependencies
RUN --mount=type=bind,from=uv-tools-alpine,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --link-mode copy --frozen --no-group dev --no-install-project

# Install wheel without dependencies
RUN --mount=type=bind,from=uv-tools-alpine,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=from=builder,target=/dist,source=/usr/src/app/dist \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv pip install --link-mode copy --no-compile --force-reinstall --no-deps /dist/*.whl

USER 65534

# Smoke test: confirm the installed entry point runs in the final image before
# it is pushed, signed, and scanned. Runs per-arch during the buildx build.
RUN [".venv/bin/cf-ips-to-hcloud-fw", "--version"]

# No -c: the tool auto-detects ./config.yaml (mount it at /usr/src/app/config.yaml)
# and otherwise falls back to the HCLOUD_TOKEN / HCLOUD_FIREWALLS env vars.
CMD [".venv/bin/cf-ips-to-hcloud-fw"]

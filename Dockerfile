# syntax=docker/dockerfile:1.20.0@sha256:91d8edf78868ed98df4d6aad9581e63696d72b1c05a821959e5824a0432c5120
# check=experimental=all;error=true

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.9.21-trixie@sha256:cbdbeec637cae43ab273f178d8b87c609b360caf65ee29c54a71b1f14d4c7bd3 AS uv-tools-trixie
FROM ghcr.io/astral-sh/uv:0.9.21-alpine3.22@sha256:63a6b7a42a23d1a7bcbf6974d5e36c09f4f6d3589dcf809b357ac5d2f362d3d7 AS uv-tools-alpine

FROM --platform=$BUILDPLATFORM public.ecr.aws/docker/library/python:3.14.2-trixie@sha256:dadbe13e4d921ffd7f10dfe21c4b5bd18f7d322740309f42a8b7a22480f3bdff AS builder

WORKDIR /usr/src/app

# Resolve and install project + dev dependencies into .venv
RUN --mount=type=bind,from=uv-tools-trixie,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    --mount=type=cache,id=npm,target=/root/.npm <<EOF
    set -eux
    uv sync --link-mode copy --group dev --frozen --no-install-project
    uv run --no-project pyright --version
EOF

# Lint, test and build using the synced environment
RUN --mount=type=bind,from=uv-tools-trixie,source=/usr/local/bin/uv,target=/usr/local/bin/uv \
    --mount=target=src/cf_ips_to_hcloud_fw,source=/src/cf_ips_to_hcloud_fw \
    --mount=target=tests,source=/tests \
    --mount=target=LICENSE,source=/LICENSE \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=target=README.md,source=/README.md \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    --mount=type=cache,id=npm,target=/root/.npm <<EOF
    set -eux
    uv sync --link-mode copy --group dev --frozen
    uv run --no-sync ruff check --output-format=github
    uv run --no-sync ty check
    uv run --no-sync pyright
    uv run --no-sync pytest
    uv build
EOF


FROM public.ecr.aws/docker/library/python:3.14.2-alpine3.22@sha256:91859223a313a4407c239afb3a8e68bddc3dbfb0d24ddc5bdeb029136b55b150 AS final-image

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

CMD [".venv/bin/cf-ips-to-hcloud-fw", "-c", "config.yaml"]

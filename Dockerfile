# syntax=docker/dockerfile:1.20.0@sha256:91d8edf78868ed98df4d6aad9581e63696d72b1c05a821959e5824a0432c5120
# check=experimental=all;error=true

FROM ghcr.io/astral-sh/uv:0.9.9@sha256:f6e3549ed287fee0ddde2460a2a74a2d74366f84b04aaa34c1f19fec40da8652 AS uv-tools

FROM --platform=$BUILDPLATFORM python:3.14.0-trixie@sha256:efde2ffbe55ff8120ef87129f0b880471eccd9581882fbaa40b9f98ea2ebb5f2 AS builder

WORKDIR /usr/src/app

# Resolve and install project + dev dependencies into .venv
RUN --mount=type=bind,from=uv-tools,source=/uv,target=/usr/bin/uv \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    --mount=type=cache,id=npm,target=/root/.npm <<EOF
    set -eux
    uv sync --group dev --frozen --no-install-project
    uv run --no-project pyright --version
EOF

# Lint, test and build using the synced environment
RUN --mount=type=bind,from=uv-tools,source=/uv,target=/usr/bin/uv \
    --mount=target=src/cf_ips_to_hcloud_fw,source=/src/cf_ips_to_hcloud_fw \
    --mount=target=tests,source=/tests \
    --mount=target=LICENSE,source=/LICENSE \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=target=README.md,source=/README.md \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    --mount=type=cache,id=npm,target=/root/.npm <<EOF
    set -eux
    uv sync --group dev --frozen
    uv run --no-sync ruff check --output-format=github
    uv run --no-sync pyright --venvpath .
    uv run --no-sync pytest
    uv build
EOF


FROM python:3.14.0-alpine3.22@sha256:8373231e1e906ddfb457748bfc032c4c06ada8c759b7b62d9c73ec2a3c56e710 AS final-image

WORKDIR /usr/src/app

ENV PYTHONFAULTHANDLER=1 PYTHONDONTWRITEBYTECODE=1

# Remove unneeded gdbm dependency with GPL-3.0 license
RUN apk add --no-network --virtual .python-rundeps $(apk info --no-network -qR .python-rundeps | grep -v gdbm)

# Resolve and install dependencies
RUN --mount=type=bind,from=uv-tools,source=/uv,target=/usr/bin/uv \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=uv.lock,source=/uv.lock \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Install wheel without dependencies
RUN --mount=type=bind,from=uv-tools,source=/uv,target=/usr/bin/uv \
    --mount=from=builder,target=/dist,source=/usr/src/app/dist \
    --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv pip install --no-compile --force-reinstall --no-deps /dist/*.whl

USER 65534

CMD [".venv/bin/cf-ips-to-hcloud-fw", "-c", "config.yaml"]

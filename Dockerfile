# syntax=docker/dockerfile:1.24.0@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# check=experimental=all;error=true

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.19-python3.14-trixie@sha256:b5a5d154dba528e849e69e0fc47f0a3ee7373843bb117d84790952100b561a02 AS uv-tools-trixie
FROM ghcr.io/astral-sh/uv:0.11.19-python3.14-alpine3.23@sha256:1054a8c47beacaea07c0bbdb073e6b80a26deeb36c270593bb92c75a653d71d5 AS uv-tools-alpine

FROM --platform=$BUILDPLATFORM public.ecr.aws/docker/library/python:3.14.5-trixie@sha256:11591407222400cafc1b2bd03fe09a90988f091fc9ddff4a901f80ceb02b78b3 AS builder

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
    uv run --no-sync ty check
    uv run --no-sync pytest
    uv build
EOF


FROM public.ecr.aws/docker/library/python:3.14.5-alpine3.23@sha256:5a824eb82cc75361f98611f3cfc5091ea33f10a6ccea4d4ebdabbc523b9a1614 AS final-image

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

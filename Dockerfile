# syntax=docker/dockerfile:1.20.0@sha256:91d8edf78868ed98df4d6aad9581e63696d72b1c05a821959e5824a0432c5120
# check=experimental=all;error=true

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.9.11-trixie@sha256:a87efc5390eaa786ad0fc36140ec833bfbc0e3abb3eb96aaa1f8e38934526055 AS uv-tools-trixie
FROM ghcr.io/astral-sh/uv:0.9.11-alpine3.22@sha256:76052b2a90519ffaa815dc3d39d35b31e87b20b87e18bcd8c7bb3577939defdd AS uv-tools-alpine

FROM --platform=$BUILDPLATFORM public.ecr.aws/docker/library/python:3.14.0-trixie@sha256:3fd62bea517655424fb4a781e74233c6386d51ba790d5e2ecf843f892c693303 AS builder

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
    uv run --no-sync pyright --venvpath .
    uv run --no-sync pytest
    uv build
EOF


FROM public.ecr.aws/docker/library/python:3.14.0-alpine3.22@sha256:8373231e1e906ddfb457748bfc032c4c06ada8c759b7b62d9c73ec2a3c56e710 AS final-image

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
    uv pip install --no-compile --force-reinstall --no-deps /dist/*.whl

USER 65534

CMD [".venv/bin/cf-ips-to-hcloud-fw", "-c", "config.yaml"]

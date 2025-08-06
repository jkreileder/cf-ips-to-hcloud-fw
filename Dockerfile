# syntax=docker/dockerfile:1.17.0@sha256:e63addfe27b10e394a5f9f1e866961adc70d08573f1cb80f8d1a0999347b3553
# check=experimental=all;error=true

FROM --platform=$BUILDPLATFORM python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419 AS builder

WORKDIR /usr/src/app

# Install dependencies and force pyright to install node
RUN --mount=target=requirements.txt,source=/requirements.txt  \
    --mount=target=requirements-dev.txt,source=/requirements-dev.txt \
    --mount=type=cache,id=npm,target=/root/.npm \
    --mount=type=cache,id=pip,target=/root/.cache/pip <<EOF
    set -ex
    pip3 install --disable-pip-version-check --require-hashes -r requirements-dev.txt
    pip3 install --disable-pip-version-check --require-hashes -r requirements.txt
    pyright --version
    pip-compile --allow-unsafe --no-strip-extras --output-file=requirements-dev-pep508.txt --quiet requirements-dev.txt
    pip-compile --allow-unsafe --no-strip-extras --output-file=requirements-pep508.txt --quiet requirements.txt
EOF

# Lint, test and build
RUN --mount=target=src/cf_ips_to_hcloud_fw,source=/src/cf_ips_to_hcloud_fw \
    --mount=target=tests,source=/tests \
    --mount=target=LICENSE,source=/LICENSE \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=README.md,source=/README.md \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    --mount=type=cache,id=npm,target=/root/.npm <<EOF
    set -ex
    ruff check --output-format=github
    pyright
    pytest
    python3 -m build
EOF


FROM python:3.13.5-alpine3.22@sha256:37b14db89f587f9eaa890e4a442a3fe55db452b69cca1403cc730bd0fbdc8aaf AS final-image

WORKDIR /usr/src/app

ENV PYTHONFAULTHANDLER=1 PYTHONDONTWRITEBYTECODE=1

# Remove unneeded gdbm dependency with GPL-3.0 license
RUN apk add --no-network --virtual .python-rundeps $(apk info --no-network -qR .python-rundeps | grep -v gdbm)

# Install dependencies directly with hashes
RUN --mount=target=requirements.txt,source=/requirements.txt  \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip3 install --disable-pip-version-check --no-compile --require-hashes -r requirements.txt

# Install wheel without dependencies
RUN --mount=from=builder,target=/dist,source=/usr/src/app/dist \
    pip3 install --disable-pip-version-check --no-compile --force-reinstall --no-deps /dist/*.whl

USER 65534

CMD ["cf-ips-to-hcloud-fw", "-c", "config.yaml"]

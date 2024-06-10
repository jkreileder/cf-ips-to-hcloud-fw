# syntax = docker/dockerfile:1.7.1@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

FROM --platform=$BUILDPLATFORM python:3.12.4-slim-bookworm@sha256:e3ae8cf03c4f0abbfef13a8147478a7cd92798a94fa729a36a185d9106cbae32 AS builder

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


FROM python:3.12.4-alpine3.20@sha256:d24ed567ee3b972478a232ceff84b0d002e18ee9f5d38234ecbffece23dfa084 AS final-image

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

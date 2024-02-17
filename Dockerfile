# syntax = docker/dockerfile:1.6.0@sha256:ac85f380a63b13dfcefa89046420e1781752bab202122f8f50032edf31be0021

FROM --platform=$BUILDPLATFORM python:3.12.2-slim-bookworm@sha256:86cd49938a9b50c3663aa93cf5db9c8f498d6fe47f463a2cb967248b9e7d69de AS builder

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


FROM python:3.12.2-alpine3.19@sha256:1a0501213b470de000d8432b3caab9d8de5489e9443c2cc7ccaa6b0aa5c3148e AS final-image

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

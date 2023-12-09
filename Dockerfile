# syntax = docker/dockerfile:1

ARG PY_VERSION=3.12


FROM --platform=$BUILDPLATFORM python:$PY_VERSION-slim AS builder

WORKDIR /usr/src/app

RUN --mount=target=requirements-dev.txt,source=/requirements-dev.txt \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip3 install -r requirements-dev.txt

RUN --mount=target=requirements.txt,source=/requirements.txt \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip3 install -r requirements.txt

RUN --mount=target=cf_ips_to_hcloud_fw,source=/cf_ips_to_hcloud_fw \
    --mount=target=LICENSE,source=/LICENSE \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=README.md,source=/README.md \
    --mount=target=requirements-dev.txt,source=/requirements-dev.txt \
    --mount=target=requirements.txt,source=/requirements.txt \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    ruff check . && pyright && python3 -m build


FROM python:$PY_VERSION-alpine as final-image

WORKDIR /usr/src/app

RUN --mount=from=builder,target=/dist,source=/usr/src/app/dist \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip3 install -f /dist cf-ips-to-hcloud-fw

USER 65534

CMD ["cf-ips-to-hcloud-fw", "-c", "config.yaml"]

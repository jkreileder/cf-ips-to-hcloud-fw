# syntax = docker/dockerfile:1.6.0

ARG BUILDKIT_SBOM_SCAN_CONTEXT=true


FROM --platform=$BUILDPLATFORM python:3.12.1-slim-bookworm AS builder
ARG BUILDKIT_SBOM_SCAN_STAGE=true

WORKDIR /usr/src/app

RUN --mount=target=requirements-dev.txt,source=/requirements-dev.txt \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip3 install --disable-pip-version-check -r requirements-dev.txt

RUN --mount=target=requirements.txt,source=/requirements.txt \
    --mount=type=cache,id=npm,target=/root/.npm \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip3 install --disable-pip-version-check -r requirements.txt && pyright --version # force pyright to install node

RUN --mount=target=cf_ips_to_hcloud_fw,source=/cf_ips_to_hcloud_fw \
    --mount=target=tests,source=/tests \
    --mount=target=LICENSE,source=/LICENSE \
    --mount=target=pyproject.toml,source=/pyproject.toml \
    --mount=target=README.md,source=/README.md \
    --mount=target=requirements-dev.txt,source=/requirements-dev.txt \
    --mount=target=requirements.txt,source=/requirements.txt \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    --mount=type=cache,id=npm,target=/root/.npm \
    ruff check . && pyright && pytest && python3 -m build


FROM python:3.12.1-alpine3.19 AS final-image

WORKDIR /usr/src/app

RUN --mount=from=builder,target=/dist,source=/usr/src/app/dist \
    --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip3 install --disable-pip-version-check --force-reinstall /dist/*.whl

USER 65534

CMD ["cf-ips-to-hcloud-fw", "-c", "config.yaml"]

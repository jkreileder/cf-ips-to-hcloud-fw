# Update Hetzner Cloud Firewall Rules with Current Cloudflare IP Ranges  <!-- omit in toc -->

[![codecov](https://codecov.io/gh/jkreileder/cf-ips-to-hcloud-fw/graph/badge.svg?token=PCP1F2XWAT)](https://codecov.io/gh/jkreileder/cf-ips-to-hcloud-fw)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/8275/badge)](https://www.bestpractices.dev/projects/8275)
[![CodeQL](https://github.com/jkreileder/cf-ips-to-hcloud-fw/actions/workflows/codeql.yaml/badge.svg)](https://github.com/jkreileder/cf-ips-to-hcloud-fw/actions/workflows/codeql.yaml)
[![Python package](https://github.com/jkreileder/cf-ips-to-hcloud-fw/actions/workflows/python-package.yaml/badge.svg)](https://github.com/jkreileder/cf-ips-to-hcloud-fw/actions/workflows/python-package.yaml)
[![Docker build](https://github.com/jkreileder/cf-ips-to-hcloud-fw/actions/workflows/docker.yaml/badge.svg)](https://github.com/jkreileder/cf-ips-to-hcloud-fw/actions/workflows/docker.yaml)
[![PyPI - Version](https://img.shields.io/pypi/v/cf-ips-to-hcloud-fw)](https://pypi.org/project/cf-ips-to-hcloud-fw/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cf-ips-to-hcloud-fw?logo=python)](https://pypi.org/project/cf-ips-to-hcloud-fw/)

This tool, `cf-ips-to-hcloud-fw`, helps you keep your Hetzner Cloud firewall
rules up-to-date with the current Cloudflare IP ranges.

## Table of Contents <!-- omit in toc -->

- [Overview](#overview)
- [Installation](#installation)
  - [Using Python](#using-python)
    - [Using pipx (Recommended)](#using-pipx-recommended)
    - [Using pip](#using-pip)
  - [Docker and Kubernetes](#docker-and-kubernetes)
- [Configuration](#configuration)
  - [Preparing the Hetzner Cloud Firewall](#preparing-the-hetzner-cloud-firewall)
  - [Configuring the Application](#configuring-the-application)

## Overview

`cf-ips-to-hcloud-fw` fetches the current [Cloudflare IP
ranges](https://www.cloudflare.com/ips/) and updates your Hetzner Cloud firewall
rules using the [hcloud
API](https://docs.hetzner.cloud/#firewall-actions-set-rules).

The tool specifically targets **incoming** firewall rules and **replaces** the
networks with Cloudflare networks if their description contains
`__CLOUDFLARE_IPS_V4__`, `__CLOUDFLARE_IPS_V6__` or `__CLOUDFLARE_IPS__`.

| Text in rule description | Cloudflare IP ranges |
| ------------------------ | -------------------- |
| `__CLOUDFLARE_IPS_V4__`  | IPv4 only            |
| `__CLOUDFLARE_IPS_V6__`  | IPv6 only            |
| `__CLOUDFLARE_IPS__`     | IPv4 + IPv6          |

Note: Having both `__CLOUDFLARE_IPS_V4__` and `__CLOUDFLARE_IPS_V6__` in a rule
description is equivalent to having `__CLOUDFLARE_IPS__` there.

## Installation

### Using Python

To install `cf-ips-to-hcloud-fw` using Python, we recommend using
[`pipx`](https://pipx.pypa.io/).  `pipx` is a tool for installing and running
Python applications in isolated environments.

#### Using pipx (Recommended)

1. Install `cf-ips-to-hcloud-fw` using pipx:

    ```shell
    pipx install cf-ips-to-hcloud-fw
    ```

2. Verify the installation:

    ```shell
    cf-ips-to-hcloud-fw -h
    ```

You should see the usage information for `cf-ips-to-hcloud-fw`.

To upgrade `cf-ips-to-hcloud-fw`, run:

> [!TIP]
> To upgrade `cf-ips-to-hcloud-fw`, run `pipx upgrade cf-ips-to-hcloud-fw`.

#### Using pip

We strongly recommend using a virtual environment when installing Python
packages with pip. This helps to avoid conflicts between packages and allows you
to manage packages on a per-project basis.

1. Create a virtual environment:

    ```shell
    python3 -m venv cf-ips-to-hcloud-fw-venv
    ```

2. Install `cf-ips-to-hcloud-fw` into the virtual environment:

    ```shell
    ./cf-ips-to-hcloud-fw-venv/bin/pip3 install cf-ips-to-hcloud-fw
    ```

3. Verify the installation:

    ```shell
    ./cf-ips-to-hcloud-fw-venv/bin/cf-ips-to-hcloud-fw -h
    ```

You should see the usage information for `cf-ips-to-hcloud-fw`.

> [!TIP]
> To upgrade `cf-ips-to-hcloud-fw` in your virtual environment, run
> `./cf-ips-to-hcloud-fw-venv/bin/pip3 install --upgrade cf-ips-to-hcloud-fw`.

### Docker and Kubernetes

As an alternative, `cf-ips-to-hcloud-fw` can be run using Docker or a Kubernetes
CronJob.  Simply mount your configuration file as `/usr/src/app/config.yaml`.

Here's an example using Docker:

```shell
docker run --rm \
  --mount type=bind,source=$(pwd)/config.yaml,target=/usr/src/app/config.yaml,readonly \
  jkreileder/cf-ips-to-hcloud-fw:1.0.8
```

(Add `--pull=always` if you use a rolling image tag.)

Docker images for `cf-ips-to-hcloud-fw` are available for both `linux/amd64` and
`linux/arm64` architectures.  The Docker images support the following tags:

- `1`: This tag always points to the latest `1.x.x` release.
- `1.0`: This tag always points to the latest `1.0.x` release.
- `1.0.8`: This tag points to the specific `1.0.8` release.
- `main`: This tag points to the most recent development version of
  `cf-ips-to-hcloud-fw`. Use this at your own risk as it may contain unstable
  changes.

You can find the Docker images at:

- [Docker Hub](https://hub.docker.com/r/jkreileder/cf-ips-to-hcloud-fw)
- [Quay.io](https://quay.io/repository/jkreileder/cf-ips-to-hcloud-fw)
- [GitHub Packages](https://github.com/jkreileder/cf-ips-to-hcloud-fw/pkgs/container/cf-ips-to-hcloud-fw)

Here's an example of how to create a Kubernetes Secret for your
[configuration](#configuration):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: cf-ips-to-hcloud-fw-config
type: Opaque
stringData:
  config.yaml: |
    - token: API_TOKEN_FOR_PROJECT_1
      firewalls:
        - firewall-1
        - firewall-2
    - token: API_TOKEN_FOR_PROJECT_2
      firewalls:
        - default
```

And here's an example of a Kubernetes CronJob that uses the Secret:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cf-ips-to-hcloud-fw
spec:
  schedule: "0 * * * *" # Run every hour
  jobTemplate:
    spec:
      template:
        spec:
          securityContext:
            runAsNonRoot: true
            runAsUser: 65534
          containers:
            - name: cf-ips-to-hcloud-fw
              image: jkreileder/cf-ips-to-hcloud-fw:1.0.8
              # imagePullPolicy: Always # Uncomment this if you use a rolling image tag
              securityContext:
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop:
                    - ALL
              volumeMounts:
                - name: config-volume
                  mountPath: /usr/src/app/config.yaml
                  subPath: config.yaml
          volumes:
            - name: config-volume
              secret:
                secretName: cf-ips-to-hcloud-fw-config
          restartPolicy: OnFailure
```

## Configuration

### Preparing the Hetzner Cloud Firewall

To prepare your Hetzner Cloud Firewall:

1. **Set the rule descriptions**: Include `__CLOUDFLARE_IPS_V4__`,
   `__CLOUDFLARE_IPS_V6__`, or `__CLOUDFLARE_IPS__` in the description of any
   incoming firewall rule where you want to insert Cloudflare networks. This
   will be used as a marker to identify which rules should be updated with the
   Cloudflare IP ranges.

2. **Generate an API token**: You'll need an API token with write permissions
   for the project that contains the firewall. This token will be used to
   authenticate your requests to the Hetzner Cloud API. You can generate a token
   in the Hetzner Cloud Console by going to "Security" > "API Tokens" >
   "Generate API Token".

### Configuring the Application

To configure the application, you'll need to create a `config.yaml` file with
your API tokens and the names of the firewalls you want to update:

```yaml
- token: API_TOKEN_FOR_PROJECT_1 # Token with read-write permissions for a Hetzner Cloud project
  firewalls:
    - firewall-1
    - firewall-2
- token: API_TOKEN_FOR_PROJECT_2 # Token with read-write permissions for another Hetzner Cloud project
  firewalls:
    - default
```

# Update Hetzner Cloud Firewall Rules with Current Cloudflare IP Ranges  <!-- omit in toc -->

This tool, `cf-ips-to-hcloud-fw`, helps you keep your Hetzner Cloud firewall
rules up-to-date with the current Cloudflare IP ranges.

## Table of Contents <!-- omit in toc -->

- [Overview](#overview)
- [Installation](#installation)
  - [Using Python](#using-python)
  - [Docker and Kubernetes](#docker-and-kubernetes)
- [Configuration](#configuration)
  - [Preparing the Hetzner Cloud Firewall](#preparing-the-hetzner-cloud-firewall)
  - [Configuring the Application](#configuring-the-application)

## Overview

`cf-ips-to-hcloud-fw` fetches the current
[Cloudflare IP ranges](https://www.cloudflare.com/ips/) and updates your
Hetzner Cloud firewall rules using the
[hcloud API](https://docs.hetzner.cloud/#firewall-actions-set-rules).

The tool specifically targets **incoming** firewall rules and **replaces**
the networks with Cloudflare networks if their description contains
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

To install `cf-ips-to-hcloud-fw` using Python, follow these steps:

1. Create a virtual environment:

    ```shell
    python3 -m venv cf-ips-to-hcloud-fw-venv
    ```

2. Install cf-ips-to-hcloud-fw into the virtual environment:

    ```shell
    ./cf-ips-to-hcloud-fw-venv/bin/pip3 install cf-ips-to-hcloud-fw
    ```

3. Verify the installation:

    ```shell
    ./cf-ips-to-hcloud-fw-venv/bin/cf-ips-to-hcloud-fw -h
    ```

You should see the usage information for cf-ips-to-hcloud-fw.

### Docker and Kubernetes

As an alternative, `cf-ips-to-hcloud-fw` can be run using Docker or a
Kubernetes CronJob. Simply mount your configuration file as
`/usr/src/app/config.yaml`. Here's an example using Docker:

```shell
docker run --rm \
  --mount type=bind,source="$(pwd)"/config.yaml,target=/usr/src/app/config.yaml,readonly \
  jkreileder/cf-ips-to-hcloud-fw:1.0
```

You can find the Docker images at:

- [Docker Hub](https://hub.docker.com/r/jkreileder/cf-ips-to-hcloud-fw)
- [Quay.io](https://quay.io/repository/jkreileder/cf-ips-to-hcloud-fw)
- [GitHub Packages](https://github.com/jkreileder/cf-ips-to-hcloud-fw/pkgs/container/cf-ips-to-hcloud-fw)

## Configuration

### Preparing the Hetzner Cloud Firewall

To prepare your Hetzner Cloud Firewall:

- Include `__CLOUDFLARE_IPS_V4__`, `__CLOUDFLARE_IPS_V6__`, or
  `__CLOUDFLARE_IPS__` in the description of any incoming firewall rule where
  you want to insert Cloudflare networks.
- Generate an API token with write permissions for the project that contains
  the firewall.

### Configuring the Application

To configure the application, add your tokens and the names of any firewalls
you want to update to `config.yaml`:

```yaml
- token: cHJvamVjdGF0b2tlbgAd43 # token for project a
  firewalls:
    - firewall-1
    - firewall-2
- token: cHJvamVjdGJ0b2tlbgDas3 # token for project b
  firewalls:
    - default
```

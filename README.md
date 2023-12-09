# Update Hetzner Cloud Firewall Rules with Current Cloudflare IP Ranges  <!-- omit from toc -->

## Table of Contents <!-- omit from toc -->

- [Overview](#overview)
- [Installation](#installation)
  - [Using Python](#using-python)
  - [Docker and Kubernetes](#docker-and-kubernetes)
- [Configuration](#configuration)
  - [Hetzner Cloud Firewall Preparation](#hetzner-cloud-firewall-preparation)
  - [Configuration File](#configuration-file)

## Overview

`cf-ips-to-hcloud-fw` fetches the current
[Cloudflare IP ranges](https://www.cloudflare.com/ips/) and inserts them into
Hetzner Cloud firewall rules via the
[hcloud API](https://docs.hetzner.cloud/#firewall-actions-set-rules).

The networks in **incoming** firewall rules are **replaced** with
Cloudflare networks if their description contains `__CLOUDFLARE_IPS_V4__`,
`__CLOUDFLARE_IPS_V6__` or `__CLOUDFLARE_IPS__`.

| Text in rule description | Cloudflare networks |
| ------------------------ | ------------------- |
| `__CLOUDFLARE_IPS_V4__`  | IPv4 only           |
| `__CLOUDFLARE_IPS_V6__`  | IPv6 only           |
| `__CLOUDFLARE_IPS__`     | IPv4 + IPv6         |

Having both `__CLOUDFLARE_IPS_V4__` and `__CLOUDFLARE_IPS_V6__` in a rule
description is equivalent to having `__CLOUDFLARE_IPS__` there.

## Installation

### Using Python

Install [`cf-ips-to-hcloud-fw`](https://pypi.org/project/cf-ips-to-hcloud-fw/)
into a virtual environement:

```shell session
$ python3 -m venv cf-ips-to-hcloud-fw-venv
$ ./cf-ips-to-hcloud-fw-venv/bin/pip3 install cf-ips-to-hcloud-fw
[...]
$ ./cf-ips-to-hcloud-fw-venv/bin/cf-ips-to-hcloud-fw -h
usage: cf-ips-to-hcloud-fw [-h] -c CONFIGFILE [-v] [-d]

Update Hetzner Cloud firewall rules with Cloudflare IP ranges

options:
  -h, --help            show this help message and exit
  -c CONFIGFILE, --config CONFIGFILE
                        config file
  -v, --version         show program's version number and exit
  -d, --debug
```

Then call `cf-ips-to-hcloud-fw-venv/bin/cf-ips-to-hcloud-fw -c config.yaml`
from a cronjob or a systemd timer.

### Docker and Kubernetes

Alternatively you can use Docker or a Kubernetes CronJob to run
`cf-ips-to-hcloud-fw`.  Just mount your config file as
`/usr/src/app/config.yaml`.  For example:

```bash
docker run --rm \
  --mount type=bind,source="$(pwd)"/config.yaml,target=/usr/src/app/config.yaml,readonly \
  jkreileder/cf-ips-to-hcloud-fw:1
```

Images are available on:

- [Docker registry](https://hub.docker.com/r/jkreileder/cf-ips-to-hcloud-fw)
- [Quay container regsitry](https://quay.io/repository/jkreileder/cf-ips-to-hcloud-fw)
- [GitHub container regsitry](https://github.com/jkreileder/cf-ips-to-hcloud-fw/pkgs/container/cf-ips-to-hcloud-fw)

## Configuration

### Hetzner Cloud Firewall Preparation

- Insert `__CLOUDFLARE_IPS_V4__`, `__CLOUDFLARE_IPS_V6__` or
  `__CLOUDFLARE_IPS__` into the description of any incoming firewall rule
  where you want to have Cloudflare networks inserted
- Create an API token with write permissions for the project containing
  the firewall

### Configuration File

Insert the tokens and names of any firewall you want to update in
`config.yaml`:

```yaml
- token: cHJvamVjdGF0b2tlbgAd43 # token for project a
  firewalls:
    - firewall-1
    - firewall-2
- token: cHJvamVjdGJ0b2tlbgDas3 # token for project b
  firewalls:
    - default
```

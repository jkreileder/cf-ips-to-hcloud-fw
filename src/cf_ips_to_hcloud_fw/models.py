from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network

from pydantic import BaseModel, SecretStr


class CloudflareIPNetworks(BaseModel):
    ipv4_cidrs: list[IPv4Network]
    ipv6_cidrs: list[IPv6Network]


class CloudflareCIDRs(BaseModel):
    ipv4_cidrs: list[str]
    ipv6_cidrs: list[str]


class Project(BaseModel):
    token: SecretStr
    firewalls: list[str]

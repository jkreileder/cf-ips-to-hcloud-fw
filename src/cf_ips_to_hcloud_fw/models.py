from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CloudflareIPNetworks(BaseModel):
    ipv4_cidrs: list[IPv4Network]
    ipv6_cidrs: list[IPv6Network]


class CloudflareCIDRs(BaseModel):
    ipv4_cidrs: list[str]
    ipv6_cidrs: list[str]


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: SecretStr
    firewalls: list[str] = Field(min_length=1)

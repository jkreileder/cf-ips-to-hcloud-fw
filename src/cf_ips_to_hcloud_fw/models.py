"""Pydantic models for Cloudflare CIDR payloads and project configuration."""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CloudflareIPNetworks(BaseModel):
    """Cloudflare CIDRs parsed as IP network objects, used to validate input."""

    ipv4_cidrs: list[IPv4Network]
    ipv6_cidrs: list[IPv6Network]


class CloudflareCIDRs(BaseModel):
    """Cloudflare CIDRs kept as strings for writing to firewall rules."""

    ipv4_cidrs: list[str]
    ipv6_cidrs: list[str]


class Project(BaseModel):
    """A Hetzner Cloud API token paired with the firewalls it should update."""

    model_config = ConfigDict(extra="forbid")

    token: SecretStr
    firewalls: list[str] = Field(min_length=1)

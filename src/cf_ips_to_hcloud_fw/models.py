"""Pydantic models for Cloudflare CIDR payloads and project configuration."""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr

_Network = TypeVar("_Network", IPv4Network, IPv6Network)


def _require_globally_routable(network: _Network) -> _Network:
    """Reject CIDRs that must never end up in a Cloudflare-only allow rule.

    Parsing only proves a CIDR is well-formed, so a tampered or malfunctioning
    API response could hand us a range that is syntactically fine and
    semantically catastrophic: ``0.0.0.0/0`` passes every structural check and
    would open every marked firewall rule to the whole internet. Cloudflare
    only ever publishes globally routable unicast space - the live list bottoms
    out at /13 for IPv4 and /29 for IPv6 - so anything else is a broken payload
    rather than a range worth syncing.

    Deliberately no minimum prefix length: a floor tight enough to be useful
    would hard-fail the run if Cloudflare ever published a broader aggregate,
    turning a hypothetical tampering risk into a real outage with stale rules.
    ``is_reserved`` is left out for the same reason - for IPv6 it means "outside
    IANA-allocated space", so an allocation newer than the running Python's
    tables would be refused, and unallocated space is not routable to an
    attacker anyway.

    Args:
        network: A parsed CIDR from the Cloudflare response.

    Returns:
        The network unchanged, when it is globally routable.

    Raises:
        ValueError: If the network is a default route or non-global space.
    """
    # A default route needs its own test: `IPv4Network("0.0.0.0/0").is_private`
    # is False, so the flag checks below do not catch it.
    if network.prefixlen == 0:
        msg = f"{network} is a default route"
        raise ValueError(msg)

    disallowed = [
        name
        for name, matches in (
            ("unspecified", network.is_unspecified),
            ("loopback", network.is_loopback),
            ("link-local", network.is_link_local),
            ("multicast", network.is_multicast),
            ("private", network.is_private),
        )
        if matches
    ]
    if disallowed:
        msg = f"{network} is not globally routable ({', '.join(disallowed)})"
        raise ValueError(msg)

    return network


GloballyRoutableIPv4Network = Annotated[
    IPv4Network, AfterValidator(_require_globally_routable)
]
GloballyRoutableIPv6Network = Annotated[
    IPv6Network, AfterValidator(_require_globally_routable)
]


class CloudflareIPNetworks(BaseModel):
    """Cloudflare CIDRs parsed as IP network objects, used to validate input."""

    ipv4_cidrs: list[GloballyRoutableIPv4Network]
    ipv6_cidrs: list[GloballyRoutableIPv6Network]


class CloudflareCIDRs(BaseModel):
    """Cloudflare CIDRs kept as strings for writing to firewall rules."""

    ipv4_cidrs: list[str]
    ipv6_cidrs: list[str]


class Project(BaseModel):
    """A Hetzner Cloud API token paired with the firewalls it should update."""

    model_config = ConfigDict(extra="forbid")

    token: SecretStr
    firewalls: list[str] = Field(min_length=1)

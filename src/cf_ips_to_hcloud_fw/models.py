"""Pydantic models for Cloudflare CIDR payloads and project configuration."""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr

_Network = TypeVar("_Network", IPv4Network, IPv6Network)

# Special-purpose blocks that must never reach a Cloudflare-only allow rule
# (IANA IPv4/IPv6 Special-Purpose Address Registries, plus multicast).
#
# These are tested with `overlaps()`, NOT with the ipaddress `is_*` flags. On a
# *network*, those flags are a conjunction over the two endpoints -
# `network_address.is_private and broadcast_address.is_private` - so a range
# that merely CONTAINS private space sets none of them: `128.0.0.0/1` spans
# half of IPv4, subsumes 192.168.0.0/16, and reports is_private False. Overlap
# is the containment-correct question to ask.
_RESERVED_IPV4 = tuple(
    IPv4Network(c)
    for c in (
        "0.0.0.0/8",  # "this network"
        "10.0.0.0/8",  # private
        "100.64.0.0/10",  # carrier-grade NAT
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local
        "172.16.0.0/12",  # private
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # TEST-NET-1
        "192.168.0.0/16",  # private
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2
        "203.0.113.0/24",  # TEST-NET-3
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved, incl. 255.255.255.255 broadcast
    )
)
_RESERVED_IPV6 = tuple(
    IPv6Network(c)
    for c in (
        "::/128",  # unspecified
        "::1/128",  # loopback
        "::ffff:0:0/96",  # IPv4-mapped
        "64:ff9b::/96",  # IPv4/IPv6 translation
        "100::/64",  # discard-only
        "2001::/32",  # Teredo
        "2001:10::/28",  # ORCHID
        "2001:db8::/32",  # documentation
        "2002::/16",  # 6to4
        "fc00::/7",  # unique local
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
    )
)

# Floors on how broad a single published range may be. Cloudflare's live list
# bottoms out at /13 (IPv4) and /29 (IPv6), so these sit 32x and 8192x broader
# than anything actually published - wide enough that a legitimately broader
# future range still passes, tight enough that a spanning aggregate cannot.
# Defence in depth: `overlaps()` above already rejects every aggregate large
# enough to swallow a reserved block.
_MIN_PREFIXLEN_IPV4 = 8
_MIN_PREFIXLEN_IPV6 = 16


def _require_globally_routable(network: _Network) -> _Network:
    """Reject CIDRs that must never end up in a Cloudflare-only allow rule.

    Parsing only proves a CIDR is well-formed, so a tampered or malfunctioning
    API response could hand us a range that is syntactically fine and
    semantically catastrophic: ``0.0.0.0/0`` passes every structural check and
    would open every marked firewall rule to the whole internet. Cloudflare
    only ever publishes globally routable unicast space, so anything else is a
    broken payload rather than a range worth syncing.

    ``is_reserved`` is deliberately not consulted: for IPv6 it means "outside
    IANA-allocated space", so an allocation newer than the running Python's
    tables would be refused, and unallocated space is not routable to an
    attacker anyway.

    Args:
        network: A parsed CIDR from the Cloudflare response.

    Returns:
        The network unchanged, when it is globally routable.

    Raises:
        ValueError: If the network is over-broad or overlaps reserved space.
    """
    if isinstance(network, IPv4Network):
        reserved: tuple = _RESERVED_IPV4
        floor = _MIN_PREFIXLEN_IPV4
    else:
        reserved = _RESERVED_IPV6
        floor = _MIN_PREFIXLEN_IPV6

    if network.prefixlen < floor:
        msg = (
            f"{network} is not globally routable: broader than /{floor}, and "
            "Cloudflare does not publish ranges this large"
        )
        raise ValueError(msg)

    overlapping = [str(block) for block in reserved if network.overlaps(block)]
    if overlapping:
        msg = (
            f"{network} is not globally routable: overlaps reserved space "
            f"({', '.join(overlapping)})"
        )
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

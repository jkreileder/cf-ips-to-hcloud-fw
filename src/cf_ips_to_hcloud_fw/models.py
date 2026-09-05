"""Pydantic models for Cloudflare CIDR payloads and project configuration."""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
)

_Network = TypeVar("_Network", IPv4Network, IPv6Network)

# Special-purpose blocks that must never reach a Cloudflare-only allow rule:
# the not-globally-reachable entries of the IANA IPv4 Special-Purpose Address
# Registry, plus multicast and the reserved 240.0.0.0/4.
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
        "192.31.196.0/24",  # AS112-v4
        "192.52.193.0/24",  # AMT
        "192.88.99.0/24",  # deprecated 6to4 relay anycast
        "192.168.0.0/16",  # private
        "192.175.48.0/24",  # direct delegation AS112
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2
        "203.0.113.0/24",  # TEST-NET-3
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved, incl. 255.255.255.255 broadcast
    )
)
# IPv6 takes the inverse approach: rather than enumerate everything that is not
# globally reachable, require membership of global unicast (RFC 4291) and list
# only the special-purpose blocks that sit *inside* it. That closes the whole
# outside-2000::/3 space in one rule - unique-local, link-local, multicast,
# IPv4-mapped, NAT64, SRv6 SIDs (5f00::/16), IANA-reserved 400::/6 - without
# needing an exhaustive registry copy that goes stale as IANA adds entries.
_GLOBAL_UNICAST_IPV6 = IPv6Network("2000::/3")
_RESERVED_IPV6 = tuple(
    IPv6Network(c)
    for c in (
        "2001::/23",  # IETF protocol assignments (Teredo, benchmarking, ORCHID)
        "2001:db8::/32",  # documentation
        "2002::/16",  # 6to4
        "3fff::/20",  # documentation (RFC 9637)
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

    Note the blast radius of a false rejection. ``overlaps()`` is bidirectional,
    so this refuses a range that merely *contains* a reserved block, and
    ``get_cloudflare_cidrs`` turns any rejection into ``log_error_and_exit`` -
    one bad CIDR aborts the whole sync and leaves every firewall on stale
    rules. That is deliberate: dropping the offending range and syncing the
    rest would quietly narrow the allow-list and break real traffic, which is
    harder to notice than a loud non-zero exit the scheduler already alerts on.
    It does mean the blocks listed above must stay conservative - each one is a
    range Cloudflare can never legitimately publish.

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

    # Containment is checked before the floor so the message names the real
    # reason: fc00::/7, fe80::/10 and ff00::/8 are all shorter than the /16
    # floor, and reporting them as merely "too broad" would send an operator
    # looking for a prefix problem when the range is not unicast at all.
    if isinstance(network, IPv6Network) and not _GLOBAL_UNICAST_IPV6.supernet_of(
        network
    ):
        msg = (
            f"{network} is not globally routable: outside global unicast "
            f"{_GLOBAL_UNICAST_IPV6}"
        )
        raise ValueError(msg)

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


def _strip_token(value: object) -> object:
    """Trim surrounding whitespace from a token before it is wrapped.

    A Kubernetes secret mounted as a file ends with a newline by convention,
    and a YAML block scalar preserves one too. That trailing byte is not part
    of the credential, and carrying it makes every request fail: ``requests``
    refuses a header value containing a newline, raising ``InvalidHeader`` with
    the whole ``Authorization`` value - token included - in its message. So
    this both fixes an ordinary deployment footgun and removes the trigger for
    that disclosure path, which :func:`firewall._describe_sdk_error` then keeps
    out of the log if it ever arises another way.

    Handles both shapes the model is built from: a plain string (the config
    file, parsed by YAML) and an already-wrapped ``SecretStr`` (the env-var
    path, which constructs ``Project`` directly).

    Args:
        value: The raw token as supplied to the model.

    Returns:
        object: The token with surrounding whitespace removed, or the value
        unchanged when it is neither a string nor a SecretStr.
    """
    if isinstance(value, SecretStr):
        return value.get_secret_value().strip()
    return value.strip() if isinstance(value, str) else value


class Project(BaseModel):
    """A Hetzner Cloud API token paired with the firewalls it should update."""

    model_config = ConfigDict(extra="forbid")

    # min_length is applied after the strip, so a whitespace-only token in a
    # config file is refused with the sanitized validation error rather than
    # authenticating as the empty string and failing on every firewall.
    token: Annotated[SecretStr, BeforeValidator(_strip_token)] = Field(min_length=1)
    firewalls: list[str] = Field(min_length=1)

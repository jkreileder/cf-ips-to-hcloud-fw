"""Tests for the Pydantic models."""

from __future__ import annotations

from ipaddress import IPv4Network, ip_network

import pytest
from pydantic import SecretStr, TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.models import CloudflareIPNetworks, Project

# Every CIDR Cloudflare publishes today, as a guard against the routability
# check rejecting a real response. The live list bottoms out at /13 for IPv4
# and /29 for IPv6, so the /8 and /16 floors leave a wide margin.
PUBLISHED_IPV4_CIDRS = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
]
PUBLISHED_IPV6_CIDRS = [
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
]

# A range can be refused either for being over-broad or for overlapping
# reserved space; which guard fires first is an implementation detail, so the
# tests assert only that the payload was refused as unroutable.
_REJECTED = "not globally routable"


def test_cloudflare_ip_networks_accepts_published_ranges() -> None:
    """The published Cloudflare ranges must all pass the routability check."""
    networks = CloudflareIPNetworks(
        ipv4_cidrs=PUBLISHED_IPV4_CIDRS,
        ipv6_cidrs=PUBLISHED_IPV6_CIDRS,
    )
    assert len(networks.ipv4_cidrs) == len(PUBLISHED_IPV4_CIDRS)
    assert len(networks.ipv6_cidrs) == len(PUBLISHED_IPV6_CIDRS)


@pytest.mark.parametrize(
    "cidr",
    [
        "10.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "198.51.100.0/24",
        "192.31.196.0/24",  # AS112-v4
        "192.52.193.0/24",  # AMT
        "192.88.99.0/24",  # deprecated 6to4 relay anycast
        "192.175.48.0/24",  # direct delegation AS112
    ],
)
def test_cloudflare_ip_networks_rejects_unroutable_ipv4(cidr: str) -> None:
    """Unroutable IPv4 ranges are rejected with an explanatory message."""
    with pytest.raises(ValidationError) as e:
        CloudflareIPNetworks(ipv4_cidrs=[cidr], ipv6_cidrs=["2400:cb00::/32"])
    assert _REJECTED in str(e.value)


@pytest.mark.parametrize(
    "cidr",
    [
        # Outside global unicast 2000::/3 — rejected by the containment rule.
        "fc00::/7",  # unique local
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
        "::1/128",  # loopback
        "::ffff:0:0/96",  # IPv4-mapped
        "64:ff9b::/96",  # NAT64
        "64:ff9b:1::/48",  # NAT64 local-use
        "100::/64",  # discard-only
        "100:0:0:1::/64",  # dummy prefix (RFC 9780)
        "5f00::/16",  # SRv6 SIDs (RFC 9602)
        "4000::/16",  # IANA-reserved 400::/6
        # Inside 2000::/3 — need an explicit block entry.
        "2001::/32",  # Teredo
        "2001:2::/48",  # benchmarking
        "2001:10::/28",  # ORCHID
        "2001:db8::/32",  # documentation
        "2002::/16",  # 6to4
        "3fff::/20",  # documentation (RFC 9637)
    ],
)
def test_cloudflare_ip_networks_rejects_unroutable_ipv6(cidr: str) -> None:
    """Unroutable IPv6 ranges are rejected with an explanatory message."""
    with pytest.raises(ValidationError) as e:
        CloudflareIPNetworks(ipv4_cidrs=["198.27.128.0/21"], ipv6_cidrs=[cidr])
    assert _REJECTED in str(e.value)


@pytest.mark.parametrize(
    "cidr",
    ["2001:200::/32", "2400:cb00::/32", "2a06:98c0::/29", "3000::/16"],
)
def test_cloudflare_ip_networks_accepts_global_unicast_ipv6(cidr: str) -> None:
    """Real global-unicast allocations must survive the containment rule.

    ``2001:200::/32`` is the important one: it is a genuine APNIC allocation
    that sits just past the ``2001::/23`` protocol-assignments block, so an
    over-broad reserved entry would wrongly refuse it.
    """
    networks = CloudflareIPNetworks(ipv4_cidrs=["198.27.128.0/21"], ipv6_cidrs=[cidr])
    assert len(networks.ipv6_cidrs) == 1


# Aggregates whose two endpoints each look routable in isolation. The
# ipaddress is_* flags are a conjunction over network_address and
# broadcast_address, so every one of these reported is_private=False and
# passed the earlier endpoint-based check while subsuming private space -
# 128.0.0.0/1 contains 192.168.0.0/16, 0.0.0.0/1 contains 10.0.0.0/8.
@pytest.mark.parametrize(
    "cidr",
    [
        "0.0.0.0/0",
        "0.0.0.0/1",
        "128.0.0.0/1",
        "0.0.0.0/2",
        "64.0.0.0/2",
        "128.0.0.0/2",
        "192.0.0.0/2",
        "0.0.0.0/4",
        "128.0.0.0/7",
    ],
)
def test_cloudflare_ip_networks_rejects_ipv4_aggregates(cidr: str) -> None:
    """Spanning aggregates must not slip past on endpoint semantics alone."""
    with pytest.raises(ValidationError) as e:
        CloudflareIPNetworks(ipv4_cidrs=[cidr], ipv6_cidrs=["2400:cb00::/32"])
    assert _REJECTED in str(e.value)


@pytest.mark.parametrize(
    "cidr",
    ["::/0", "::/1", "8000::/1", "4000::/2", "2000::/3", "::/15"],
)
def test_cloudflare_ip_networks_rejects_ipv6_aggregates(cidr: str) -> None:
    """Same endpoint-semantics bypass on the IPv6 path."""
    with pytest.raises(ValidationError) as e:
        CloudflareIPNetworks(ipv4_cidrs=["198.27.128.0/21"], ipv6_cidrs=[cidr])
    assert _REJECTED in str(e.value)


def test_no_accepted_ipv4_range_can_contain_private_space() -> None:
    """No accepted IPv4 range may overlap reserved space, swept exhaustively.

    An oracle independent of the validator's own reasoning: every /8, /9, /10
    and /12 is offered, and anything accepted must not overlap RFC 1918,
    loopback, link-local, CGNAT, multicast or reserved space. The earlier
    endpoint-based implementation failed this at /8 and above.
    """
    forbidden = [
        ip_network(c)
        for c in (
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "127.0.0.0/8",
            "169.254.0.0/16",
            "100.64.0.0/10",
            "224.0.0.0/4",
            "240.0.0.0/4",
        )
    ]
    checked = 0
    for prefixlen in (8, 9, 10, 12):
        step = 2 ** (32 - prefixlen)
        for base in range(0, 2**32, step):
            net = IPv4Network((base, prefixlen))
            try:
                CloudflareIPNetworks(
                    ipv4_cidrs=[str(net)], ipv6_cidrs=["2400:cb00::/32"]
                )
            except ValidationError:
                continue
            checked += 1
            assert not any(net.overlaps(f) for f in forbidden), (
                f"{net} was accepted but overlaps reserved space"
            )
    assert checked > 0  # the sweep actually exercised accepted ranges


def test_project_valid() -> None:
    """Project model accepts valid configuration."""
    project = Project(token=SecretStr("my-token"), firewalls=["fw-1", "fw-2"])
    assert project.token.get_secret_value() == "my-token"
    assert project.firewalls == ["fw-1", "fw-2"]


def test_project_no_firewall_fails() -> None:
    """Project model rejects empty firewall list."""
    with pytest.raises(ValidationError) as e:
        Project(token=SecretStr("my-token"), firewalls=[])
    assert "at least 1 item" in str(e.value).lower()


def test_project_single_firewall() -> None:
    """Project model accepts a single firewall."""
    project = Project(token=SecretStr("my-token"), firewalls=["fw-1"])
    assert project.firewalls == ["fw-1"]


def test_project_extra_field_rejected() -> None:
    """Project model rejects unknown fields."""
    with pytest.raises(ValidationError) as e:
        Project(
            token=SecretStr("my-token"),
            firewalls=["fw-1"],
            unknown_field="value",  # ty: ignore[unknown-argument]
        )
    assert "Extra inputs are not permitted" in str(e.value)


@pytest.mark.parametrize(
    "raw",
    ["my-token\n", "my-token\r\n", "  my-token  ", "\tmy-token\t", "my-token"],
)
def test_project_token_strips_surrounding_whitespace(raw: str) -> None:
    """A mounted secret file ends with a newline; that byte is not credential.

    Carried through, it makes every request fail — ``requests`` rejects a
    header value containing a newline — so this is a functional fix as well as
    removing the trigger for the disclosure path that
    `firewall._describe_sdk_error` guards.
    """
    assert Project(
        token=SecretStr(raw), firewalls=["fw-1"]
    ).token.get_secret_value() == ("my-token")


def test_project_token_strips_when_parsed_from_a_config_file() -> None:
    """The config-file path hands the validator a plain str, not a SecretStr."""
    projects = TypeAdapter(list[Project]).validate_python([
        {"token": "my-token\n", "firewalls": ["fw-1"]}
    ])
    assert projects[0].token.get_secret_value() == "my-token"

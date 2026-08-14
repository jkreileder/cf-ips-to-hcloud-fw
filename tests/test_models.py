"""Tests for the Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from cf_ips_to_hcloud_fw.models import CloudflareIPNetworks, Project

# Every CIDR Cloudflare publishes today, as a guard against the routability
# check rejecting a real response. The live list bottoms out at /13 for IPv4
# and /29 for IPv6, which is why no minimum prefix length is enforced.
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


def test_cloudflare_ip_networks_accepts_published_ranges() -> None:
    """The published Cloudflare ranges must all pass the routability check."""
    networks = CloudflareIPNetworks(
        ipv4_cidrs=PUBLISHED_IPV4_CIDRS,
        ipv6_cidrs=PUBLISHED_IPV6_CIDRS,
    )
    assert len(networks.ipv4_cidrs) == len(PUBLISHED_IPV4_CIDRS)
    assert len(networks.ipv6_cidrs) == len(PUBLISHED_IPV6_CIDRS)


@pytest.mark.parametrize(
    ("cidr", "reason"),
    [
        ("0.0.0.0/0", "default route"),
        ("10.0.0.0/8", "not globally routable (private)"),
        ("127.0.0.0/8", "not globally routable"),
        ("169.254.0.0/16", "not globally routable"),
        ("224.0.0.0/4", "not globally routable (multicast)"),
        ("240.0.0.0/4", "not globally routable"),
    ],
)
def test_cloudflare_ip_networks_rejects_unroutable_ipv4(cidr: str, reason: str) -> None:
    """Unroutable IPv4 ranges are rejected with an explanatory message."""
    with pytest.raises(ValidationError) as e:
        CloudflareIPNetworks(ipv4_cidrs=[cidr], ipv6_cidrs=["2400:cb00::/32"])
    assert reason in str(e.value)


@pytest.mark.parametrize(
    ("cidr", "reason"),
    [
        ("::/0", "default route"),
        ("fc00::/7", "not globally routable (private)"),
        ("fe80::/10", "not globally routable"),
        ("ff00::/8", "not globally routable (multicast)"),
    ],
)
def test_cloudflare_ip_networks_rejects_unroutable_ipv6(cidr: str, reason: str) -> None:
    """Unroutable IPv6 ranges are rejected with an explanatory message."""
    with pytest.raises(ValidationError) as e:
        CloudflareIPNetworks(ipv4_cidrs=["198.27.128.0/21"], ipv6_cidrs=[cidr])
    assert reason in str(e.value)


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

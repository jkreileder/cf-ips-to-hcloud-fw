"""Tests for the Cloudflare CIDR fetching and validation module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import cloudflare
import cloudflare.types.ips
import httpx
import pytest

from cf_ips_to_hcloud_fw.cloudflare import (
    cf_ips_list,
    get_cloudflare_cidrs,
)
from cf_ips_to_hcloud_fw.models import CloudflareCIDRs


@patch("cloudflare.Cloudflare")
def test_cf_ips_list_sends_no_credentials(mock_cloudflare: MagicMock) -> None:
    """ips.list is public: build the client with no key and omit auth headers."""
    sentinel = object()
    mock_cloudflare.return_value.ips.list.return_value = sentinel

    result = cf_ips_list()

    assert result is sentinel
    # No api_key/api_token/etc. is passed to the client constructor, but the
    # base URL is pinned so CLOUDFLARE_BASE_URL cannot redirect the fetch.
    mock_cloudflare.assert_called_once_with(
        base_url="https://api.cloudflare.com/client/v4"
    )
    _, kwargs = mock_cloudflare.return_value.ips.list.call_args
    headers = kwargs["extra_headers"]
    assert set(headers) == {
        "Authorization",
        "X-Auth-Email",
        "X-Auth-Key",
        "X-Auth-User-Service-Key",
    }
    assert all(isinstance(value, cloudflare.Omit) for value in headers.values())


@patch.dict("os.environ", {"CLOUDFLARE_BASE_URL": "http://attacker.example.invalid"})
def test_cf_ips_list_ignores_base_url_env_var() -> None:
    """CLOUDFLARE_BASE_URL must not redirect the fetch to another server."""
    real_client = cloudflare.Cloudflare
    created: list[cloudflare.Cloudflare] = []

    def build(*, base_url: str) -> MagicMock:
        # Build a real client so the SDK's own env-var fallback gets its chance,
        # then hand cf_ips_list a stub so no request is attempted.
        created.append(real_client(base_url=base_url))
        return MagicMock()

    with patch("cloudflare.Cloudflare", side_effect=build):
        cf_ips_list()

    assert len(created) == 1
    assert str(created[0].base_url) == "https://api.cloudflare.com/client/v4/"


@patch("cloudflare.Cloudflare")
@patch("logging.error")
def test_cf_ips_list_api_connection_error(
    mock_logging: MagicMock, mock_cloudflare: MagicMock
) -> None:
    """cf_ips_list exits when the Cloudflare client raises a connection error."""
    mock_cloudflare.return_value.ips.list.side_effect = cloudflare.APITimeoutError(
        httpx.Request("GET", "https://api.cloudflare.com/client/v4/ips")
    )
    with pytest.raises(SystemExit) as e:
        cf_ips_list()
    assert e.value.code == 1
    mock_cloudflare.return_value.ips.list.assert_called_once()
    mock_logging.assert_called_once_with(
        "Error getting CloudFlare IPs: Request timed out."
    )


@patch("cloudflare.Cloudflare")
@patch("logging.error")
def test_cf_ips_list_api_status_error(
    mock_logging: MagicMock, mock_cloudflare: MagicMock
) -> None:
    """cf_ips_list exits when the Cloudflare API returns a non-success status."""
    mock_cloudflare.return_value.ips.list.side_effect = cloudflare.RateLimitError(
        "rate-limit",
        response=httpx.Response(
            status_code=200,
            request=httpx.Request("GET", "https://api.cloudflare.com/client/v4/ips"),
        ),
        body=None,
    )
    with pytest.raises(SystemExit) as e:
        cf_ips_list()
    assert e.value.code == 1
    mock_cloudflare.return_value.ips.list.assert_called_once()
    mock_logging.assert_called_once_with("Error getting CloudFlare IPs: rate-limit")


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(return_value=None),
)
@patch("logging.error")
def test_get_cloudflare_cidrs_no_response(mock_logging: MagicMock) -> None:
    """get_cloudflare_cidrs aborts when the SDK returns an empty payload."""
    with pytest.raises(SystemExit) as e:
        get_cloudflare_cidrs()
    assert e.value.code == 1
    mock_logging.assert_called_once_with("Cloudflare/ips.list: no response")


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(
        return_value=cloudflare.types.ips.ip_list_response.PublicIPIPs(
            ipv4_cidrs=[],
            ipv6_cidrs=["2400:cb00::/32"],
        )
    ),
)
@patch("logging.error")
def test_get_cloudflare_cidrs_empty_ipv4(mock_logging: MagicMock) -> None:
    """get_cloudflare_cidrs aborts when the API returns an empty IPv4 CIDR list."""
    with pytest.raises(SystemExit) as e:
        get_cloudflare_cidrs()
    assert e.value.code == 1
    mock_logging.assert_called_once_with("Cloudflare/ips.list: empty IPv4 CIDR list")


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(
        return_value=cloudflare.types.ips.ip_list_response.PublicIPIPs(
            ipv4_cidrs=["198.27.128.0/21"],
            ipv6_cidrs=[],
        )
    ),
)
@patch("logging.error")
def test_get_cloudflare_cidrs_empty_ipv6(mock_logging: MagicMock) -> None:
    """get_cloudflare_cidrs aborts when the API returns an empty IPv6 CIDR list."""
    with pytest.raises(SystemExit) as e:
        get_cloudflare_cidrs()
    assert e.value.code == 1
    mock_logging.assert_called_once_with("Cloudflare/ips.list: empty IPv6 CIDR list")


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(
        return_value=cloudflare.types.ips.ip_list_response.PublicIPIPs(
            ipv4_cidrs=["399.27.128.0/21", "198.27.128.0/21"],
            ipv6_cidrs=["2400:cb00::/32", "2606:4700::/32"],
        )
    ),
)
@patch("logging.error")
def test_get_cloudflare_cidrs_invalid(mock_logging: MagicMock) -> None:
    """Invalid IP payloads propagate a validation error through log_error_and_exit."""
    with pytest.raises(SystemExit) as e:
        get_cloudflare_cidrs()
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Cloudflare/ips.list didn't validate" in mock_logging.call_args[0][0]


@pytest.mark.parametrize(
    ("ipv4_cidrs", "ipv6_cidrs"),
    [
        pytest.param(["0.0.0.0/0"], ["2400:cb00::/32"], id="ipv4-default-route"),
        pytest.param(["198.27.128.0/21"], ["::/0"], id="ipv6-default-route"),
        pytest.param(["10.0.0.0/8"], ["2400:cb00::/32"], id="ipv4-private"),
        pytest.param(["127.0.0.0/8"], ["2400:cb00::/32"], id="ipv4-loopback"),
        pytest.param(["198.27.128.0/21"], ["fc00::/7"], id="ipv6-unique-local"),
        pytest.param(["198.27.128.0/21"], ["fe80::/10"], id="ipv6-link-local"),
    ],
)
@patch("logging.error")
def test_get_cloudflare_cidrs_rejects_unroutable(
    mock_logging: MagicMock,
    ipv4_cidrs: list[str],
    ipv6_cidrs: list[str],
) -> None:
    """Syntactically valid but unroutable ranges must never reach a firewall."""
    response = cloudflare.types.ips.ip_list_response.PublicIPIPs(
        ipv4_cidrs=ipv4_cidrs,
        ipv6_cidrs=ipv6_cidrs,
    )
    with (
        patch(
            "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
            MagicMock(return_value=response),
        ),
        pytest.raises(SystemExit) as e,
    ):
        get_cloudflare_cidrs()

    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Cloudflare/ips.list didn't validate" in mock_logging.call_args[0][0]


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(
        return_value=cloudflare.types.ips.ip_list_response.PublicIPIPs(
            ipv4_cidrs=["199.27.128.0/21", "198.27.128.0/21"],
            ipv6_cidrs=["2606:4700::/32", "2400:cb00::/32"],
        )
    ),
)
def test_get_cloudflare_cidrs() -> None:
    """Valid payloads are converted to sorted CloudflareCIDRs instances."""
    result = get_cloudflare_cidrs()
    assert result == CloudflareCIDRs(
        ipv4_cidrs=["198.27.128.0/21", "199.27.128.0/21"],
        ipv6_cidrs=["2400:cb00::/32", "2606:4700::/32"],
    )

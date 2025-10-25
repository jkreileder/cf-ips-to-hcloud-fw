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
@patch("logging.error")
def test_cf_ips_list_api_connection_error(
    mock_logging: MagicMock, mock_cloudflare: MagicMock
) -> None:
    mock_cloudflare.return_value.ips.list.side_effect = cloudflare.APITimeoutError(
        httpx.Request("GET", "https://api.cloudflare.com/client/v4/ips")
    )
    with pytest.raises(SystemExit) as e:
        cf_ips_list()
    assert e.type is SystemExit
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
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_cloudflare.return_value.ips.list.assert_called_once()
    mock_logging.assert_called_once_with("Error getting CloudFlare IPs: rate-limit")


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(return_value=None),
)
@patch("logging.error")
def test_get_cloudflare_cidrs_no_response(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        get_cloudflare_cidrs()
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once_with("Cloudflare/ips.list: no response")


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(
        return_value=cloudflare.types.ips.ip_list_response.PublicIPIPs(
            ipv4_cidrs=["399.27.128.0/21", "198.27.128.0/21"],
            ipv6_cidrs=["2400:cb00::/32", "1400:cb00::/32"],
        )
    ),
)
@patch("logging.error")
def test_get_cloudflare_cidrs_invalid(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        get_cloudflare_cidrs()
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Cloudflare/ips.list didn't validate" in mock_logging.call_args[0][0]


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_list",
    MagicMock(
        return_value=cloudflare.types.ips.ip_list_response.PublicIPIPs(
            ipv4_cidrs=["199.27.128.0/21", "198.27.128.0/21"],
            ipv6_cidrs=["2400:cb00::/32", "1400:cb00::/32"],
        )
    ),
)
def test_get_cloudflare_cidrs() -> None:
    result = get_cloudflare_cidrs()
    assert result == CloudflareCIDRs(
        ipv4_cidrs=["198.27.128.0/21", "199.27.128.0/21"],
        ipv6_cidrs=["1400:cb00::/32", "2400:cb00::/32"],
    )

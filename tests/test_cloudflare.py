from __future__ import annotations

from unittest.mock import MagicMock, patch

import CloudFlare  # type: ignore[import-untyped]
import pytest

from cf_ips_to_hcloud_fw.cloudflare import (
    cf_ips_get,  # type: ignore[import-untyped]
    get_cloudflare_cidrs,
)
from cf_ips_to_hcloud_fw.models import CloudflareCIDRs


@patch("CloudFlare.CloudFlare")
@patch("logging.error")
def test_cf_ips_get(mock_logging: MagicMock, mock_cloudflare: MagicMock) -> None:
    mock_cloudflare.return_value.ips.get.side_effect = (
        CloudFlare.exceptions.CloudFlareAPIError(503, "503")  # type: ignore[assignment]
    )
    with pytest.raises(SystemExit) as e:
        cf_ips_get()
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_cloudflare.return_value.ips.get.assert_called_once()
    mock_logging.assert_called_once_with("Error getting CloudFlare IPs: 503")


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_get",
    MagicMock(return_value={"ipv4_cidrs": ["199.27.128.0/21", "198.27.128.0/21"]}),
)
@patch("logging.error")
def test_get_cloudflare_cidrs_invalid(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        get_cloudflare_cidrs()
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Cloudflare/ips.get didn't validate" in mock_logging.call_args[0][0]


@patch(
    "cf_ips_to_hcloud_fw.cloudflare.cf_ips_get",
    MagicMock(
        return_value={
            "ipv4_cidrs": ["199.27.128.0/21", "198.27.128.0/21"],
            "ipv6_cidrs": ["2400:cb00::/32", "1400:cb00::/32"],
        }
    ),
)
def test_get_cloudflare_cidrs() -> None:
    result = get_cloudflare_cidrs()
    assert result == CloudflareCIDRs(
        ipv4_cidrs=["198.27.128.0/21", "199.27.128.0/21"],
        ipv6_cidrs=["1400:cb00::/32", "2400:cb00::/32"],
    )

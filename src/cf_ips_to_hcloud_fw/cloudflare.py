from __future__ import annotations

import logging

import cloudflare
import cloudflare.types.ips
from pydantic import TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import CloudflareCIDRs, CloudflareIPNetworks


def cf_ips_list() -> cloudflare.types.ips.IPListResponse | None:
    """Call Cloudflare's `ips.list` endpoint and return the raw response.

    Returns:
        cloudflare.types.ips.IPListResponse | None: Raw API response, or None
        when the SDK returns no payload.
    """
    cf = cloudflare.Cloudflare(api_key="dummy")  # required to pass credential check
    try:
        return cf.ips.list()
    except (cloudflare.APIConnectionError, cloudflare.APIStatusError) as e:
        log_error_and_exit(f"Error getting CloudFlare IPs: {e}")


def get_cloudflare_cidrs() -> CloudflareCIDRs:
    """Fetch, validate, and sort the Cloudflare IPv4/IPv6 CIDR lists.

    Returns:
        CloudflareCIDRs: Sanitized CIDR model ready for downstream consumers.
    """
    ips_model = cf_ips_list()
    if ips_model is None:
        log_error_and_exit("Cloudflare/ips.list: no response")
    try:
        ips_dict = ips_model.model_dump()
        TypeAdapter(CloudflareIPNetworks).validate_python(ips_dict)  # sanity check
        cf_ips = TypeAdapter(CloudflareCIDRs).validate_python(ips_dict)
    except ValidationError as e:
        log_error_and_exit(f"Cloudflare/ips.list didn't validate: {e}")

    if not cf_ips.ipv4_cidrs:
        log_error_and_exit("Cloudflare/ips.list: empty IPv4 CIDR list")
    if not cf_ips.ipv6_cidrs:
        log_error_and_exit("Cloudflare/ips.list: empty IPv6 CIDR list")

    cf_ips.ipv4_cidrs.sort()
    cf_ips.ipv6_cidrs.sort()
    logging.info("Got Cloudflare IPs")
    logging.debug(f"Cloudflare CIDRs: {cf_ips}")
    return cf_ips

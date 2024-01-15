from __future__ import annotations

import logging

import CloudFlare  # type: ignore[import-untyped]
from pydantic import TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import CloudflareCIDRs, CloudflareIPNetworks


def cf_ips_get() -> dict:  # type: ignore[return]
    cf = CloudFlare.CloudFlare(use_sessions=False)
    try:
        return cf.ips.get()  # type: ignore[return-value]
    except CloudFlare.exceptions.CloudFlareAPIError as e:  # type: ignore[attr-defined]
        log_error_and_exit(f"Error getting CloudFlare IPs: {e}")


def get_cloudflare_cidrs() -> CloudflareCIDRs:
    response = cf_ips_get()  # type: ignore[return-value]
    try:
        TypeAdapter(CloudflareIPNetworks).validate_python(response)  # sanity check
        cf_ips = TypeAdapter(CloudflareCIDRs).validate_python(response)
    except ValidationError as e:
        log_error_and_exit(f"Cloudflare/ips.get didn't validate: {e}")

    cf_ips.ipv4_cidrs.sort()
    cf_ips.ipv6_cidrs.sort()
    logging.info("Got Cloudflare IPs")
    logging.debug(f"Cloudflare CIDRs: {cf_ips}")
    return cf_ips

from __future__ import annotations

import logging

import cloudflare
import cloudflare.types.ips
from pydantic import TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import CloudflareCIDRs, CloudflareIPNetworks


def cf_ips_list() -> cloudflare.types.ips.IPListResponse | None:
    cf = cloudflare.Cloudflare(api_key="dummy")  # required to pass credential check
    try:
        return cf.ips.list()
    except (cloudflare.APIConnectionError, cloudflare.APIStatusError) as e:
        log_error_and_exit(f"Error getting CloudFlare IPs: {e}")


def get_cloudflare_cidrs() -> CloudflareCIDRs:
    ips_model = cf_ips_list()
    if ips_model is None:
        log_error_and_exit("Cloudflare/ips.list: no response")
    try:
        ips_dict = ips_model.model_dump()
        TypeAdapter(CloudflareIPNetworks).validate_python(ips_dict)  # sanity check
        cf_ips = TypeAdapter(CloudflareCIDRs).validate_python(ips_dict)
    except ValidationError as e:
        log_error_and_exit(f"Cloudflare/ips.list didn't validate: {e}")

    cf_ips.ipv4_cidrs.sort()
    cf_ips.ipv6_cidrs.sort()
    logging.info("Got Cloudflare IPs")
    logging.debug(f"Cloudflare CIDRs: {cf_ips}")
    return cf_ips

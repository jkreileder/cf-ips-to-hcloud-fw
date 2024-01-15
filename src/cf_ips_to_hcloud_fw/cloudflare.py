from __future__ import annotations

import logging
from ipaddress import IPv4Network, IPv6Network

import CloudFlare  # type: ignore[import-untyped]
from pydantic import BaseModel, TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.logging import log_error_and_exit


class CloudflareIPNetworks(BaseModel):
    ipv4_cidrs: list[IPv4Network]
    ipv6_cidrs: list[IPv6Network]


class CloudflareIPs(BaseModel):
    ipv4_cidrs: list[str]
    ipv6_cidrs: list[str]


def cf_ips_get() -> dict:  # type: ignore[return]
    cf = CloudFlare.CloudFlare(use_sessions=False)
    try:
        return cf.ips.get()  # type: ignore[return-value]
    except CloudFlare.exceptions.CloudFlareAPIError as e:  # type: ignore[attr-defined]
        log_error_and_exit(f"Error getting CloudFlare IPs: {e}")


def get_cloudflare_ips() -> CloudflareIPs:
    response = cf_ips_get()  # type: ignore[return-value]
    try:
        TypeAdapter(CloudflareIPNetworks).validate_python(response)  # sanity check
        cf_ips = TypeAdapter(CloudflareIPs).validate_python(response)
    except ValidationError as e:
        log_error_and_exit(f"Cloudflare/ips.get didn't validate: {e}")

    cf_ips.ipv4_cidrs.sort()
    cf_ips.ipv6_cidrs.sort()
    logging.info("Got Cloudflare IPs")
    logging.debug(f"Cloudflare IPs: {cf_ips}")
    return cf_ips

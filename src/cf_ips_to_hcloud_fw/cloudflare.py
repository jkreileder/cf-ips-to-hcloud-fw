"""Fetch and validate Cloudflare's published IPv4/IPv6 CIDR ranges."""

from __future__ import annotations

import logging

import cloudflare
import cloudflare.types.ips
from cloudflare import Omit
from pydantic import TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import CloudflareCIDRs, CloudflareIPNetworks

# `ips.list` is a public endpoint that needs no credentials. The SDK otherwise
# refuses to send a request without an auth method, so explicitly omit the auth
# headers — this sends no credential at all, instead of a placeholder key.
_NO_AUTH_HEADERS = {
    "Authorization": Omit(),
    "X-Auth-Email": Omit(),
    "X-Auth-Key": Omit(),
    "X-Auth-User-Service-Key": Omit(),
}

# Passed explicitly because the SDK otherwise falls back to the
# CLOUDFLARE_BASE_URL environment variable, an undocumented knob that decides
# where the firewall's entire allow list comes from. Pinning it here makes that
# one variable inert; the value is the SDK's own default.
#
# That is a real boundary but a partial one, and the scope is worth being exact
# about. The transport is deliberately left alone: httpx keeps trust_env=True,
# so HTTPS_PROXY and SSL_CERT_FILE still apply and a principal who can set them
# can still intercept the fetch. That is on purpose - operators behind a
# corporate egress proxy need it, and turning it off would break them with no
# way to opt back in. The trade is easy because anyone able to set environment
# variables on this job can already set HCLOUD_TOKEN, replace the config file,
# or point PYTHONPATH at their own code; TLS interception is a longer road to
# capabilities they already have. What actually guards a tampered response is
# the routability check in models.py, and that is bounded too - it rejects
# reserved and over-broad ranges, not a globally routable prefix an attacker
# happens to control.
CLOUDFLARE_API_BASE_URL = "https://api.cloudflare.com/client/v4"


def cf_ips_list() -> cloudflare.types.ips.IPListResponse | None:
    """Call Cloudflare's `ips.list` endpoint and return the raw response.

    Returns:
        cloudflare.types.ips.IPListResponse | None: Raw API response, or None
        when the SDK returns no payload.
    """
    cf = cloudflare.Cloudflare(base_url=CLOUDFLARE_API_BASE_URL)
    try:
        return cf.ips.list(extra_headers=_NO_AUTH_HEADERS)
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

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hcloud import APIException, Client
from hcloud.firewalls.domain import Firewall, FirewallRule

from cf_ips_to_hcloud_fw.logging import log_error_and_exit

if TYPE_CHECKING:  # pragma: no cover
    from cf_ips_to_hcloud_fw.models import CloudflareCIDRs, Project  # pragma: no cover

CF_IPV4 = "__CLOUDFLARE_IPS_V4__"
CF_IPV6 = "__CLOUDFLARE_IPS_V6__"
CF_ALL = "__CLOUDFLARE_IPS__"


def update_project(project: Project, cf_cidrs: CloudflareCIDRs) -> None:
    client = Client(token=project.token.get_secret_value())
    for name in project.firewalls:
        try:
            fw = client.firewalls.get_by_name(name)
        except APIException as e:
            log_error_and_exit(f"hcloud/firewalls.get_by_name failed for {name!r}: {e}")
        if fw:
            logging.info(f"Inspecting hcloud firewall {name!r}")
            update_firewall(client, fw, cf_cidrs)
        else:
            logging.error(f"hcloud firewall {name!r} not found")


def update_source_ips(
    fw: Firewall, rule: FirewallRule, cidrs: list[str], kind: str
) -> bool:
    needs_update = rule.source_ips != cidrs
    if needs_update:
        rule.source_ips = cidrs
        logging.debug(
            f"Updating {fw.name!r}/{rule.description!r} with {kind} addresses"
        )
    else:
        logging.debug(f"{fw.name!r}/{rule.description!r} already up-to-date")
    return needs_update


def update_firewall_rule(
    fw: Firewall,
    rule: FirewallRule,
    cf_cidrs: CloudflareCIDRs,
    *,
    ipv4: bool,
    ipv6: bool,
) -> bool:
    if not ipv4 and not ipv6:
        return False

    ip_types: dict[tuple[bool, bool], tuple[list[str], str]] = {
        (True, True): (cf_cidrs.ipv4_cidrs + cf_cidrs.ipv6_cidrs, "IPv4+IPv6"),
        (True, False): (cf_cidrs.ipv4_cidrs, "IPv4"),
        (False, True): (cf_cidrs.ipv6_cidrs, "IPv6"),
    }
    ip_cidrs, ip_type = ip_types[(ipv4, ipv6)]
    return update_source_ips(fw, rule, ip_cidrs, ip_type)


def fw_set_rules(client: Client, fw: Firewall) -> None:
    logging.info(f"Updating rules for hcloud firewall {fw.name!r}")
    try:
        rules = fw.rules or []
        client.firewalls.set_rules(fw, rules)
    except APIException as e:
        log_error_and_exit(f"hcloud/firewall.set_rules failed for {fw.name!r}: {e}")


def update_firewall(client: Client, fw: Firewall, cf_cidrs: CloudflareCIDRs) -> None:
    if fw.rules:
        needs_update = False
        for rule in fw.rules:
            if rule.direction == FirewallRule.DIRECTION_IN and rule.description:
                needs_update |= update_firewall_rule(
                    fw,
                    rule,
                    cf_cidrs,
                    ipv4=CF_ALL in rule.description or CF_IPV4 in rule.description,
                    ipv6=CF_ALL in rule.description or CF_IPV6 in rule.description,
                )
        if needs_update:
            fw_set_rules(client, fw)
        else:
            logging.info(f"hcloud firewall {fw.name!r} already up-to-date")
    else:
        logging.warning(f"hcloud firewall {fw.name!r} has no rules - ignoring it")

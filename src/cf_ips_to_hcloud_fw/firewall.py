from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from hcloud import APIException, Client
from hcloud.firewalls.domain import Firewall, FirewallRule

from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit

if TYPE_CHECKING:  # pragma: no cover
    from cf_ips_to_hcloud_fw.models import CloudflareCIDRs, Project  # pragma: no cover

CF_IPV4 = "__CLOUDFLARE_IPS_V4__"
CF_IPV6 = "__CLOUDFLARE_IPS_V6__"
CF_ALL = "__CLOUDFLARE_IPS__"


class IPVersionTargets(NamedTuple):
    """
    Structure holding boolean flags indicating which IP versions (IPv4/IPv6)
    should be targeted for firewall rule updates.
    """

    ipv4: bool
    ipv6: bool


def update_project(
    *, project: Project, cf_cidrs: CloudflareCIDRs, project_index: int
) -> list[str]:
    """Synchronize every firewall listed in a project with the latest CIDRs.

    Args:
        project: Project definition that holds the API token and firewall names.
        cf_cidrs: Cloudflare CIDR model downloaded at runtime.
        project_index: 1-based index of the project being processed, used for logging.

    Returns:
        list[str]: Labels of firewalls not found, prefixed with the project index.
    """
    client = Client(token=project.token.get_secret_value())
    skipped: list[str] = []
    for name in project.firewalls:
        try:
            fw = client.firewalls.get_by_name(name)
        except APIException as e:
            log_error_and_exit(
                "hcloud/firewalls.get_by_name failed for "
                f"{name!r} in project {project_index}: {e}"
            )
        if fw:
            logging.info(
                f"Inspecting hcloud firewall {name!r} in project {project_index}"
            )
            update_firewall(client, fw, cf_cidrs, project_index=project_index)
        else:
            logging.debug(
                f"hcloud firewall {name!r} not found in project {project_index}"
            )
            skipped.append(f"project {project_index}:{name!r}")
    return skipped


def update_source_ips(
    fw: Firewall, rule: FirewallRule, cidrs: list[str], kind: str, *, project_index: int
) -> bool:
    """Update a rule's source CIDRs when they differ.

    Args:
        fw: Firewall currently being mutated.
        rule: Individual firewall rule within the firewall.
        cidrs: Desired list of CIDR strings.
        kind: Human-readable tag (IPv4/IPv6) for logging.
        project_index: 1-based index of the project being processed, used for logging.

    Returns:
        bool: True when the rule was modified.
    """
    needs_update = rule.source_ips != cidrs
    if needs_update:
        rule.source_ips = cidrs
        logging.debug(
            f"Updating {fw.name!r}/{rule.description!r} in project {project_index} "
            f"with {kind} addresses"
        )
    else:
        logging.debug(
            f"{fw.name!r}/{rule.description!r} in project {project_index} "
            "already up-to-date"
        )
    return needs_update


def update_firewall_rule(
    fw: Firewall,
    rule: FirewallRule,
    cf_cidrs: CloudflareCIDRs,
    ip_targets: IPVersionTargets,
    *,
    project_index: int,
) -> bool:
    """Apply the correct IPv4/IPv6 CIDRs to a single firewall rule if marked.

    Args:
        fw: Firewall currently being mutated (used for logging).
        rule: Rule candidate to inspect/update.
        cf_cidrs: Cloudflare CIDR model downloaded at runtime.
        ip_targets: Targeted IP versions for this rule.
        project_index: 1-based index of the project being processed, used for logging.

    Returns:
        bool: True when the rule needed a change.
    """
    if not ip_targets.ipv4 and not ip_targets.ipv6:
        return False

    ip_types: dict[tuple[bool, bool], tuple[list[str], str]] = {
        (True, True): (cf_cidrs.ipv4_cidrs + cf_cidrs.ipv6_cidrs, "IPv4+IPv6"),
        (True, False): (cf_cidrs.ipv4_cidrs, "IPv4"),
        (False, True): (cf_cidrs.ipv6_cidrs, "IPv6"),
    }
    ip_cidrs, ip_type = ip_types[ip_targets.ipv4, ip_targets.ipv6]
    return update_source_ips(fw, rule, ip_cidrs, ip_type, project_index=project_index)


def fw_set_rules(client: Client, fw: Firewall, project_index: int) -> None:
    """Persist rule updates to Hetzner via the SDK, aborting on API errors.

    Args:
        client: Authenticated Hetzner Cloud client.
        fw: Firewall whose rules were modified earlier in the flow.
        project_index: 1-based index of the project being processed, used for logging.
    """
    logging.info(
        f"Updating rules for hcloud firewall {fw.name!r} in project {project_index}"
    )
    try:
        rules = fw.rules or []
        client.firewalls.set_rules(fw, rules)
    except APIException as e:
        log_error_and_exit(
            f"hcloud/firewall.set_rules failed for {fw.name!r} in project "
            f"{project_index}: {e}"
        )


def update_firewall(
    client: Client, fw: Firewall, cf_cidrs: CloudflareCIDRs, *, project_index: int
) -> None:
    """Refresh all Cloudflare-tagged rules on a firewall and push changes.

    Args:
        client: Authenticated Hetzner Cloud client.
        fw: Firewall retrieved from the API.
        cf_cidrs: Cloudflare CIDR model downloaded at runtime.
        project_index: 1-based index of the project being processed, used for logging.
    """
    if fw.rules:
        needs_update = False
        for rule in fw.rules:
            if rule.direction == FirewallRule.DIRECTION_IN and rule.description:
                ip_targets = IPVersionTargets(
                    ipv4=CF_ALL in rule.description or CF_IPV4 in rule.description,
                    ipv6=CF_ALL in rule.description or CF_IPV6 in rule.description,
                )
                needs_update |= update_firewall_rule(
                    fw,
                    rule,
                    cf_cidrs,
                    ip_targets,
                    project_index=project_index,
                )
        if needs_update:
            fw_set_rules(client, fw, project_index=project_index)
        else:
            logging.info(
                f"hcloud firewall {fw.name!r} in project {project_index} "
                "already up-to-date"
            )
    else:
        logging.warning(
            f"hcloud firewall {fw.name!r} in project {project_index} "
            "has no rules - ignoring it"
        )

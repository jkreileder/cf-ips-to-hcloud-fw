import argparse
import logging
import sys
from ipaddress import IPv4Network, IPv6Network
from typing import NoReturn

import CloudFlare  # type: ignore[import-untyped]
import yaml
from hcloud._client import Client
from hcloud._exceptions import APIException
from hcloud.firewalls.domain import Firewall, FirewallRule
from pydantic import BaseModel, SecretStr, TypeAdapter, ValidationError
from yaml import YAMLError

from cf_ips_to_hcloud_fw.version import __VERSION__

CF_IPV4 = "__CLOUDFLARE_IPS_V4__"
CF_IPV6 = "__CLOUDFLARE_IPS_V6__"
CF_ALL = "__CLOUDFLARE_IPS__"


class CloudflareIPNetworks(BaseModel):
    ipv4_cidrs: list[IPv4Network]
    ipv6_cidrs: list[IPv6Network]


class CloudflareIPs(BaseModel):
    ipv4_cidrs: list[str]
    ipv6_cidrs: list[str]


class Project(BaseModel):
    token: SecretStr
    firewalls: list[str]


def log_error_and_exit(msg: str) -> NoReturn:
    logging.error(msg)
    sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update Hetzner Cloud firewall rules with Cloudflare IP ranges"
    )
    parser.add_argument(
        "-c", "--config", help="config file", metavar="CONFIGFILE", required=True
    )
    parser.add_argument("-v", "--version", action="version", version=__VERSION__)
    parser.add_argument("-d", "--debug", action="store_true")
    return parser


def read_config(config_file: str) -> list[Project]:
    try:
        with open(config_file, encoding="utf-8") as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        log_error_and_exit(f"Config file {config_file} not found.")
    except YAMLError as e:
        log_error_and_exit(f"Error reading config file {config_file}: {e}")

    try:
        projects = TypeAdapter(list[Project]).validate_python(config)
    except ValidationError as e:
        log_error_and_exit(f"Config file {config_file} is broken: {e}")

    if not projects:
        logging.warning(f"Config file {config_file} contains no projects - exiting")
        sys.exit(0)

    return projects


def cf_ips_get() -> dict:  # type: ignore
    cf = CloudFlare.CloudFlare(use_sessions=False)
    try:
        return cf.ips.get()  # type: ignore
    except CloudFlare.exceptions.CloudFlareAPIError as e:  # type: ignore
        log_error_and_exit(f"Error getting CloudFlare IPs: {e}")


def get_cloudflare_ips() -> CloudflareIPs:
    response = cf_ips_get()  # type: ignore
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


def update_project(project: Project, cf_ips: CloudflareIPs) -> None:
    client = Client(token=project.token.get_secret_value())
    for name in project.firewalls:
        try:
            fw = client.firewalls.get_by_name(name)
        except APIException as e:
            log_error_and_exit(f"hcloud/firewalls.get_by_name failed for {name!r}: {e}")
        if fw:
            logging.info(f"Inspecting hcloud firewall {name!r}")
            update_firewall(client, fw, cf_ips)
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
    fw: Firewall, rule: FirewallRule, cf_ips: CloudflareIPs, ipv4: bool, ipv6: bool
) -> bool:
    if not ipv4 and not ipv6:
        return False

    ip_types: dict[tuple[bool, bool], tuple[list[str], str]] = {
        (True, True): (cf_ips.ipv4_cidrs + cf_ips.ipv6_cidrs, "IPv4+IPv6"),
        (True, False): (cf_ips.ipv4_cidrs, "IPv4"),
        (False, True): (cf_ips.ipv6_cidrs, "IPv6"),
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


def update_firewall(client: Client, fw: Firewall, cf_ips: CloudflareIPs) -> None:
    if fw.rules:
        needs_update = False
        for rule in fw.rules:
            if rule.direction == FirewallRule.DIRECTION_IN and rule.description:
                needs_update |= update_firewall_rule(
                    fw,
                    rule,
                    cf_ips,
                    CF_ALL in rule.description or CF_IPV4 in rule.description,
                    CF_ALL in rule.description or CF_IPV6 in rule.description,
                )
        if needs_update:
            fw_set_rules(client, fw)
        else:
            logging.info(f"hcloud firewall {fw.name!r} already up-to-date")
    else:
        logging.warning(f"hcloud firewall {fw.name!r} has no rules - ignoring it")


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.getLevelName(logging.DEBUG if args.debug else logging.INFO),
        format=(
            "%(asctime)s %(levelname)-8s "
            + ("[%(filename)s:%(funcName)s:%(lineno)d] " if args.debug else "")
            + "%(message)s"
        ),
    )

    projects = read_config(args.config)
    cf_ips = get_cloudflare_ips()
    for project in projects:
        update_project(project, cf_ips)


if __name__ == "__main__":  # pragma: no cover
    main()  # pragma: no cover

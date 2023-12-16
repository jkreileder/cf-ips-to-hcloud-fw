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
    all_cidrs: list[str] = []


class Project(BaseModel):
    token: SecretStr
    firewalls: list[str]


def log_error_and_exit(msg: str) -> NoReturn:
    logging.error(msg)
    sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update Hetzner Cloud firewall rules with Cloudflare IP ranges",
    )
    parser.add_argument(
        "-c", "--config", help="config file", metavar="CONFIGFILE", required=True
    )
    parser.add_argument("-v", "--version", action="version", version=__VERSION__)
    parser.add_argument("-d", "--debug", action="store_true")
    return parser


def read_config(config_file: str) -> list[Project]:
    try:
        with open(config_file) as file:
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
    cf_ips.all_cidrs = cf_ips.ipv4_cidrs + cf_ips.ipv6_cidrs
    logging.info("Got Cloudflare IPs")
    logging.debug(f"Cloudflare IPs: {cf_ips}")
    return cf_ips


def update_project(project: Project, cf_ips: CloudflareIPs) -> None:
    client = Client(token=project.token.get_secret_value())
    for name in project.firewalls:
        try:
            fw = client.firewalls.get_by_name(name)
        except APIException as e:
            log_error_and_exit(f"hcloud/firewalls.get_by_name failed: {e}")
        if fw:
            logging.info(f"Inspecting hcloud firewall {name!r}")
            update_firewall(client, fw, cf_ips)
        else:
            logging.error(f"hcloud firewall {name!r} not found")


def update_source_ips(
    needs_update: bool, fw: Firewall, r: FirewallRule, cidrs: list[str], kind: str
) -> bool:
    needs_update = needs_update or r.source_ips != cidrs
    r.source_ips = cidrs
    logging.debug(f"Updating {fw.name!r}/{r.description!r} with {kind} addresses")
    return needs_update


def update_firewall_rule(
    needs_update: bool,
    fw: Firewall,
    r: FirewallRule,
    cf_ips: CloudflareIPs,
    ipv4: bool,
    ipv6: bool,
) -> bool:
    if ipv4 and ipv6:
        ip_cidrs = cf_ips.all_cidrs
        ip_type = "all"
    elif ipv4:
        ip_cidrs = cf_ips.ipv4_cidrs
        ip_type = "IPv4"
    elif ipv6:
        ip_cidrs = cf_ips.ipv6_cidrs
        ip_type = "IPv6"
    else:
        return needs_update

    return update_source_ips(needs_update, fw, r, ip_cidrs, ip_type)


def fw_set_rules(client: Client, fw: Firewall) -> None:
    logging.info(f"Updating hcloud firewall {fw.name!r}")
    try:
        rules = fw.rules or []
        client.firewalls.set_rules(fw, rules)
    except APIException as e:
        log_error_and_exit(f"hcloud/firewall.set_rules failed: {e}")


def update_firewall(client: Client, fw: Firewall, cf_ips: CloudflareIPs) -> None:
    if fw.rules:
        needs_update = False
        for r in fw.rules:
            if r.direction == "in" and r.description:
                needs_update = update_firewall_rule(
                    needs_update,
                    fw,
                    r,
                    cf_ips,
                    CF_ALL in r.description or CF_IPV4 in r.description,
                    CF_ALL in r.description or CF_IPV6 in r.description,
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
    for p in projects:
        update_project(p, cf_ips)


if __name__ == "__main__":
    main()

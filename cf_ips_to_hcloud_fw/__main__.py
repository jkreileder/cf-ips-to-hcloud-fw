import argparse
import logging
import sys
from ipaddress import IPv4Network, IPv6Network
from typing import NoReturn

import CloudFlare  # type: ignore[import-untyped]
import yaml
from hcloud._client import Client
from hcloud.firewalls.domain import Firewall, FirewallRule
from pydantic import BaseModel, SecretStr, TypeAdapter

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


def fatal(msg: str) -> NoReturn:
    logging.fatal(msg)
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
        with open(config_file) as file:
            config = yaml.safe_load(file)
    except Exception as e:
        fatal(f"Error reading config file {config_file}: {e}")

    try:
        projects = TypeAdapter(list[Project]).validate_python(config)
    except Exception as e:
        fatal(f"Config file {config_file} is broken: {e}")

    if not projects:
        logging.warning(f"Config file {config_file} is empty - exiting")
        sys.exit(0)

    return projects


def get_cloudflare_ips() -> CloudflareIPs:
    try:
        response = CloudFlare.CloudFlare(use_sessions=False).ips.get()  # type: ignore
        TypeAdapter(CloudflareIPNetworks).validate_python(response)  # sanity check
        cf_ips = TypeAdapter(CloudflareIPs).validate_python(response)
        cf_ips.ipv4_cidrs.sort()
        cf_ips.ipv6_cidrs.sort()
        cf_ips.all_cidrs = cf_ips.ipv4_cidrs + cf_ips.ipv6_cidrs
        logging.info("Got Cloudflare IPs")
        logging.debug(f"Cloudflare IPs: {cf_ips}")
        return cf_ips
    except Exception as e:
        fatal(f"Cloudflare/ips.get failed: {e}")


def update_project(project: Project, cf_ips: CloudflareIPs) -> None:
    client = Client(token=project.token.get_secret_value())
    for name in project.firewalls:
        try:
            fw = client.firewalls.get_by_name(name)
        except Exception as e:
            fatal(f"hcloud/firewalls.get_by_name failed: {e}")
        if fw:
            logging.info(f"Inspecting hcloud firewall {name!r}")
            update_firewall(client, fw, cf_ips)
        else:
            logging.error(f"hcloud firewall {name!r} not found")


def update_source_ips(
    needs_update: bool, fw: Firewall, r: FirewallRule, cidrs: list[str], type: str
) -> bool:
    needs_update = needs_update or r.source_ips != cidrs
    r.source_ips = cidrs
    logging.debug(f"Updating {fw.name!r}/{r.description!r} with {type} addresses")
    return needs_update


def update_firewall(client: Client, fw: Firewall, cf_ips: CloudflareIPs) -> None:
    if fw.rules:
        needs_update = False
        for r in fw.rules:
            if r.direction == "in" and r.description:
                ipv4 = CF_IPV4 in r.description
                ipv6 = CF_IPV6 in r.description
                if ipv4 and ipv6 or CF_ALL in r.description:
                    needs_update = update_source_ips(
                        needs_update, fw, r, cf_ips.all_cidrs, "all"
                    )
                elif ipv4:
                    needs_update = update_source_ips(
                        needs_update, fw, r, cf_ips.ipv4_cidrs, "IPv4"
                    )
                elif ipv6:
                    needs_update = update_source_ips(
                        needs_update, fw, r, cf_ips.ipv6_cidrs, "IPv6"
                    )
        if needs_update:
            logging.info(f"Updating hcloud firewall {fw.name!r}")
            try:
                client.firewalls.set_rules(fw, fw.rules)
            except Exception as e:
                fatal(f"hcloud/firewall.set_rules failed: {e}")
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

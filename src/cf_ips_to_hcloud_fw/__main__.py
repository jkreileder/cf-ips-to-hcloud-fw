from __future__ import annotations

import argparse

from cf_ips_to_hcloud_fw.cloudflare import get_cloudflare_cidrs
from cf_ips_to_hcloud_fw.config import read_config
from cf_ips_to_hcloud_fw.firewall import update_project
from cf_ips_to_hcloud_fw.logging import setup_logging
from cf_ips_to_hcloud_fw.version import __VERSION__


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


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    setup_logging(args)

    projects = read_config(args.config)
    cf_cidrs = get_cloudflare_cidrs()
    for project in projects:
        update_project(project, cf_cidrs)


if __name__ == "__main__":  # pragma: no cover
    main()  # pragma: no cover

from __future__ import annotations

import argparse

from cf_ips_to_hcloud_fw import __version__
from cf_ips_to_hcloud_fw.cloudflare import get_cloudflare_cidrs
from cf_ips_to_hcloud_fw.config import read_config
from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit, setup_logging
from cf_ips_to_hcloud_fw.firewall import update_project


def create_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser with config, version, and debug switches.

    Returns:
        argparse.ArgumentParser: Parser configured for this CLI.
    """
    parser = argparse.ArgumentParser(
        description="Update Hetzner Cloud firewall rules with Cloudflare IP ranges"
    )
    parser.add_argument(
        "-c", "--config", help="config file", metavar="CONFIGFILE", required=True
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument("-d", "--debug", action="store_true")
    return parser


def main() -> None:
    """Parse arguments, configure logging, and run the sync workflow."""
    parser = create_parser()
    args = parser.parse_args()
    setup_logging(args)

    projects = read_config(args.config)
    cf_cidrs = get_cloudflare_cidrs()
    all_skipped: list[str] = []
    for project in projects:
        skipped = update_project(project, cf_cidrs)
        all_skipped.extend(skipped)

    if all_skipped:
        msg = f"Some firewalls have been skipped: {', '.join(all_skipped)}"
        log_error_and_exit(msg)


if __name__ == "__main__":  # pragma: no cover
    main()  # pragma: no cover

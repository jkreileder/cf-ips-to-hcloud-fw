"""CLI entry point: parse args, fetch Cloudflare ranges, update firewalls."""

from __future__ import annotations

import argparse

from cf_ips_to_hcloud_fw import __version__
from cf_ips_to_hcloud_fw.cloudflare import get_cloudflare_cidrs
from cf_ips_to_hcloud_fw.config import load_projects
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
        "-c",
        "--config",
        help=(
            "config file; if omitted, a 'config.yaml' in the working directory "
            "is used when present, otherwise a single project is built from the "
            "HCLOUD_TOKEN and HCLOUD_FIREWALLS environment variables"
        ),
        metavar="CONFIGFILE",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument("-d", "--debug", action="store_true")
    return parser


def main() -> None:
    """Parse arguments, configure logging, and run the sync workflow."""
    parser = create_parser()
    args = parser.parse_args()
    setup_logging(args)

    projects = load_projects(args.config)
    cf_cidrs = get_cloudflare_cidrs()
    all_skipped: list[str] = []
    all_failed: list[str] = []
    for idx, project in enumerate(projects, start=1):
        outcome = update_project(project=project, cf_cidrs=cf_cidrs, project_index=idx)
        all_skipped.extend(outcome.skipped)
        all_failed.extend(outcome.failed)

    if all_failed or all_skipped:
        parts: list[str] = []
        if all_failed:
            parts.append(f"failed: {', '.join(all_failed)}")
        if all_skipped:
            parts.append(f"not found: {', '.join(all_skipped)}")
        log_error_and_exit(f"Some firewalls were not updated ({'; '.join(parts)})")


if __name__ == "__main__":  # pragma: no cover
    main()  # pragma: no cover

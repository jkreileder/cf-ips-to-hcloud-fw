from __future__ import annotations

import logging
import os
import stat
import sys

import yaml
from pydantic import TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import Project


def _validate_config_permissions(config_file: str) -> None:
    """Reject group/world-accessible config files on Unix-like platforms.

    Args:
        config_file: Absolute or relative path to the YAML config file.
    """
    if os.name != "posix" or not os.path.exists(config_file):
        return

    try:
        mode = stat.S_IMODE(os.stat(config_file).st_mode)
    except OSError as e:
        log_error_and_exit(
            f"Couldn't check permissions of config file {config_file!r}: {e}"
        )

    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        log_error_and_exit(
            f"Config file {config_file!r} has insecure permissions "
            f"({mode:o}); group/other write bits are not allowed."
        )

    if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IXGRP | stat.S_IXOTH):
        logging.warning(
            f"Config file {config_file!r} permissions are permissive ({mode:o}); "
            "consider owner-only access (for example 600) when possible."
        )


def read_config(config_file: str) -> list[Project]:
    """Load and validate project definitions from a YAML file.

    Args:
        config_file: Absolute or relative path to the YAML config file.

    Returns:
        list[Project]: Ordered list of validated project definitions.
    """
    _validate_config_permissions(config_file)

    try:
        with open(config_file, encoding="utf-8") as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        log_error_and_exit(f"Config file {config_file!r} not found.")
    except IsADirectoryError:
        log_error_and_exit(f"Config file {config_file!r} is a directory.")
    except PermissionError:
        log_error_and_exit(f"Config file {config_file!r} is unreadable.")
    except yaml.YAMLError as e:
        log_error_and_exit(f"Error reading config file {config_file!r}: {e}")

    try:
        projects = TypeAdapter(list[Project]).validate_python(config)
    except ValidationError as e:
        log_error_and_exit(f"Config file {config_file!r} is broken: {e}")

    if not projects:
        logging.warning(f"Config file {config_file!r} contains no projects - exiting")
        sys.exit(0)

    return projects

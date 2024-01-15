from __future__ import annotations

import logging
import sys

import yaml
from pydantic import TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import Project


def read_config(config_file: str) -> list[Project]:
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

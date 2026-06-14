from __future__ import annotations

import logging
import os
import stat
import sys

import yaml
from pydantic import SecretStr, TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import Project

ENV_TOKEN = "HCLOUD_TOKEN"  # noqa: S105 # env var name, not a secret value
ENV_FIREWALLS = "HCLOUD_FIREWALLS"
DEFAULT_CONFIG_FILE = "config.yaml"


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
        sanitized_errors = e.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )
        log_error_and_exit(f"Config file {config_file!r} is broken: {sanitized_errors}")

    if not projects:
        logging.warning(f"Config file {config_file!r} contains no projects - exiting")
        sys.exit(0)

    return projects


def read_config_from_env() -> list[Project]:
    """Build a single-project config from environment variables.

    Used when no config file is given. Reads the API token from ``HCLOUD_TOKEN``
    and a comma-separated firewall list from ``HCLOUD_FIREWALLS``, so the common
    single-project Docker/Kubernetes case needs no config file on disk.

    Returns:
        list[Project]: A single-element list with the env-derived project.
    """
    token = os.environ.get(ENV_TOKEN)
    if not token:
        log_error_and_exit(
            f"No configuration found and {ENV_TOKEN} is not set; provide -c "
            f"CONFIGFILE or a {DEFAULT_CONFIG_FILE!r} file, or set {ENV_TOKEN} "
            f"and {ENV_FIREWALLS}."
        )

    firewalls = [
        fw.strip() for fw in os.environ.get(ENV_FIREWALLS, "").split(",") if fw.strip()
    ]
    if not firewalls:
        log_error_and_exit(
            f"{ENV_FIREWALLS} is empty; set it to a comma-separated list of "
            "firewall names (for example 'fw-1,fw-2')."
        )

    return [Project(token=SecretStr(token), firewalls=firewalls)]


def load_projects(config_file: str | None) -> list[Project]:
    """Resolve the project list from the CLI flag, a default file, or env vars.

    Precedence:

    1. An explicit ``config_file`` (``-c``) is the sole source.
    2. Otherwise a ``config.yaml`` in the working directory, if present. This
       keeps mounted-file Docker/Kubernetes setups working with the image's
       default command and avoids an ambient ``HCLOUD_TOKEN`` (a shared variable
       name) silently overriding a real config file.
    3. Otherwise the ``HCLOUD_TOKEN``/``HCLOUD_FIREWALLS`` environment variables.

    Args:
        config_file: Explicit config path from ``-c``, or None when not given.

    Returns:
        list[Project]: Ordered list of validated project definitions.
    """
    if config_file is not None:
        return read_config(config_file)
    if os.path.exists(DEFAULT_CONFIG_FILE):
        return read_config(DEFAULT_CONFIG_FILE)
    return read_config_from_env()

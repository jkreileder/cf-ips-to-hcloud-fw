"""Resolve project definitions from a config file or environment variables."""

from __future__ import annotations

import logging
import os
import stat
import sys

# coverage.py's sys.monitoring tracer (Python 3.14) calls os.stat while tracing;
# binding stat under a private name lets tests patch config's own lookup without
# intercepting those tracer calls. See test_read_config_permission_stat_error.
from os import stat as _os_stat

import yaml
from pydantic import SecretStr, TypeAdapter, ValidationError

from cf_ips_to_hcloud_fw.custom_logging import log_error_and_exit
from cf_ips_to_hcloud_fw.models import Project

ENV_TOKEN = "HCLOUD_TOKEN"  # ruff:ignore[hardcoded-password-string] # env var name, not a secret value
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
        mode = stat.S_IMODE(_os_stat(config_file).st_mode)
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


def _describe_yaml_error(e: yaml.YAMLError) -> str:
    """Summarize a YAML parse failure without echoing the file's contents.

    ``yaml.MarkedYAMLError.__str__`` embeds ``Mark.get_snippet()``, a verbatim
    copy of the offending source line. When the syntax error sits on or next to
    the ``token:`` line - an unterminated quote, a stray tab, an unclosed flow
    mapping - that snippet writes the raw Hetzner API token straight into the
    log stream, which is typically readable by far more principals than the
    config file itself. PyYAML's ``context``/``problem`` strings are static
    descriptions that interpolate at most a single offending character, and the
    marks carry line/column numbers, so both are safe to report; the snippets
    are not. This mirrors the ``include_input=False`` redaction already applied
    to the Pydantic validation errors below.

    Args:
        e: Exception raised while parsing the config file.

    Returns:
        str: What failed and where, free of file contents.
    """
    detail = ": ".join(
        str(part)
        for part in (getattr(e, "context", None), getattr(e, "problem", None))
        if part
    )
    # ReaderError and bare YAMLErrors carry no marks; fall back to the position
    # being unknown rather than raising while handling an error.
    mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
    location = (
        f" at line {mark.line + 1}, column {mark.column + 1}"
        if mark is not None
        else ""
    )
    return f"{detail or type(e).__name__}{location}"


def _read_config(config_file: str) -> list[Project]:
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
        log_error_and_exit(
            f"Error reading config file {config_file!r}: {_describe_yaml_error(e)}"
        )

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


def _read_config_from_env() -> list[Project]:
    """Build a single-project config from environment variables.

    Used when no config file is given. Reads the API token from ``HCLOUD_TOKEN``
    and a newline-separated firewall list from ``HCLOUD_FIREWALLS``, so the common
    single-project Docker/Kubernetes case needs no config file on disk. Newlines
    are used as the separator because firewall names may contain commas and
    spaces but never newlines.

    Returns:
        list[Project]: A single-element list with the env-derived project.
    """
    token = os.environ.get(ENV_TOKEN)
    if not token:
        log_error_and_exit(
            f"No configuration found and {ENV_TOKEN} is not set; provide -c "
            f"CONFIGFILE or a {DEFAULT_CONFIG_FILE!r} file, or set {ENV_TOKEN} "
            f"and {ENV_FIREWALLS} (one firewall name per line)."
        )

    firewalls = [
        fw.strip()
        for fw in os.environ.get(ENV_FIREWALLS, "").splitlines()
        if fw.strip()
    ]
    if not firewalls:
        log_error_and_exit(
            f"{ENV_FIREWALLS} is empty; set it to a newline-separated list of "
            "firewall names (one name per line)."
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
        return _read_config(config_file)
    if os.path.exists(DEFAULT_CONFIG_FILE):
        return _read_config(DEFAULT_CONFIG_FILE)
    return _read_config_from_env()

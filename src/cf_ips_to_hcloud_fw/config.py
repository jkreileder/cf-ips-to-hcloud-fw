"""Resolve project definitions from a config file or environment variables."""

from __future__ import annotations

import logging
import os
import stat

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
    config file itself.

    The parser's own ``context``/``problem`` descriptions are no safer: PyYAML
    interpolates source-derived identifiers into some of them, so a stray ``*``
    or ``&`` in front of the value - a mangled template render, a bad paste -
    makes the token an alias, anchor, or tag handle that lands in the message
    verbatim ("found undefined alias '<token>'"). Which strings do that varies
    by PyYAML version, so rather than auditing them, report only the error type
    and position: neither can carry file contents at any version. This mirrors
    the ``include_input=False`` redaction already applied to the Pydantic
    validation errors below.

    Args:
        e: Exception raised while parsing the config file.

    Returns:
        str: What failed and where, free of file contents.
    """
    # ReaderError and bare YAMLErrors carry no marks; fall back to the position
    # being unknown rather than raising while handling an error.
    mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
    location = (
        f" at line {mark.line + 1}, column {mark.column + 1}"
        if mark is not None
        else ""
    )
    return f"{type(e).__name__}{location}"


def _describe_validation_errors(e: ValidationError) -> list[dict[str, object]]:
    """Summarize validation errors without echoing file-derived strings.

    ``include_input=False`` keeps the offending *values* out of the message,
    but every ``loc`` still names the mapping keys on the way to the error,
    and because :class:`Project` forbids unknown keys, an unknown key is
    reported verbatim. A mistyped config can put the token in key position -
    ``{token:<TOKEN>, …}`` with no space after the colon is a single flow-mapping
    key, and a token pasted on a line of its own as ``<TOKEN>: x`` is a key too -
    so the key names are file contents just as much as the values are.

    The config is a ``list[Project]``, so a ``loc`` has at most three parts:
    the project's index, a ``Project`` field name, and for ``firewalls`` the
    entry's index. Keep exactly those, which carry no file-derived text, and
    replace everything else with a fixed placeholder. Filtering by position
    rather than by type matters because YAML keys need not be strings: a key
    the parser reads as an int or a bool is reported in ``loc`` as that value,
    so an all-digit token in key position would otherwise pass as an "index".

    ``type`` is one of Pydantic's fixed identifiers. ``msg`` is fixed too for
    every error ``Project`` can raise today, but a ``value_error`` or
    ``assertion_error`` carries the validator's own message, which the
    validator idiom in :mod:`models` builds from the input; withhold those so
    the invariant does not depend on how a future validator phrases its error.

    Args:
        e: The validation error raised for the parsed config.

    Returns:
        list[dict[str, object]]: One entry per error (``type``, ``loc``,
        ``msg``), with ``loc`` and ``msg`` sanitized.
    """
    known = Project.model_fields.keys()

    def is_index(part: object) -> bool:
        return isinstance(part, int) and not isinstance(part, bool)

    def sanitize_loc(loc: tuple[int | str, ...]) -> tuple[int | str, ...]:
        # One predicate per position: project index, field name, firewall index.
        keep = (
            is_index,
            lambda part: isinstance(part, str) and part in known,
            lambda part: loc[1] == "firewalls" and is_index(part),
        )
        return tuple(
            part if position < len(keep) and keep[position](part) else "<unknown key>"
            for position, part in enumerate(loc)
        )

    def sanitize_msg(err_type: str, msg: str) -> str:
        if err_type in {"value_error", "assertion_error"}:
            return "<message withheld: may quote the input>"
        return msg

    return [
        {
            "type": err["type"],
            "loc": sanitize_loc(err["loc"]),
            "msg": sanitize_msg(err["type"], err["msg"]),
        }
        for err in e.errors(
            include_url=False, include_context=False, include_input=False
        )
    ]


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
        log_error_and_exit(
            f"Config file {config_file!r} is broken: {_describe_validation_errors(e)}"
        )

    if not projects:
        # Non-zero, not a clean exit. An empty list is a valid YAML document, so
        # a truncated file or a mis-rendered template validates fine and syncs
        # nothing; exiting 0 told every exit-code-keyed monitor - systemd,
        # a Kubernetes CronJob, a cron wrapper - that the run was healthy while
        # the firewall rules quietly froze at their last-synced state. The
        # env-var path already fails loudly for the same condition.
        log_error_and_exit(
            f"Config file {config_file!r} contains no projects - no firewalls "
            "would be synced. Add at least one project entry."
        )

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
    # Stripped before the guard, not after: the model strips the token too, so
    # a variable holding only a newline (HCLOUD_TOKEN=$(cat secret-file) on an
    # otherwise-empty file) would otherwise slip past this check and surface as
    # a 401 on every firewall instead of the actionable message below.
    token = (os.environ.get(ENV_TOKEN) or "").strip()
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

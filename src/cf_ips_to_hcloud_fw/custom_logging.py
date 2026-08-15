"""Logging setup and error helpers shared across the package."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:  # pragma: no cover
    import argparse  # pragma: no cover

REDACTED = "[REDACTED]"

# Values that must never reach the log stream, registered once at the point the
# credential is first used. Third-party exception text is the reason this
# exists: an hcloud token with a trailing newline (routine for a Kubernetes
# secret mounted as a file) makes requests raise InvalidHeader carrying the
# whole `Authorization: Bearer <token>` value, and the per-firewall handlers
# log the exception verbatim so the run can continue. Scrubbing centrally means
# a new call site cannot forget, and covers any future SDK that decides to put
# the credential in a message.
_secrets: set[str] = set()


def register_secret(secret: str) -> None:
    """Mark a value for redaction from all subsequent error output.

    Args:
        secret: The literal value to scrub. Blank values are ignored, since
            scrubbing the empty string would rewrite every message.
    """
    if secret and secret.strip():
        _secrets.add(secret)


def forget_secrets() -> None:
    """Drop every registered secret. For tests."""
    _secrets.clear()


def redact(msg: str) -> str:
    """Replace every registered secret in `msg` with a placeholder.

    Args:
        msg: Text about to be logged.

    Returns:
        str: The text with any registered secret masked.
    """
    # Longest first: with two projects configured, a shorter token that happens
    # to be a prefix of a longer one would otherwise be substituted first and
    # destroy the longer match, leaking its tail. Set iteration order is
    # arbitrary, so without this the failure would be nondeterministic.
    for secret in sorted(_secrets, key=len, reverse=True):
        msg = msg.replace(secret, REDACTED)
    return msg


def setup_logging(args: argparse.Namespace) -> None:
    """Configure root logging with optional debug-level verbosity.

    Args:
        args: Parsed CLI arguments that include the `debug` flag.
    """
    logging.basicConfig(
        level=logging.getLevelName(logging.DEBUG if args.debug else logging.INFO),
        format=(
            "%(asctime)s %(levelname)-8s "
            + ("[%(filename)s:%(funcName)s:%(lineno)d] " if args.debug else "")
            + "%(message)s"
        ),
    )


def log_error(msg: str) -> None:
    """Emit an error without terminating the process.

    Use for recoverable failures that should be recorded but allow the run to
    continue (for example, one firewall failing while others still sync).

    Args:
        msg: Pre-formatted error message to log.
    """
    logging.error(redact(msg))


def log_error_and_exit(msg: str) -> NoReturn:
    """Emit an error and terminate the process with exit code 1.

    Args:
        msg: Pre-formatted error message to log before exiting.
    """
    log_error(msg)
    sys.exit(1)

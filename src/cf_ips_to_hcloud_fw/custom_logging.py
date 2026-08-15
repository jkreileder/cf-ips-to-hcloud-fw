"""Logging setup and error helpers shared across the package."""

from __future__ import annotations

import logging
import re
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
# Compiled at registration rather than matched per call. Two reasons: the
# alternation is built once instead of re-sorted on every log line, and the
# secret is consumed by re.compile here instead of appearing as an argument at
# the point of logging - so a taint analyser does not read the scrubber as a
# path from credential to log sink, which is the opposite of what it does.
# Held in a one-element list so the binding is mutated in place rather than
# rebound, matching how `_secrets` above is updated and avoiding a `global`.
_pattern: list[re.Pattern[str] | None] = [None]


def _rebuild_pattern() -> None:
    """Recompile the alternation after the registry changes."""
    if not _secrets:
        _pattern[0] = None
        return
    # Longest first: alternation matches leftmost-first, so a shorter token
    # that happens to prefix a longer one would otherwise match first and
    # leave the longer token's tail in the output.
    _pattern[0] = re.compile(
        "|".join(re.escape(s) for s in sorted(_secrets, key=len, reverse=True))
    )


def register_secret(secret: str) -> None:
    """Mark a value for redaction from all subsequent error output.

    Args:
        secret: The literal value to scrub. Blank values are ignored, since
            scrubbing the empty string would rewrite every message.
    """
    if secret and secret.strip():
        _secrets.add(secret)
        _rebuild_pattern()


def forget_secrets() -> None:
    """Drop every registered secret. For tests."""
    _secrets.clear()
    _rebuild_pattern()


def redact(msg: str) -> str:
    """Replace every registered secret in `msg` with a placeholder.

    Args:
        msg: Text about to be logged.

    Returns:
        str: The text with any registered secret masked.
    """
    pattern = _pattern[0]
    return pattern.sub(REDACTED, msg) if pattern else msg


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

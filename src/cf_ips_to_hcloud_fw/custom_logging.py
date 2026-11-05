"""Logging setup and error helpers shared across the package."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:  # pragma: no cover
    import argparse  # pragma: no cover


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


def _escape_control_characters(text: str) -> str:
    """Make a message safe to log on one line.

    Error text often comes from outside the process: an API's error body or
    reason phrase, an OS error, a parser's description. A newline in it would
    end the log line and let the rest pose as a log entry of its own. Escape
    control characters, and the backslash as well, so an escaped newline stays
    distinguishable from a literal backslash-n in the original text.

    Args:
        text: The message as composed.

    Returns:
        str: The message with every control character and backslash escaped.
    """
    return "".join(
        ch if ch.isprintable() and ch != "\\" else repr(ch)[1:-1] for ch in text
    )


def log_error(msg: str) -> None:
    """Emit an error without terminating the process.

    Use for recoverable failures that should be recorded but allow the run to
    continue (for example, one firewall failing while others still sync).
    Every error line passes through here, so this is where the message is
    made safe for a single log line; see :func:`_escape_control_characters`.

    Args:
        msg: Pre-formatted error message to log.
    """
    logging.error(_escape_control_characters(msg))


def log_error_and_exit(msg: str) -> NoReturn:
    """Emit an error and terminate the process with exit code 1.

    Args:
        msg: Pre-formatted error message to log before exiting.
    """
    log_error(msg)
    sys.exit(1)

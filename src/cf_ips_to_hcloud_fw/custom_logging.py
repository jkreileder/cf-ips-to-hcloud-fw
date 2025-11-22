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


def log_error_and_exit(msg: str) -> NoReturn:
    """Emit an error and terminate the process with exit code 1.

    Args:
        msg: Pre-formatted error message to log before exiting.
    """
    logging.error(msg)
    sys.exit(1)

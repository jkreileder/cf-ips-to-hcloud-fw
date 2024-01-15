from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:  # pragma: no cover
    import argparse  # pragma: no cover


def setup_logging(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.getLevelName(logging.DEBUG if args.debug else logging.INFO),
        format=(
            "%(asctime)s %(levelname)-8s "
            + ("[%(filename)s:%(funcName)s:%(lineno)d] " if args.debug else "")
            + "%(message)s"
        ),
    )


def log_error_and_exit(msg: str) -> NoReturn:
    logging.error(msg)
    sys.exit(1)

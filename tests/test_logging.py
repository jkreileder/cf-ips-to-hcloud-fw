from __future__ import annotations

import argparse
import logging
from unittest.mock import MagicMock, patch

from cf_ips_to_hcloud_fw.logging import setup_logging


@patch("logging.basicConfig")
def test_setup_logging_debug(mock_basic_config: MagicMock) -> None:
    args = argparse.Namespace(debug=True)
    setup_logging(args)
    mock_basic_config.assert_called_once_with(
        level=logging.getLevelName(logging.DEBUG),
        format="%(asctime)s %(levelname)-8s "
        "[%(filename)s:%(funcName)s:%(lineno)d] %(message)s",
    )


@patch("logging.basicConfig")
def test_setup_logging_info(mock_basic_config: MagicMock) -> None:
    args = argparse.Namespace(debug=False)
    setup_logging(args)
    mock_basic_config.assert_called_once_with(
        level=logging.getLevelName(logging.INFO),
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

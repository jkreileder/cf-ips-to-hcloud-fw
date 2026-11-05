"""Tests for logging setup and error helpers."""

from __future__ import annotations

import argparse
import logging
from unittest.mock import MagicMock, patch

import pytest

from cf_ips_to_hcloud_fw.custom_logging import log_error, setup_logging


@patch("logging.basicConfig")
def test_setup_logging_debug(mock_basic_config: MagicMock) -> None:
    """setup_logging should enable DEBUG formatting when the flag is set."""
    args = argparse.Namespace(debug=True)
    setup_logging(args)
    mock_basic_config.assert_called_once_with(
        level=logging.getLevelName(logging.DEBUG),
        format="%(asctime)s %(levelname)-8s "
        "[%(filename)s:%(funcName)s:%(lineno)d] %(message)s",
    )


@patch("logging.basicConfig")
def test_setup_logging_info(mock_basic_config: MagicMock) -> None:
    """setup_logging should default to INFO formatting when debug is False."""
    args = argparse.Namespace(debug=False)
    setup_logging(args)
    mock_basic_config.assert_called_once_with(
        level=logging.getLevelName(logging.INFO),
        format="%(asctime)s %(levelname)-8s %(message)s",
    )


@pytest.mark.parametrize(
    ("message", "logged"),
    [
        ("plain text", "plain text"),
        ("one\ntwo", "one\\ntwo"),
        ("tab\there\r\n", "tab\\there\\r\\n"),
        ("a\\nb", "a\\\\nb"),  # a literal backslash-n stays distinguishable
        ("bell\x07 and esc\x1b[0m", "bell\\x07 and esc\\x1b[0m"),
        ("umlaut ü stays", "umlaut ü stays"),
    ],
)
@patch("logging.error")
def test_log_error_keeps_the_message_on_one_line(
    mock_logging: MagicMock, message: str, logged: str
) -> None:
    """Control characters and backslashes are escaped; printable text is untouched."""
    log_error(message)
    mock_logging.assert_called_once_with(logged)

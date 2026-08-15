"""Tests for logging setup and error helpers."""

from __future__ import annotations

import argparse
import logging
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.exceptions import RequestException

from cf_ips_to_hcloud_fw.custom_logging import (
    REDACTED,
    log_error,
    log_error_and_exit,
    redact,
    register_secret,
    setup_logging,
)

# ruff: ignore[hardcoded-password-string] — synthetic test value
SECRET = "hcloud-SUPER_SECRET_TOKEN_VALUE"


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


def test_redact_masks_registered_secret() -> None:
    """A registered secret is replaced wherever it appears."""
    register_secret(SECRET)
    assert redact(f"failed: {SECRET} and again {SECRET}") == (
        f"failed: {REDACTED} and again {REDACTED}"
    )


def test_redact_is_a_noop_without_registration() -> None:
    """Nothing is rewritten until a secret is registered."""
    assert redact(f"failed: {SECRET}") == f"failed: {SECRET}"


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_secrets_are_ignored(blank: str) -> None:
    """Registering a blank value must not rewrite every message."""
    register_secret(blank)
    assert redact("an ordinary message") == "an ordinary message"


@patch("logging.error")
def test_log_error_redacts(mock_logging: MagicMock) -> None:
    """log_error scrubs registered secrets before emitting."""
    register_secret(SECRET)
    log_error(f"hcloud call failed: {SECRET}")
    assert SECRET not in mock_logging.call_args[0][0]
    assert REDACTED in mock_logging.call_args[0][0]


@patch("logging.error")
def test_log_error_and_exit_redacts(mock_logging: MagicMock) -> None:
    """The exiting variant goes through the same scrubbing."""
    register_secret(SECRET)
    with pytest.raises(SystemExit) as e:
        log_error_and_exit(f"fatal: {SECRET}")
    assert e.value.code == 1
    assert SECRET not in mock_logging.call_args[0][0]


@patch("logging.error")
def test_log_error_redacts_real_invalid_header_exception(
    mock_logging: MagicMock,
) -> None:
    """Redact the real InvalidHeader exception, not a hand-written string.

    A token with a trailing newline makes requests raise InvalidHeader
    carrying the whole Authorization value.

    Exercises the real exception rather than a hand-written string, so the test
    still holds if requests changes its message format.
    """
    register_secret(SECRET)
    with pytest.raises(RequestException) as excinfo:
        requests.get(
            "http://127.0.0.1:9/x",
            headers={"Authorization": f"Bearer {SECRET}\n"},
            timeout=1,
        )
    raw = str(excinfo.value)
    assert SECRET in raw  # the exception really does carry the token

    log_error(f"hcloud/firewalls.get_by_name failed for 'fw' in project 1: {raw}")
    assert SECRET not in mock_logging.call_args[0][0]


def test_redact_prefers_the_longest_secret() -> None:
    """A shorter secret must not partially unmask a longer one.

    With two projects configured, one token can be a prefix of another. Set
    iteration order is arbitrary, so replacing the short one first would leak
    the longer token's tail nondeterministically.
    """
    register_secret("abc123")
    register_secret("abc123def456")
    assert redact("err: Bearer abc123def456") == f"err: Bearer {REDACTED}"
    assert redact("err: Bearer abc123") == f"err: Bearer {REDACTED}"

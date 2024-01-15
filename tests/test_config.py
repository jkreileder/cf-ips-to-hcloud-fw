from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import SecretStr

from cf_ips_to_hcloud_fw.config import read_config
from cf_ips_to_hcloud_fw.models import Project


@patch("builtins.open", side_effect=FileNotFoundError("config.yaml"))
@patch("logging.error")
def test_read_config_file_not_found(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_open.assert_called_once_with("config.yaml", encoding="utf-8")
    mock_logging.assert_called_once_with("Config file 'config.yaml' not found.")


@patch("builtins.open", side_effect=IsADirectoryError("config.yaml"))
@patch("logging.error")
def test_read_config_file_is_a_directory(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_open.assert_called_once_with("config.yaml", encoding="utf-8")
    mock_logging.assert_called_once_with("Config file 'config.yaml' is a directory.")


@patch("builtins.open", side_effect=PermissionError("config.yaml"))
@patch("logging.error")
def test_read_config_file_is_unreadable(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_open.assert_called_once_with("config.yaml", encoding="utf-8")
    mock_logging.assert_called_once_with("Config file 'config.yaml' is unreadable.")


@patch("builtins.open", mock_open())
@patch("logging.error")
def test_read_config_empty(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Config file 'config.yaml' is broken: " in mock_logging.call_args[0][0]


@patch("builtins.open", mock_open(read_data="[]"))
@patch("logging.warning")
def test_read_config_empty_list(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 0
    mock_logging.assert_called_once_with(
        "Config file 'config.yaml' contains no projects - exiting",
    )


@patch("builtins.open", mock_open(read_data="v: ]["))
@patch("logging.error")
def test_read_config_broken_yaml(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Error reading config file 'config.yaml': " in mock_logging.call_args[0][0]


@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: token
  firewalls:
    - fw-1
""",
    ),
)
def test_read_config() -> None:
    projects = read_config("config.yaml")
    assert projects == [Project(token=SecretStr("token"), firewalls=["fw-1"])]

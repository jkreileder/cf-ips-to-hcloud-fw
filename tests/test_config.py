from __future__ import annotations

import stat
from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import SecretStr

from cf_ips_to_hcloud_fw.config import read_config
from cf_ips_to_hcloud_fw.models import Project


@patch("cf_ips_to_hcloud_fw.config.os.name", "posix")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=True)
@patch("cf_ips_to_hcloud_fw.config.os.stat")
@patch("logging.error")
def test_read_config_permission_stat_error(
    mock_logging: MagicMock,
    mock_stat: MagicMock,
    mock_exists: MagicMock,
) -> None:
    """Exit with an error when config permission metadata cannot be read."""
    mock_stat.side_effect = OSError("boom")

    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")

    assert e.value.code == 1
    mock_exists.assert_called_once_with("config.yaml")
    mock_stat.assert_called_once_with("config.yaml")
    mock_logging.assert_called_once()
    assert (
        "Couldn't check permissions of config file 'config.yaml': boom"
        in mock_logging.call_args[0][0]
    )


@patch("cf_ips_to_hcloud_fw.config.os.name", "posix")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=True)
@patch("cf_ips_to_hcloud_fw.config.os.stat")
@patch("logging.warning")
def test_read_config_permissive_read_permissions_warn(
    mock_warning: MagicMock,
    mock_stat: MagicMock,
    mock_exists: MagicMock,
) -> None:
    """Allow read-only group access (common for mounted secrets) but warn."""
    mock_stat.return_value = MagicMock(st_mode=stat.S_IFREG | 0o640)

    with patch(
        "builtins.open",
        mock_open(
            read_data="""
- token: token
  firewalls:
    - fw-1
""",
        ),
    ):
        projects = read_config("config.yaml")

    assert projects == [Project(token=SecretStr("token"), firewalls=["fw-1"])]
    mock_exists.assert_called_once_with("config.yaml")
    mock_stat.assert_called_once_with("config.yaml")
    mock_warning.assert_called_once_with(
        "Config file 'config.yaml' permissions are permissive (640); "
        "consider owner-only access (for example 600) when possible."
    )


@patch("cf_ips_to_hcloud_fw.config.os.name", "posix")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=True)
@patch("cf_ips_to_hcloud_fw.config.os.stat")
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
def test_read_config_secure_permissions(
    mock_stat: MagicMock,
    mock_exists: MagicMock,
) -> None:
    """Allow owner-only config files to be parsed normally."""
    mock_stat.return_value = MagicMock(st_mode=stat.S_IFREG | 0o600)

    projects = read_config("config.yaml")

    assert projects == [Project(token=SecretStr("token"), firewalls=["fw-1"])]
    mock_exists.assert_called_once_with("config.yaml")
    mock_stat.assert_called_once_with("config.yaml")


@patch("cf_ips_to_hcloud_fw.config.os.name", "posix")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=True)
@patch("cf_ips_to_hcloud_fw.config.os.stat")
@patch("logging.error")
def test_read_config_group_or_world_writable_permissions_rejected(
    mock_logging: MagicMock,
    mock_stat: MagicMock,
    mock_exists: MagicMock,
) -> None:
    """Reject config files writable by group/others."""
    mock_stat.return_value = MagicMock(st_mode=stat.S_IFREG | 0o666)

    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")

    assert e.value.code == 1
    mock_exists.assert_called_once_with("config.yaml")
    mock_stat.assert_called_once_with("config.yaml")
    mock_logging.assert_called_once_with(
        "Config file 'config.yaml' has insecure permissions (666); "
        "group/other write bits are not allowed."
    )


@patch("builtins.open", side_effect=FileNotFoundError("config.yaml"))
@patch("logging.error")
def test_read_config_file_not_found(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    """Ensure read_config exits cleanly when the config path is missing."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_open.assert_called_once_with("config.yaml", encoding="utf-8")
    mock_logging.assert_called_once_with("Config file 'config.yaml' not found.")


@patch("builtins.open", side_effect=IsADirectoryError("config.yaml"))
@patch("logging.error")
def test_read_config_file_is_a_directory(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    """Detect directories passed as config files and exit."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_open.assert_called_once_with("config.yaml", encoding="utf-8")
    mock_logging.assert_called_once_with("Config file 'config.yaml' is a directory.")


@patch("builtins.open", side_effect=PermissionError("config.yaml"))
@patch("logging.error")
def test_read_config_file_is_unreadable(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    """Verify unreadable files trigger an error log and exit."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_open.assert_called_once_with("config.yaml", encoding="utf-8")
    mock_logging.assert_called_once_with("Config file 'config.yaml' is unreadable.")


@patch("builtins.open", mock_open())
@patch("logging.error")
def test_read_config_empty(mock_logging: MagicMock) -> None:
    """Empty files fail validation and abort execution."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Config file 'config.yaml' is broken: " in mock_logging.call_args[0][0]


@patch("builtins.open", mock_open(read_data="[]"))
@patch("logging.warning")
def test_read_config_empty_list(mock_logging: MagicMock) -> None:
    """Empty project lists exit with code 0 after warning the operator."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 0
    mock_logging.assert_called_once_with(
        "Config file 'config.yaml' contains no projects - exiting",
    )


@patch("builtins.open", mock_open(read_data="v: ]["))
@patch("logging.error")
def test_read_config_broken_yaml(mock_logging: MagicMock) -> None:
    """Malformed YAML surfaces as an error message and exit."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
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
    """Happy-path parsing returns validated Project instances."""
    projects = read_config("config.yaml")
    assert projects == [Project(token=SecretStr("token"), firewalls=["fw-1"])]


@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: token
  firewall_names:
    - fw-1
""",
    ),
)
@patch("logging.error")
def test_read_config_extra_field_rejected(mock_logging: MagicMock) -> None:
    """Config with misspelled or extra fields is rejected due to extra='forbid'."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Config file 'config.yaml' is broken:" in error_msg
    assert "Extra inputs are not permitted" in error_msg
    assert "firewall_names" in error_msg


@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: token
  firewalls:
    - fw-1
  extra_key: extra_value
""",
    ),
)
@patch("logging.error")
def test_read_config_unknown_key_rejected(mock_logging: MagicMock) -> None:
    """Config with unknown keys alongside valid ones is rejected."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Config file 'config.yaml' is broken:" in error_msg
    assert "Extra inputs are not permitted" in error_msg
    assert "extra_key" in error_msg


@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: token
  firewalls: []
""",
    ),
)
@patch("logging.error")
def test_read_config_empty_firewalls_rejected(mock_logging: MagicMock) -> None:
    """Config with empty firewalls list is rejected due to min_length=1."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Config file 'config.yaml' is broken:" in error_msg
    assert "at least 1 item" in error_msg.lower() or "min_length" in error_msg.lower()


@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: token
""",
    ),
)
@patch("logging.error")
def test_read_config_missing_firewalls_rejected(mock_logging: MagicMock) -> None:
    """Config missing required firewalls field is rejected."""
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Config file 'config.yaml' is broken:" in error_msg
    assert "firewalls" in error_msg.lower()
    assert "required" in error_msg.lower() or "missing" in error_msg.lower()

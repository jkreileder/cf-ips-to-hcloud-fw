"""Tests for config resolution from files and environment variables."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import SecretStr

from cf_ips_to_hcloud_fw.config import (
    _read_config,
    _read_config_from_env,
    load_projects,
)
from cf_ips_to_hcloud_fw.models import Project

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path  # pragma: no cover


@patch("cf_ips_to_hcloud_fw.config.os.name", "posix")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=True)
@patch("cf_ips_to_hcloud_fw.config._os_stat")
@patch("logging.error")
def test_read_config_permission_stat_error(
    mock_logging: MagicMock,
    mock_stat: MagicMock,
    mock_exists: MagicMock,
) -> None:
    """Exit with an error when config permission metadata cannot be read."""
    mock_stat.side_effect = OSError("boom")

    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")

    assert e.value.code == 1
    mock_exists.assert_called_once_with("config.yaml")
    mock_stat.assert_called_once_with("config.yaml")
    mock_logging.assert_called_once()
    assert (
        "Couldn't check permissions of config file 'config.yaml': boom"
        in mock_logging.call_args[0][0]
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission semantics")
@patch("logging.warning")
def test_read_config_permissive_read_permissions_warn(
    mock_warning: MagicMock,
    tmp_path: Path,
) -> None:
    """Allow read-only group access (common for mounted secrets) but warn."""
    config = tmp_path / "config.yaml"
    config.write_text(
        """
- token: token
  firewalls:
    - fw-1
""",
        encoding="utf-8",
    )
    config.chmod(0o640)
    config_path = str(config)

    projects = _read_config(config_path)

    assert projects == [Project(token=SecretStr("token"), firewalls=["fw-1"])]
    mock_warning.assert_called_once_with(
        f"Config file {config_path!r} permissions are permissive (640); "
        "consider owner-only access (for example 600) when possible."
    )


@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
def test_read_config_permission_check_skipped_on_non_posix(tmp_path: Path) -> None:
    """Skip POSIX-only permission checks on non-POSIX systems."""
    config = tmp_path / "config.yaml"
    config.write_text(
        """
- token: token
  firewalls:
    - fw-1
""",
        encoding="utf-8",
    )
    # World/group-writable would be rejected on POSIX; with os.name forced to a
    # non-POSIX value the check is skipped and the file parses normally.
    config.chmod(0o666)

    projects = _read_config(str(config))

    assert projects == [Project(token=SecretStr("token"), firewalls=["fw-1"])]


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission semantics")
def test_read_config_secure_permissions(tmp_path: Path) -> None:
    """Allow owner-only config files to be parsed normally."""
    config = tmp_path / "config.yaml"
    config.write_text(
        """
- token: token
  firewalls:
    - fw-1
""",
        encoding="utf-8",
    )
    config.chmod(0o600)

    projects = _read_config(str(config))

    assert projects == [Project(token=SecretStr("token"), firewalls=["fw-1"])]


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission semantics")
@patch("logging.error")
def test_read_config_group_or_world_writable_permissions_rejected(
    mock_logging: MagicMock,
    tmp_path: Path,
) -> None:
    """Reject config files writable by group/others."""
    config = tmp_path / "config.yaml"
    config.write_text(
        """
- token: token
  firewalls:
    - fw-1
""",
        encoding="utf-8",
    )
    config.chmod(0o666)
    config_path = str(config)

    with pytest.raises(SystemExit) as e:
        _read_config(config_path)

    assert e.value.code == 1
    mock_logging.assert_called_once_with(
        f"Config file {config_path!r} has insecure permissions "
        "(666); group/other write bits are not allowed."
    )


@patch("builtins.open", side_effect=FileNotFoundError("config.yaml"))
@patch("logging.error")
def test_read_config_file_not_found(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    """Ensure _read_config exits cleanly when the config path is missing."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")
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
        _read_config("config.yaml")
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
        _read_config("config.yaml")
    assert e.value.code == 1
    mock_open.assert_called_once_with("config.yaml", encoding="utf-8")
    mock_logging.assert_called_once_with("Config file 'config.yaml' is unreadable.")


@patch("builtins.open", mock_open())
@patch("logging.error")
def test_read_config_empty(mock_logging: MagicMock) -> None:
    """Empty files fail validation and abort execution."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Config file 'config.yaml' is broken: " in mock_logging.call_args[0][0]


@patch("builtins.open", mock_open(read_data="[]"))
@patch("logging.warning")
def test_read_config_empty_list(mock_logging: MagicMock) -> None:
    """Empty project lists exit with code 0 after warning the operator."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")
    assert e.value.code == 0
    mock_logging.assert_called_once_with(
        "Config file 'config.yaml' contains no projects - exiting",
    )


@patch("builtins.open", mock_open(read_data="v: ]["))
@patch("logging.error")
def test_read_config_broken_yaml(mock_logging: MagicMock) -> None:
    """Malformed YAML surfaces as an error message and exit."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")
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
    projects = _read_config("config.yaml")
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
        _read_config("config.yaml")
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
        _read_config("config.yaml")
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
        _read_config("config.yaml")
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
        _read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Config file 'config.yaml' is broken:" in error_msg
    assert "firewalls" in error_msg.lower()
    assert "required" in error_msg.lower() or "missing" in error_msg.lower()


@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: SUPER_SECRET_TOKEN_VALUE
  firewalls: []
""",
    ),
)
@patch("logging.error")
def test_read_config_validation_error_redacts_secret_value(
    mock_logging: MagicMock,
) -> None:
    """Validation error logs must not include raw token values."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")

    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Config file 'config.yaml' is broken:" in error_msg
    assert "SUPER_SECRET_TOKEN_VALUE" not in error_msg


@patch.dict(
    "os.environ",
    {"HCLOUD_TOKEN": "env-token", "HCLOUD_FIREWALLS": "fw-1\nfw-2"},
    clear=True,
)
def test_read_config_from_env() -> None:
    """A token and newline-separated firewall list build a single project."""
    projects = _read_config_from_env()
    assert projects == [
        Project(token=SecretStr("env-token"), firewalls=["fw-1", "fw-2"])
    ]


@patch.dict(
    "os.environ",
    {"HCLOUD_TOKEN": "env-token", "HCLOUD_FIREWALLS": " fw-1 \n \nfw-2 \n"},
    clear=True,
)
def test_read_config_from_env_trims_and_filters_firewalls() -> None:
    """Whitespace is trimmed and blank lines dropped from the firewall list."""
    projects = _read_config_from_env()
    assert projects == [
        Project(token=SecretStr("env-token"), firewalls=["fw-1", "fw-2"])
    ]


@patch.dict(
    "os.environ",
    {
        "HCLOUD_TOKEN": "env-token",
        "HCLOUD_FIREWALLS": "ICMP, SSH 222 IPv6, Cloudflare\nfw-2",
    },
    clear=True,
)
def test_read_config_from_env_keeps_commas_and_spaces_in_names() -> None:
    """Firewall names may contain commas and spaces; newlines separate entries."""
    projects = _read_config_from_env()
    assert projects == [
        Project(
            token=SecretStr("env-token"),
            firewalls=["ICMP, SSH 222 IPv6, Cloudflare", "fw-2"],
        )
    ]


@patch.dict("os.environ", {"HCLOUD_FIREWALLS": "fw-1"}, clear=True)
@patch("logging.error")
def test_read_config_from_env_missing_token(mock_logging: MagicMock) -> None:
    """A missing HCLOUD_TOKEN exits with a helpful error."""
    with pytest.raises(SystemExit) as e:
        _read_config_from_env()
    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "HCLOUD_TOKEN is not set" in error_msg


@patch.dict("os.environ", {"HCLOUD_TOKEN": "env-token"}, clear=True)
@patch("logging.error")
def test_read_config_from_env_missing_firewalls(mock_logging: MagicMock) -> None:
    """A token without any firewalls exits with a helpful error."""
    with pytest.raises(SystemExit) as e:
        _read_config_from_env()
    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "HCLOUD_FIREWALLS is empty" in error_msg


@patch.dict(
    "os.environ",
    {"HCLOUD_TOKEN": "SUPER_SECRET_TOKEN_VALUE", "HCLOUD_FIREWALLS": " \n \n "},
    clear=True,
)
@patch("logging.error")
def test_read_config_from_env_blank_firewalls_redacts_token(
    mock_logging: MagicMock,
) -> None:
    """The firewalls error must not leak the token value."""
    with pytest.raises(SystemExit) as e:
        _read_config_from_env()
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "SUPER_SECRET_TOKEN_VALUE" not in mock_logging.call_args[0][0]


@patch("cf_ips_to_hcloud_fw.config._read_config_from_env")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists")
@patch("cf_ips_to_hcloud_fw.config._read_config")
def test_load_projects_explicit_config_wins(
    mock_read_config: MagicMock,
    mock_exists: MagicMock,
    mock_read_env: MagicMock,
) -> None:
    """An explicit -c path is the sole source; no default-file or env lookup."""
    mock_read_config.return_value = [Project(token=SecretStr("t"), firewalls=["fw"])]
    result = load_projects("custom.yaml")
    assert result is mock_read_config.return_value
    mock_read_config.assert_called_once_with("custom.yaml")
    mock_exists.assert_not_called()
    mock_read_env.assert_not_called()


@patch("cf_ips_to_hcloud_fw.config._read_config_from_env")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=True)
@patch("cf_ips_to_hcloud_fw.config._read_config")
def test_load_projects_default_file_used(
    mock_read_config: MagicMock,
    mock_exists: MagicMock,
    mock_read_env: MagicMock,
) -> None:
    """With no -c, a present config.yaml is used before the env fallback."""
    mock_read_config.return_value = [Project(token=SecretStr("t"), firewalls=["fw"])]
    result = load_projects(None)
    assert result is mock_read_config.return_value
    mock_exists.assert_called_once_with("config.yaml")
    mock_read_config.assert_called_once_with("config.yaml")
    mock_read_env.assert_not_called()


@patch.dict(
    "os.environ",
    {"HCLOUD_TOKEN": "env-token", "HCLOUD_FIREWALLS": "fw-1"},
    clear=True,
)
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=True)
@patch("cf_ips_to_hcloud_fw.config._read_config_from_env")
@patch("cf_ips_to_hcloud_fw.config._read_config")
def test_load_projects_file_beats_env(
    mock_read_config: MagicMock,
    mock_read_env: MagicMock,
    mock_exists: MagicMock,
) -> None:
    """A present config.yaml takes precedence over set environment variables."""
    mock_read_config.return_value = [Project(token=SecretStr("t"), firewalls=["fw"])]
    load_projects(None)
    mock_exists.assert_called_once_with("config.yaml")
    mock_read_config.assert_called_once_with("config.yaml")
    mock_read_env.assert_not_called()


@patch("cf_ips_to_hcloud_fw.config._read_config")
@patch("cf_ips_to_hcloud_fw.config.os.path.exists", return_value=False)
@patch("cf_ips_to_hcloud_fw.config._read_config_from_env")
def test_load_projects_env_fallback(
    mock_read_env: MagicMock,
    mock_exists: MagicMock,
    mock_read_config: MagicMock,
) -> None:
    """With no -c and no config.yaml, the env-var path is used."""
    mock_read_env.return_value = [Project(token=SecretStr("t"), firewalls=["fw"])]
    result = load_projects(None)
    assert result is mock_read_env.return_value
    mock_exists.assert_called_once_with("config.yaml")
    mock_read_config.assert_not_called()
    mock_read_env.assert_called_once_with()

"""Tests for config resolution from files and environment variables."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Annotated
from unittest.mock import MagicMock, mock_open, patch

import pytest
import yaml
from pydantic import AfterValidator, BaseModel, SecretStr, ValidationError

from cf_ips_to_hcloud_fw.config import (
    ENV_TOKEN,
    _describe_validation_errors,
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
@patch("logging.error")
def test_read_config_empty_list(mock_logging: MagicMock) -> None:
    """An empty project list fails the run rather than reporting success.

    `[]` is a valid YAML document, so a truncated file or a mis-rendered
    template validates cleanly and syncs nothing. Exiting 0 would tell an
    exit-code-keyed monitor the run was healthy while the firewall rules froze.
    """
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")
    assert e.value.code == 1
    mock_logging.assert_called_once_with(
        "Config file 'config.yaml' contains no projects - no firewalls would "
        "be synced. Add at least one project entry."
    )


# The text stream decodes in chunks of 8 KiB, so an offset taken from its error
# is only right inside the first chunk; the second case puts the bad byte past
# that boundary.
@pytest.mark.parametrize("padding", [0, 2000], ids=["first-chunk", "later-chunk"])
@patch("logging.error")
def test_read_config_non_utf8_file(
    mock_logging: MagicMock, padding: int, tmp_path: Path
) -> None:
    """A file that is not UTF-8 is reported by file offset, not as a traceback."""
    prefix = b"# padding\n" * padding
    config_file = tmp_path / "config.yaml"
    config_file.write_bytes(
        prefix + b"- token: \xff\xfeSUPER_SECRET\n  firewalls: [fw-1]\n"
    )
    config_file.chmod(0o600)

    with pytest.raises(SystemExit) as e:
        _read_config(str(config_file))

    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert error_msg.endswith(f"is not valid UTF-8 (byte {len(prefix) + 9}).")
    assert "SUPER_SECRET" not in error_msg


@patch(
    "builtins.open",
    mock_open(read_data="- token: t\x00SUPER_SECRET\n  firewalls: [fw-1]\n"),
)
@patch("logging.error")
def test_read_config_control_character_reports_position(
    mock_logging: MagicMock,
) -> None:
    """PyYAML's ReaderError carries a character position, not marks; report it."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")

    assert e.value.code == 1
    error_msg = mock_logging.call_args[0][0]
    assert error_msg == (
        "Error reading config file 'config.yaml': ReaderError at character 10"
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


# Malformations that put the token into PyYAML's own error output, verified
# against PyYAML. The first three land the error marks on the token line, so
# `MarkedYAMLError.__str__` splices in the source snippet. The rest turn the
# token into an identifier that PyYAML interpolates into `problem` itself, so
# forwarding the parser's description would leak it even without the snippet.
LEAKY_YAML = {
    "unterminated-quote": (
        '- token: "SUPER_SECRET_TOKEN_VALUE\n  firewalls:\n    - fw-1\n'
    ),
    "tab-after-key": "- token:\tSUPER_SECRET_TOKEN_VALUE\n  firewalls: [fw-1]\n",
    "unclosed-flow-mapping": "- {token: SUPER_SECRET_TOKEN_VALUE, firewalls: [fw-1]\n",
    "undefined-alias": "- token: *SUPER_SECRET_TOKEN_VALUE\n  firewalls: [fw-1]\n",
    "duplicate-anchor": (
        "- token: &SUPER_SECRET_TOKEN_VALUE t1\n"
        "  firewalls: [fw-1]\n"
        "- token: &SUPER_SECRET_TOKEN_VALUE t2\n"
        "  firewalls: [fw-2]\n"
    ),
    "duplicate-tag-handle": (
        "%TAG !SUPER_SECRET_TOKEN_VALUE! tag:example.com,2026:\n"
        "%TAG !SUPER_SECRET_TOKEN_VALUE! tag:example.com,2027:\n"
        "---\n"
        "- token: t\n"
        "  firewalls: [fw-1]\n"
    ),
}


@pytest.mark.parametrize("yaml_source", LEAKY_YAML.values(), ids=LEAKY_YAML.keys())
@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
@patch("logging.error")
def test_read_config_yaml_error_redacts_secret_value(
    mock_logging: MagicMock,
    yaml_source: str,
) -> None:
    """YAML parse errors must not echo any part of the file holding the token."""
    with (
        patch("builtins.open", mock_open(read_data=yaml_source)),
        pytest.raises(SystemExit) as e,
    ):
        _read_config("config.yaml")

    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Error reading config file 'config.yaml': " in error_msg
    assert "SUPER_SECRET_TOKEN_VALUE" not in error_msg
    # The operator still gets an actionable message: what broke and where.
    assert "line " in error_msg


@patch("logging.error")
def test_read_config_yaml_error_without_marks(mock_logging: MagicMock) -> None:
    """A YAMLError carrying no position marks still logs without raising."""
    with (
        patch("builtins.open", mock_open(read_data="- token: token\n")),
        patch(
            "cf_ips_to_hcloud_fw.config.yaml.safe_load",
            side_effect=yaml.YAMLError("bare failure"),
        ),
        pytest.raises(SystemExit) as e,
    ):
        _read_config("config.yaml")

    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert (
        "Error reading config file 'config.yaml': YAMLError"
        in mock_logging.call_args[0][0]
    )


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
    # Unknown keys are file contents (a token can end up in key position), so
    # the message names the position but not the key itself.
    assert "'loc': (0, '<unknown key>')" in error_msg
    assert "firewall_names" not in error_msg


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
    assert "'loc': (0, '<unknown key>')" in error_msg
    assert "extra_key" not in error_msg


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


# Typos that turn the token into a mapping *key*: a flow mapping with no space
# after the colon makes "token:<TOKEN>" one key, and a token pasted on its own
# line is a key with whatever follows the colon as its value. Pydantic reports
# unknown keys in the error `loc`, which include_input=False does not touch.
_TOKEN_AS_KEY_CONFIGS = {
    "flow-mapping-no-space": "- {token:SUPER_SECRET_TOKEN_VALUE, firewalls: [fw-1]}\n",
    "token-as-key": "- SUPER_SECRET_TOKEN_VALUE: x\n  firewalls: [fw-1]\n",
}


@pytest.mark.parametrize(
    "config_text", _TOKEN_AS_KEY_CONFIGS.values(), ids=_TOKEN_AS_KEY_CONFIGS.keys()
)
@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
@patch("logging.error")
def test_read_config_validation_error_redacts_token_in_mapping_key(
    mock_logging: MagicMock, config_text: str
) -> None:
    """A token that lands in key position must not reach the log through `loc`."""
    with (
        patch("builtins.open", mock_open(read_data=config_text)),
        pytest.raises(SystemExit) as e,
    ):
        _read_config("config.yaml")

    assert e.value.code == 1
    mock_logging.assert_called_once()
    error_msg = mock_logging.call_args[0][0]
    assert "Config file 'config.yaml' is broken:" in error_msg
    assert "SUPER_SECRET_TOKEN_VALUE" not in error_msg
    assert "<unknown key>" in error_msg
    assert "extra_forbidden" in error_msg


# Keys YAML reads as something other than a string: Pydantic reports them in
# `loc` as that value, so a numeric secret in key position would look like a
# list index and a bool key like the second project. The sanitizer filters by
# position, not by type.
_NON_STRING_KEY_CONFIGS = {
    "int-key": "- 1234567890123456: x\n  token: t\n  firewalls: [fw-1]\n",
    "hex-key": "- 0xDEADBEEFCAFE: x\n  token: t\n  firewalls: [fw-1]\n",
    "bool-key": "- yes: x\n  token: t\n  firewalls: [fw-1]\n",
}


@pytest.mark.parametrize(
    "config_text",
    _NON_STRING_KEY_CONFIGS.values(),
    ids=_NON_STRING_KEY_CONFIGS.keys(),
)
@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
@patch("logging.error")
def test_read_config_validation_error_redacts_non_string_keys(
    mock_logging: MagicMock, config_text: str
) -> None:
    """An int or bool key in `loc` is file content too, not a list index."""
    with (
        patch("builtins.open", mock_open(read_data=config_text)),
        pytest.raises(SystemExit) as e,
    ):
        _read_config("config.yaml")

    assert e.value.code == 1
    error_msg = mock_logging.call_args[0][0]
    assert "'loc': (0, '<unknown key>')" in error_msg
    assert "1234567890123456" not in error_msg
    assert "244837814094590" not in error_msg  # 0xDEADBEEFCAFE as decimal
    assert "'loc': (0, 1)" not in error_msg  # True would read as an index
    assert "'loc': (0, True)" not in error_msg


@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: SUPER_SECRET_TOKEN_VALUE
  firewall: [fw-1]
""",
    ),
)
@patch("logging.error")
def test_read_config_validation_error_keeps_known_field_names(
    mock_logging: MagicMock,
) -> None:
    """Sanitizing `loc` keeps indices and known field names so errors stay useful."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")

    assert e.value.code == 1
    error_msg = mock_logging.call_args[0][0]
    assert "'loc': (0, 'firewalls')" in error_msg  # the missing known field
    assert "'loc': (0, '<unknown key>')" in error_msg  # the mistyped one
    assert "firewall'" not in error_msg


@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: t
  firewalls: [fw-1, 2]
""",
    ),
)
@patch("logging.error")
def test_read_config_validation_error_keeps_firewall_entry_index(
    mock_logging: MagicMock,
) -> None:
    """The index of a bad `firewalls` entry survives, so the operator can find it."""
    with pytest.raises(SystemExit):
        _read_config("config.yaml")

    error_msg = mock_logging.call_args[0][0]
    assert "'loc': (0, 'firewalls', 1)" in error_msg


def test_describe_validation_errors_withholds_validator_messages() -> None:
    """A validator's own message may quote the input, so it is not forwarded."""

    def reject(value: str) -> str:
        msg = f"bad value {value!r}"
        raise ValueError(msg)

    class Model(BaseModel):
        value: Annotated[str, AfterValidator(reject)]

    with pytest.raises(ValidationError) as e:
        Model(value="SUPER_SECRET_TOKEN_VALUE")

    described = _describe_validation_errors(e.value)
    assert described == [
        {
            "type": "value_error",
            "loc": ("<unknown key>",),
            "msg": "<message withheld: may quote the input>",
        }
    ]


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


@patch.dict(
    "os.environ",
    {"HCLOUD_TOKEN": "\n", "HCLOUD_FIREWALLS": "fw-1"},
    clear=True,
)
@patch("logging.error")
def test_read_config_from_env_rejects_whitespace_only_token(
    mock_logging: MagicMock,
) -> None:
    """A secret file holding only a newline must fail as "not set".

    `HCLOUD_TOKEN=$(cat /run/secrets/token)` on an empty-ish file yields a lone
    newline. The model strips it, so without stripping before this guard the
    run would proceed with an empty token and 401 on every firewall instead of
    telling the operator the variable is unset.
    """
    with pytest.raises(SystemExit) as e:
        _read_config_from_env()

    assert e.value.code == 1
    assert f"{ENV_TOKEN} is not set" in mock_logging.call_args[0][0]


@patch(
    "builtins.open",
    mock_open(
        read_data="""
- token: "   "
  firewalls:
    - fw-1
""",
    ),
)
@patch("cf_ips_to_hcloud_fw.config.os.name", "nt")
@patch("logging.error")
def test_read_config_rejects_whitespace_only_token(mock_logging: MagicMock) -> None:
    """The same empty-after-strip state, arriving via a config file."""
    with pytest.raises(SystemExit) as e:
        _read_config("config.yaml")

    assert e.value.code == 1
    assert "Config file 'config.yaml' is broken:" in mock_logging.call_args[0][0]

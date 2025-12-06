from __future__ import annotations

import importlib
import importlib.metadata
import re
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

import cf_ips_to_hcloud_fw
from cf_ips_to_hcloud_fw.__main__ import create_parser, main  # noqa: PLC2701
from cf_ips_to_hcloud_fw.models import Project


def test_create_parser() -> None:
    """CLI parser should expose the expected options and defaults."""
    parser = create_parser()
    assert "-c" in parser._option_string_actions
    assert "--config" in parser._option_string_actions
    assert "-d" in parser._option_string_actions
    assert "--debug" in parser._option_string_actions
    assert "-v" in parser._option_string_actions
    assert "--version" in parser._option_string_actions
    args = parser.parse_args(["-c", "config.yaml", "-d"])
    assert args.config == "config.yaml"
    assert args.debug is True
    args = parser.parse_args(["-c", "config2.yaml"])
    assert args.config == "config2.yaml"
    assert args.debug is False


def test_parser_version(capfd: pytest.CaptureFixture[str]) -> None:
    """`-v` should print the package version and exit cleanly."""
    parser = create_parser()
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["-v"])
    assert e.value.code == 0
    out, _err = capfd.readouterr()
    assert out.strip() == cf_ips_to_hcloud_fw.__version__
    assert re.match(r"^\d+\.\d+\.\d+(\.dev\d+)?$", cf_ips_to_hcloud_fw.__version__)


def test_parser_version_no_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fallback to 'local' when importlib.metadata cannot find the package."""
    monkeypatch.setattr(
        "importlib.metadata.version",
        MagicMock(side_effect=importlib.metadata.PackageNotFoundError),
    )
    try:
        importlib.reload(cf_ips_to_hcloud_fw)
        assert cf_ips_to_hcloud_fw.__version__ == "local"
    finally:
        monkeypatch.undo()
        importlib.reload(cf_ips_to_hcloud_fw)


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.read_config",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"]),
        Project(token=SecretStr("token-2"), firewalls=["fw-1", "fw-2"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch("cf_ips_to_hcloud_fw.__main__.update_project", return_value=[])
def test_main(mock_update_project: MagicMock, mock_projects: MagicMock) -> None:
    """main should iterate every parsed project and call update_project."""
    main()
    assert mock_update_project.call_count == len(mock_projects.return_value)
    for i, project in enumerate(mock_projects.return_value):
        assert mock_update_project.call_args_list[i][0][0] == project
        assert mock_update_project.call_args_list[i][0][2] == i + 1


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.read_config",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.update_project",
    return_value=["project 1:fw-2", "project 1:fw-3"],
)
@patch("logging.error")
def test_main_with_skipped_firewalls(
    mock_logging: MagicMock, mock_update_project: MagicMock, mock_projects: MagicMock
) -> None:
    """main should exit with code 1 when firewalls are skipped."""
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    assert mock_update_project.call_count == len(mock_projects.return_value)
    mock_logging.assert_called_once_with(
        "Some firewalls have been skipped: project 1:fw-2, project 1:fw-3"
    )


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.read_config",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-2"]),
        Project(token=SecretStr("token-3"), firewalls=["fw-4"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.update_project",
    side_effect=[["project 1:fw-1"], ["project 2:fw-3", "project 2:fw-4"]],
)
@patch("logging.error")
def test_main_with_skipped_firewalls_multiple_projects(
    mock_logging: MagicMock, mock_update_project: MagicMock, mock_projects: MagicMock
) -> None:
    """Aggregate skipped firewalls across multiple projects before exiting."""
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    assert mock_update_project.call_count == len(mock_projects.return_value)
    mock_logging.assert_called_once_with(
        "Some firewalls have been skipped: "
        "project 1:fw-1, project 2:fw-3, project 2:fw-4"
    )

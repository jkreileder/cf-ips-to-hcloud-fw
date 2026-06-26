"""Tests for the CLI entry point and argument parsing."""

from __future__ import annotations

import importlib
import importlib.metadata
import re
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

import cf_ips_to_hcloud_fw
from cf_ips_to_hcloud_fw.__main__ import create_parser, main
from cf_ips_to_hcloud_fw.firewall import ProjectOutcome
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
    # -c is optional: without it the env-var fallback kicks in downstream.
    args = parser.parse_args([])
    assert args.config is None
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
    "cf_ips_to_hcloud_fw.__main__.load_projects",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"]),
        Project(token=SecretStr("token-2"), firewalls=["fw-1", "fw-2"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.update_project",
    return_value=ProjectOutcome(skipped=[], failed=[]),
)
def test_main(mock_update_project: MagicMock, mock_projects: MagicMock) -> None:
    """Iterate every parsed project and call update_project."""
    main()
    assert mock_update_project.call_count == len(mock_projects.return_value)
    for i, project in enumerate(mock_projects.return_value):
        call_kwargs = mock_update_project.call_args_list[i].kwargs
        assert call_kwargs["project"] == project
        assert call_kwargs["project_index"] == i + 1


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.load_projects",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.update_project",
    return_value=ProjectOutcome(
        skipped=["project 1:fw-2", "project 1:fw-3"], failed=[]
    ),
)
@patch("logging.error")
def test_main_with_skipped_firewalls(
    mock_logging: MagicMock, mock_update_project: MagicMock, mock_projects: MagicMock
) -> None:
    """Exit with code 1 when firewalls are skipped."""
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    assert mock_update_project.call_count == len(mock_projects.return_value)
    mock_logging.assert_called_once_with(
        "Some firewalls were not updated (not found: project 1:fw-2, project 1:fw-3)"
    )


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.load_projects",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-2"]),
        Project(token=SecretStr("token-3"), firewalls=["fw-4"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.update_project",
    side_effect=[
        ProjectOutcome(skipped=["project 1:fw-1"], failed=[]),
        ProjectOutcome(skipped=["project 2:fw-3", "project 2:fw-4"], failed=[]),
    ],
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
        "Some firewalls were not updated (not found: "
        "project 1:fw-1, project 2:fw-3, project 2:fw-4)"
    )


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.load_projects",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-1"]),
        Project(token=SecretStr("token-2"), firewalls=["fw-2"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.update_project",
    side_effect=[
        ProjectOutcome(skipped=[], failed=["project 1:fw-1"]),
        ProjectOutcome(skipped=[], failed=[]),
    ],
)
@patch("logging.error")
def test_main_failed_project_does_not_abort_remaining(
    mock_logging: MagicMock, mock_update_project: MagicMock, mock_projects: MagicMock
) -> None:
    """A failure in project 1 must not prevent project 2 from being processed."""
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    # Both projects were attempted even though the first one failed.
    assert mock_update_project.call_count == len(mock_projects.return_value)
    mock_logging.assert_called_once_with(
        "Some firewalls were not updated (failed: project 1:fw-1)"
    )


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.load_projects",
    return_value=[Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"])],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.update_project",
    return_value=ProjectOutcome(skipped=["project 1:fw-2"], failed=["project 1:fw-1"]),
)
@patch("logging.error")
def test_main_reports_failed_and_skipped(
    mock_logging: MagicMock, mock_update_project: MagicMock, mock_projects: MagicMock
) -> None:
    """Both failed and not-found firewalls are reported, failures listed first."""
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    assert mock_update_project.call_count == len(mock_projects.return_value)
    mock_logging.assert_called_once_with(
        "Some firewalls were not updated "
        "(failed: project 1:fw-1; not found: project 1:fw-2)"
    )

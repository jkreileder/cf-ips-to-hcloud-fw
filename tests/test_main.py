from __future__ import annotations

from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from cf_ips_to_hcloud_fw.__main__ import create_parser, main  # noqa: PLC2701
from cf_ips_to_hcloud_fw.models import Project


def test_create_parser() -> None:
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


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.read_config",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"]),
        Project(token=SecretStr("token-2"), firewalls=["fw-1", "fw-2"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_cidrs", MagicMock())
@patch("cf_ips_to_hcloud_fw.__main__.update_project")
def test_main(mock_update_project: MagicMock, mock_projects: MagicMock) -> None:
    main()
    assert mock_update_project.call_count == len(mock_projects.return_value)
    for i, project in enumerate(mock_projects.return_value):
        assert mock_update_project.call_args_list[i][0][0] == project

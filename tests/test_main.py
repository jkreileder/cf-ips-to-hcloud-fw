from __future__ import annotations

from unittest.mock import MagicMock, call, mock_open, patch

import CloudFlare  # type: ignore[import-untyped]
import pytest
from hcloud import APIException
from hcloud.firewalls.domain import Firewall, FirewallRule
from pydantic import SecretStr

from cf_ips_to_hcloud_fw.__main__ import (
    CF_ALL,
    CF_IPV4,
    CF_IPV6,
    CloudflareIPs,
    Project,
    cf_ips_get,  # type: ignore[import-untyped]
    create_parser,
    fw_set_rules,
    get_cloudflare_ips,
    main,
    read_config,
    update_firewall,
    update_firewall_rule,
    update_project,
    update_source_ips,
)


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


@patch("CloudFlare.CloudFlare")
@patch("logging.error")
def test_cf_ips_get(mock_logging: MagicMock, mock_cloudflare: MagicMock) -> None:
    mock_cloudflare.return_value.ips.get.side_effect = (
        CloudFlare.exceptions.CloudFlareAPIError(503, "503")  # type: ignore[assignment]
    )
    with pytest.raises(SystemExit) as e:
        cf_ips_get()
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_cloudflare.return_value.ips.get.assert_called_once()
    mock_logging.assert_called_once_with("Error getting CloudFlare IPs: 503")


@patch(
    "cf_ips_to_hcloud_fw.__main__.cf_ips_get",
    MagicMock(return_value={"ipv4_cidrs": ["199.27.128.0/21", "198.27.128.0/21"]}),
)
@patch("logging.error")
def test_get_cloudflare_ips_invalid(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        get_cloudflare_ips()
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Cloudflare/ips.get didn't validate" in mock_logging.call_args[0][0]


@patch(
    "cf_ips_to_hcloud_fw.__main__.cf_ips_get",
    MagicMock(
        return_value={
            "ipv4_cidrs": ["199.27.128.0/21", "198.27.128.0/21"],
            "ipv6_cidrs": ["2400:cb00::/32", "1400:cb00::/32"],
        }
    ),
)
def test_get_cloudflare_ips() -> None:
    result = get_cloudflare_ips()
    assert result == CloudflareIPs(
        ipv4_cidrs=["198.27.128.0/21", "199.27.128.0/21"],
        ipv6_cidrs=["1400:cb00::/32", "2400:cb00::/32"],
    )


@pytest.mark.parametrize(
    ("ips", "cidrs", "expected"),
    [
        (None, ["127.1"], True),
        ([], ["127.1"], True),
        (["127.1"], ["127.1"], False),
        (["127.1"], ["127.2"], True),
        (["127.1"], ["127.1", "127.2"], True),
    ],
)
def test_update_source_ips(*, ips: list[str], cidrs: list[str], expected: bool) -> None:
    rule = FirewallRule(FirewallRule.DIRECTION_IN, FirewallRule.PROTOCOL_TCP, ips)
    fw = Firewall(rules=[rule])
    needs_update = update_source_ips(fw, rule, cidrs, "")
    assert needs_update == expected
    assert fw.rules
    assert fw.rules[0].source_ips == cidrs


@pytest.mark.parametrize(
    ("ipv4", "ipv6", "kind"),
    [
        (True, True, "IPv4+IPv6"),
        (True, False, "IPv4"),
        (False, True, "IPv6"),
        (False, False, None),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.update_source_ips", wraps=update_source_ips)
def test_update_firewall_rule(
    mock_update_source_ips: MagicMock, *, ipv4: bool, ipv6: bool, kind: str
) -> None:
    r = FirewallRule(FirewallRule.DIRECTION_IN, FirewallRule.PROTOCOL_TCP, [])
    fw = Firewall(1, "fw-1", rules=[r])
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])
    if ipv4 or ipv6:
        assert update_firewall_rule(fw, r, cf_ips, ipv4=ipv4, ipv6=ipv6)
        if ipv4 and ipv6:
            ips = cf_ips.ipv4_cidrs + cf_ips.ipv6_cidrs
        elif ipv4:
            ips = cf_ips.ipv4_cidrs
        else:
            ips = cf_ips.ipv6_cidrs
        mock_update_source_ips.assert_called_once_with(fw, r, ips, kind)
        # Second update should not change anything
        assert not update_firewall_rule(fw, r, cf_ips, ipv4=ipv4, ipv6=ipv6)
    else:
        assert not update_firewall_rule(fw, r, cf_ips, ipv4=ipv4, ipv6=ipv6)
        mock_update_source_ips.assert_not_called()


@patch("cf_ips_to_hcloud_fw.__main__.update_firewall_rule", wraps=update_firewall_rule)
@patch("cf_ips_to_hcloud_fw.__main__.fw_set_rules")
def test_update_firewall(
    mock_firewalls_set_rules: MagicMock, mock_update_firewall_rule: MagicMock
) -> None:
    client = MagicMock()
    fw = Firewall(
        name="fw-1",
        rules=[
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=f" {CF_ALL} ",
                source_ips=[],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_OUT,
                FirewallRule.PROTOCOL_TCP,
                description=CF_ALL,
                source_ips=[],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=CF_IPV4,
                source_ips=[],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=CF_IPV6,
                source_ips=[],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=f"{CF_IPV4} {CF_IPV6}",
                source_ips=[],
            ),
        ],
    )
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])

    update_firewall(client, fw, cf_ips)

    assert fw.rules
    mock_update_firewall_rule.assert_has_calls([
        call(fw, fw.rules[0], cf_ips, ipv4=True, ipv6=True),
        call(fw, fw.rules[2], cf_ips, ipv4=True, ipv6=False),
        call(fw, fw.rules[3], cf_ips, ipv4=False, ipv6=True),
        call(fw, fw.rules[4], cf_ips, ipv4=True, ipv6=True),
    ])
    mock_firewalls_set_rules.assert_called_once_with(client, fw)


@patch("cf_ips_to_hcloud_fw.__main__.update_firewall_rule", wraps=update_firewall_rule)
@patch("cf_ips_to_hcloud_fw.__main__.fw_set_rules")
def test_update_firewall_already_up_to_date(
    mock_firewalls_set_rules: MagicMock,
    mock_update_firewall_rule: MagicMock,
) -> None:
    client = MagicMock()
    fw = Firewall(
        name="fw-1",
        rules=[
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=f" {CF_ALL} ",
                source_ips=["127.1", "::1"],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_OUT,
                FirewallRule.PROTOCOL_TCP,
                description=CF_ALL,
                source_ips=[],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=CF_IPV4,
                source_ips=["127.1"],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=CF_IPV6,
                source_ips=["::1"],
            ),
            FirewallRule(
                FirewallRule.DIRECTION_IN,
                FirewallRule.PROTOCOL_TCP,
                description=f"{CF_IPV4} {CF_IPV6}",
                source_ips=["127.1", "::1"],
            ),
        ],
    )
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])
    update_firewall(client, fw, cf_ips)

    assert fw.rules
    mock_update_firewall_rule.assert_has_calls([
        call(fw, fw.rules[0], cf_ips, ipv4=True, ipv6=True),
        call(fw, fw.rules[2], cf_ips, ipv4=True, ipv6=False),
        call(fw, fw.rules[3], cf_ips, ipv4=False, ipv6=True),
        call(fw, fw.rules[4], cf_ips, ipv4=True, ipv6=True),
    ])
    mock_firewalls_set_rules.assert_not_called()


@pytest.mark.parametrize(
    "rules",
    [
        None,
        [],
        [FirewallRule(FirewallRule.DIRECTION_IN, FirewallRule.PROTOCOL_TCP, ["127.1"])],
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.Client")
def test_fw_set_rules(mock_client: MagicMock, *, rules: list[FirewallRule]) -> None:
    expected = rules or []
    fw = Firewall(name="fw-1", rules=rules)
    fw_set_rules(mock_client, fw)
    mock_client.firewalls.set_rules.assert_called_once_with(fw, expected)


@patch("cf_ips_to_hcloud_fw.__main__.Client")
@patch("logging.error")
def test_fw_set_rules_fail(mock_logging: MagicMock, mock_client: MagicMock) -> None:
    fw = Firewall(name="fw-1", rules=[])
    mock_client.firewalls.set_rules.side_effect = APIException(
        "Test exception", "Message", "Details"
    )
    with pytest.raises(SystemExit) as e:
        fw_set_rules(mock_client, fw)
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_client.firewalls.set_rules.assert_called_once_with(fw, [])
    mock_logging.assert_called_once_with(
        "hcloud/firewall.set_rules failed for 'fw-1': Message"
    )


@patch("cf_ips_to_hcloud_fw.__main__.update_firewall_rule", wraps=update_firewall_rule)
@patch("cf_ips_to_hcloud_fw.__main__.fw_set_rules")
def test_update_firewall_no_rules(
    mock_firewalls_set_rules: MagicMock,
    mock_update_firewall_rule: MagicMock,
) -> None:
    fw = Firewall(name="fw-1", rules=[])
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])

    update_firewall(MagicMock(), fw, cf_ips)

    mock_update_firewall_rule.assert_not_called()
    mock_firewalls_set_rules.assert_not_called()


@patch("cf_ips_to_hcloud_fw.__main__.Client")
@patch("cf_ips_to_hcloud_fw.__main__.update_firewall")
def test_update_project_found(
    mock_update_firewall: MagicMock, mock_client: MagicMock
) -> None:
    fw = Firewall(1, "fw-1")
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])
    mock_client.return_value.firewalls.get_by_name.return_value = fw
    project = Project(token=SecretStr("token-1"), firewalls=["fw-1"])
    update_project(project, cf_ips)
    mock_client.return_value.firewalls.get_by_name.assert_called_once_with("fw-1")
    mock_update_firewall.assert_called_once_with(mock_client.return_value, fw, cf_ips)


@patch("cf_ips_to_hcloud_fw.__main__.Client")
@patch("cf_ips_to_hcloud_fw.__main__.update_firewall")
@patch("logging.error")
def test_update_project_not_found(
    mock_logging: MagicMock, mock_update_firewall: MagicMock, mock_client: MagicMock
) -> None:
    mock_client.return_value.firewalls.get_by_name.return_value = None
    project = Project(token=SecretStr("token-1"), firewalls=["fw-1"])
    update_project(project, CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"]))
    mock_client.return_value.firewalls.get_by_name.assert_called_once_with("fw-1")
    mock_update_firewall.assert_not_called()
    mock_logging.assert_called_once_with("hcloud firewall 'fw-1' not found")


@patch("cf_ips_to_hcloud_fw.__main__.Client")
@patch("logging.error")
def test_update_project_fail(mock_logging: MagicMock, mock_client: MagicMock) -> None:
    mock_client.return_value.firewalls.get_by_name.side_effect = APIException(
        "Test exception", "Message", "Details"
    )
    project = Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"])
    with pytest.raises(SystemExit) as e:
        update_project(project, CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"]))
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_client.return_value.firewalls.get_by_name.assert_called_once_with("fw-1")
    mock_logging.assert_called_once_with(
        "hcloud/firewalls.get_by_name failed for 'fw-1': Message"
    )


@patch("cf_ips_to_hcloud_fw.__main__.create_parser", MagicMock())
@patch(
    "cf_ips_to_hcloud_fw.__main__.read_config",
    MagicMock(
        return_value=[
            Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"]),
            Project(token=SecretStr("token-2"), firewalls=["fw-1", "fw-2"]),
        ]
    ),
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_ips", MagicMock())
@patch("cf_ips_to_hcloud_fw.__main__.update_project")
def test_main(mock_update_project: MagicMock) -> None:
    main()
    assert mock_update_project.call_count == 2  # noqa: PLR2004

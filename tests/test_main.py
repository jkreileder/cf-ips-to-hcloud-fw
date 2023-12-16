from unittest.mock import MagicMock, call, mock_open, patch

import pytest
from hcloud.firewalls.domain import Firewall, FirewallRule
from pydantic import SecretStr

from cf_ips_to_hcloud_fw.__main__ import (
    CF_ALL,
    CF_IPV4,
    CF_IPV6,
    CloudflareIPs,
    Project,
    create_parser,
    get_cloudflare_ips,
    main,
    read_config,
    update_firewall,
    update_firewall_rule,
    update_source_ips,
)


def test_create_parser() -> None:
    parser = create_parser()
    assert "-c" in parser._option_string_actions
    assert "--config" in parser._option_string_actions
    assert "-d" in parser._option_string_actions
    assert "--debug" in parser._option_string_actions


@patch("builtins.open", side_effect=FileNotFoundError("config.yaml"))
@patch("logging.error")
def test_read_config_file_not_found(
    mock_logging: MagicMock, mock_open: MagicMock
) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert mock_logging.call_args[0][0].startswith("Config file config.yaml not found.")


@patch("builtins.open", mock_open())
@patch("logging.error")
def test_read_config_empty(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Config file config.yaml is broken" in mock_logging.call_args[0][0]


@patch("builtins.open", mock_open(read_data="[]"))
@patch("logging.warning")
def test_read_config_empty_list(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 0
    mock_logging.assert_called_once_with(
        "Config file config.yaml contains no projects - exiting",
    )


@patch("builtins.open", mock_open(read_data="v: ]["))
@patch("logging.error")
def test_read_config_broken_yaml(mock_logging: MagicMock) -> None:
    with pytest.raises(SystemExit) as e:
        read_config("config.yaml")
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Error reading config file config.yaml" in mock_logging.call_args[0][0]


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


@patch(
    "cf_ips_to_hcloud_fw.__main__.cf_ips_get",
    return_value={"ipv4_cidrs": ["199.27.128.0/21", "198.27.128.0/21"]},
)
@patch("logging.error")
def test_get_cloudflare_ips_invalid(
    mock_logging: MagicMock, mock_cf_ips_get: MagicMock
) -> None:
    with pytest.raises(SystemExit) as e:
        get_cloudflare_ips()
    assert e.type is SystemExit
    assert e.value.code == 1
    mock_logging.assert_called_once()
    assert "Cloudflare/ips.get didn't validate" in mock_logging.call_args[0][0]


@patch(
    "cf_ips_to_hcloud_fw.__main__.cf_ips_get",
    return_value={
        "ipv4_cidrs": ["199.27.128.0/21", "198.27.128.0/21"],
        "ipv6_cidrs": ["2400:cb00::/32", "1400:cb00::/32"],
    },
)
def test_get_cloudflare_ips(mock_cf_ips_get: MagicMock) -> None:
    result = get_cloudflare_ips()
    assert result == CloudflareIPs(
        ipv4_cidrs=["198.27.128.0/21", "199.27.128.0/21"],
        ipv6_cidrs=["1400:cb00::/32", "2400:cb00::/32"],
        all_cidrs=[
            "198.27.128.0/21",
            "199.27.128.0/21",
            "1400:cb00::/32",
            "2400:cb00::/32",
        ],
    )


@pytest.mark.parametrize(
    ("needs_update_in", "ips", "cidrs", "needs_update_out"),
    [
        (False, None, ["127.1"], True),
        (False, [], ["127.1"], True),
        (False, ["127.1"], ["127.1"], False),
        (False, ["127.1"], ["127.2"], True),
        (True, ["127.1"], ["127.1"], True),
        (True, ["127.1"], ["127.2"], True),
        (False, ["127.1"], ["127.1", "127.2"], True),
        (True, ["127.1"], ["127.1", "127.2"], True),
    ],
)
def test_update_source_ips(
    needs_update_in: bool, ips: list[str], cidrs: list[str], needs_update_out: bool
) -> None:
    rule = FirewallRule("in", "tcp", ips)
    fw = Firewall(rules=[rule])
    needs_update = update_source_ips(needs_update_in, fw, rule, cidrs, "")
    assert needs_update == needs_update_out
    assert fw.rules
    assert fw.rules[0].source_ips == cidrs


@pytest.mark.parametrize(
    ("ipv4", "ipv6", "kind"),
    [
        (True, True, "all"),
        (True, False, "IPv4"),
        (False, True, "IPv6"),
        (False, False, None),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.update_source_ips", return_value=True)
def test_update_firewall_rule(
    mock_update_source_ips: MagicMock, ipv4: bool, ipv6: bool, kind: str
) -> None:
    fw = Firewall()
    r = FirewallRule("in", "tcp", [])
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])
    if ipv4 or ipv6:
        res = update_firewall_rule(False, fw, r, cf_ips, ipv4, ipv6)
        if ipv4 and ipv6:
            ips = cf_ips.all_cidrs
        elif ipv4:
            ips = cf_ips.ipv4_cidrs
        else:
            ips = cf_ips.ipv6_cidrs
        mock_update_source_ips.assert_called_once_with(False, fw, r, ips, kind)
        assert res is True
    else:
        assert not update_firewall_rule(False, fw, r, cf_ips, ipv4, ipv6)
        mock_update_source_ips.assert_not_called()
        assert update_firewall_rule(True, fw, r, cf_ips, ipv4, ipv6)
        mock_update_source_ips.assert_not_called()


@patch("cf_ips_to_hcloud_fw.__main__.update_firewall_rule", wraps=update_firewall_rule)
@patch("cf_ips_to_hcloud_fw.__main__.fw_set_rules")
def test_update_firewall(
    mock_firewalls_set_rules: MagicMock,
    mock_update_firewall_rule: MagicMock,
) -> None:
    client = MagicMock()
    fw = Firewall(
        name="test-firewall",
        rules=[
            FirewallRule("in", "tcp", description=f" {CF_ALL} ", source_ips=[]),
            FirewallRule("out", "tcp", description=CF_ALL, source_ips=[]),
            FirewallRule("in", "tcp", description=CF_IPV4, source_ips=[]),
            FirewallRule("in", "tcp", description=CF_IPV6, source_ips=[]),
        ],
    )
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])
    cf_ips.all_cidrs = cf_ips.ipv4_cidrs + cf_ips.ipv6_cidrs

    update_firewall(client, fw, cf_ips)

    assert fw.rules
    mock_update_firewall_rule.assert_has_calls([
        call(False, fw, fw.rules[0], cf_ips, True, True),
        call(True, fw, fw.rules[2], cf_ips, True, False),
        call(True, fw, fw.rules[3], cf_ips, False, True),
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
        name="test-firewall",
        rules=[
            FirewallRule(
                "in", "tcp", description=f" {CF_ALL} ", source_ips=["127.1", "::1"]
            ),
            FirewallRule("out", "tcp", description=CF_ALL, source_ips=[]),
            FirewallRule("in", "tcp", description=CF_IPV4, source_ips=["127.1"]),
            FirewallRule("in", "tcp", description=CF_IPV6, source_ips=["::1"]),
        ],
    )
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])
    cf_ips.all_cidrs = cf_ips.ipv4_cidrs + cf_ips.ipv6_cidrs

    update_firewall(client, fw, cf_ips)

    assert fw.rules
    mock_update_firewall_rule.assert_has_calls([
        call(False, fw, fw.rules[0], cf_ips, True, True),
        call(False, fw, fw.rules[2], cf_ips, True, False),
        call(False, fw, fw.rules[3], cf_ips, False, True),
    ])
    mock_firewalls_set_rules.assert_not_called()


@patch("cf_ips_to_hcloud_fw.__main__.update_firewall_rule", wraps=update_firewall_rule)
@patch("cf_ips_to_hcloud_fw.__main__.fw_set_rules")
def test_update_firewall_no_rules(
    mock_firewalls_set_rules: MagicMock,
    mock_update_firewall_rule: MagicMock,
) -> None:
    client = MagicMock()
    fw = Firewall(
        name="test-firewall",
        rules=[],
    )
    cf_ips = CloudflareIPs(ipv4_cidrs=["127.1"], ipv6_cidrs=["::1"])
    cf_ips.all_cidrs = cf_ips.ipv4_cidrs + cf_ips.ipv6_cidrs

    update_firewall(client, fw, cf_ips)

    mock_update_firewall_rule.assert_not_called()
    mock_firewalls_set_rules.assert_not_called()


@patch("cf_ips_to_hcloud_fw.__main__.create_parser")
@patch(
    "cf_ips_to_hcloud_fw.__main__.read_config",
    return_value=[
        Project(token=SecretStr("token-1"), firewalls=["fw-1", "fw-2"]),
        Project(token=SecretStr("token-2"), firewalls=["fw-1", "fw-2"]),
    ],
)
@patch("cf_ips_to_hcloud_fw.__main__.get_cloudflare_ips")
@patch("cf_ips_to_hcloud_fw.__main__.update_project")
def test_main(
    mock_update_project: MagicMock,
    mock_get_cloudflare_ips: MagicMock,
    mock_read_config: MagicMock,
    mock_create_parser: MagicMock,
) -> None:
    main()
    assert mock_update_project.call_count == 2

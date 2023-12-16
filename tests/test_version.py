from cf_ips_to_hcloud_fw.version import __VERSION__


def test_version() -> None:
    assert isinstance(__VERSION__, str)

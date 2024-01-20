from __future__ import annotations

import re

import pytest

from cf_ips_to_hcloud_fw.__main__ import create_parser  # noqa: PLC2701
from cf_ips_to_hcloud_fw.version import __VERSION__


def test_version(capfd: pytest.CaptureFixture[str]) -> None:
    assert isinstance(__VERSION__, str)
    assert re.match(r"^\d+\.\d+\.\d+(-dev)?$", __VERSION__)

    parser = create_parser()
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["-v"])
    assert e.type is SystemExit
    assert e.value.code == 0
    out, _err = capfd.readouterr()
    assert out.strip() == __VERSION__

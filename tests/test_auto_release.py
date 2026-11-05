"""Tests for the release automation script in .github/scripts/auto_release.py.

The script is not a package, so it is loaded by path. Only the pure helpers are
covered here; the git and gh paths run in the auto-release workflows.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover
    from types import ModuleType  # pragma: no cover

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "auto_release.py"


@pytest.fixture(scope="module")
def auto_release() -> ModuleType:
    """Load the script as a module.

    The container image build runs the tests from a context that holds
    ``tests/`` but not ``.github/``, so the script may be absent; skip then.
    The module is registered in ``sys.modules`` before it executes because
    ``dataclasses`` resolves the script's string annotations (it uses
    ``from __future__ import annotations``) through the module's entry there
    on Python 3.11 to 3.14.

    Returns:
        ModuleType: The executed script module.
    """
    if not SCRIPT.exists():
        pytest.skip("the release script is not part of this checkout")
    spec = importlib.util.spec_from_file_location("auto_release", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_annotation_encodes_workflow_command_syntax(auto_release: ModuleType) -> None:
    """Percent, CR and LF cannot end the annotation or start another command."""
    text = "CVE-1\r\n::error::injected 100%"
    assert auto_release.annotation("warning", text) == (
        "::warning::CVE-1%0D%0A::error::injected 100%25\n"
    )


def test_fail_writes_an_encoded_error_annotation(
    auto_release: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """fail() goes through the same encoding and exits 1."""
    with pytest.raises(SystemExit) as e:
        auto_release.fail("first\nsecond")
    assert e.value.code == 1
    assert capsys.readouterr().err == "::error::first%0Asecond\n"


@pytest.mark.parametrize("version", ["1.2.3", "0.0.0", "10.20.30"])
def test_parse_final_accepts_final_versions(
    auto_release: ModuleType, version: str
) -> None:
    """Plain X.Y.Z parses into integers."""
    assert auto_release.parse_final(version) == tuple(
        int(part) for part in version.split(".")
    )


@pytest.mark.parametrize(
    "version",
    ["1.2.3\n", "1.2.3.dev1", "v1.2.3", "01.2.3", "1.2", "1.2.3 ", "1.2.3rc1"],
)
def test_parse_final_rejects_anything_else(
    auto_release: ModuleType, version: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A trailing newline, a dev suffix, a prefix or a leading zero is not final."""
    with pytest.raises(SystemExit):
        auto_release.parse_final(version)
    assert "not a final X.Y.Z version" in capsys.readouterr().err


def test_dev_version_regex_matches_exactly(auto_release: ModuleType) -> None:
    """The dev regex pairs with fullmatch and refuses a trailing newline."""
    assert auto_release.DEV_VERSION_RE.fullmatch("1.2.3.dev1")
    assert auto_release.DEV_VERSION_RE.fullmatch("1.2.3.dev1\n") is None
    assert auto_release.DEV_VERSION_RE.fullmatch("1.02.3.dev1") is None


def test_write_outputs_rejects_line_breaks(
    auto_release: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A value with a line break would become a second output; it is refused."""
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    with pytest.raises(SystemExit):
        auto_release.write_outputs(release="false\nrelease=true")
    assert "would span more than one line" in capsys.readouterr().err
    assert not output.exists()


def test_write_outputs_appends_one_line_per_output(
    auto_release: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Well-formed outputs are appended to GITHUB_OUTPUT and echoed."""
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    auto_release.write_outputs(release="true", version="1.2.3")
    assert output.read_text() == "release=true\nversion=1.2.3\n"

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from cf_ips_to_hcloud_fw.models import Project


def test_project_valid() -> None:
    """Project model accepts valid configuration."""
    project = Project(token=SecretStr("my-token"), firewalls=["fw-1", "fw-2"])
    assert project.token.get_secret_value() == "my-token"
    assert project.firewalls == ["fw-1", "fw-2"]


def test_project_no_firewall_fails() -> None:
    """Project model rejects empty firewall list."""
    with pytest.raises(ValidationError) as e:
        Project(token=SecretStr("my-token"), firewalls=[])
    assert e.type is ValidationError
    assert "List should have at least 1 item after validation, not 0" in str(e.value)


def test_project_single_firewall() -> None:
    """Project model accepts a single firewall."""
    project = Project(token=SecretStr("my-token"), firewalls=["fw-1"])
    assert project.firewalls == ["fw-1"]

"""Shared fixtures.

The secret registry in `custom_logging` is module-level state, so it outlives
any single test. Clearing it here rather than in one test module keeps tokens
registered by `test_firewall.py` / `test_main.py` from lingering and silently
rewriting another test's expected log output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cf_ips_to_hcloud_fw.custom_logging import forget_secrets

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator  # pragma: no cover


@pytest.fixture(autouse=True)
def _clean_secret_registry() -> Iterator[None]:
    """Give every test an empty secret registry.

    Yields:
        None: Control returns to the test with nothing registered.
    """
    forget_secrets()
    yield
    forget_secrets()

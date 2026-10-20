"""pytest configuration: register the `slow` marker."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "slow: needs the models, the corpus and the index (minutes, not seconds)"
    )

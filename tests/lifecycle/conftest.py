"""Fixtures for the lifecycle parity gate (Child 2).

Provides the external-system doubles the parity test drives. ``tmp_repo`` is a
clean temp directory standing in for a repo root; conventions are loaded from the
installed ``atdd`` package (the canonical phase-machine YAML), so the parity test
needs no checked-out tree to decide against.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures import FakeAgent, FakeGitHub, FakeObserver


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def fake_agent() -> FakeAgent:
    return FakeAgent()


@pytest.fixture
def fake_observer() -> FakeObserver:
    return FakeObserver()

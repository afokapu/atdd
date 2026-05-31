# URN: test:govern-lifecycle:extract-workflow-persistence-and-events-schema:E040-UNIT-002-load-conventions-snapshot-hash
# Acceptance: acc:govern-lifecycle:E040-UNIT-002-load-conventions-snapshot-hash
"""Unit test for E040-UNIT-002 (docs/coach-decomposition.md §4.4, §4.5, §5.3).

``load_conventions(repo_root)`` loads + normalizes the phase-machine YAML, freezes
it into a ``Conventions`` bundle, and computes a deterministic sha256 snapshot
hash. This replaces the Child 3 signature-only ``NotImplementedError``.
"""
from __future__ import annotations

import re

import pytest

from atdd.coach.core.types import Conventions, Persona, Phase
from atdd.train.persistence import load_conventions

from tests.coach._e040_helpers import build_temp_repo

pytestmark = pytest.mark.atdd_validator

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def test_load_conventions_returns_frozen_phase_machine(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)

    assert isinstance(conventions, Conventions)
    pm = conventions.phase_machine
    # Every §4.5 phase is present.
    for phase in Phase:
        assert phase in pm, f"phase machine missing {phase}"
    # INIT is driven by the planner and can advance to PLANNED.
    assert pm[Phase.INIT].agent == Persona.PLANNER
    assert Phase.PLANNED in pm[Phase.INIT].transitions_to
    assert conventions.snapshot_paths, "snapshot_paths must name the source file(s)"


def test_snapshot_hash_is_sha256_and_stable(tmp_path):
    repo = build_temp_repo(tmp_path)
    first = load_conventions(repo)
    second = load_conventions(repo)

    assert _SHA256_HEX.match(first.snapshot_hash), "snapshot_hash must be a sha256 hex digest"
    assert first.snapshot_hash == second.snapshot_hash, "hash must be byte-stable across loads"


def test_load_conventions_no_longer_raises(tmp_path):
    repo = build_temp_repo(tmp_path)
    # The Child 3 signature-only behavior (NotImplementedError) is gone.
    conventions = load_conventions(repo)
    assert conventions.snapshot_hash

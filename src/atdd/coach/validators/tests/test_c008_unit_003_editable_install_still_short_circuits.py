# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:C008-UNIT-003-editable-install-still-short-circuits
# Acceptance: acc:govern-lifecycle:C008-UNIT-003-editable-install-still-short-circuits
# WMBT: wmbt:govern-lifecycle:C008
# Phase: GREEN
# Layer: backend.domain
# Assertion: behavioral
"""C008-UNIT-003 — the one legitimate skip survives the repair.

Of the gate's several skips, exactly one is honest: under an editable install (or
``PYTHONPATH=src``) the imported package IS the source tree, so `expected.exists()`
is asking whether a file exists at its own path. That is a tautology, not a check,
and it must still short-circuit.

This is the guard rail on C008-UNIT-002: the cwd fallback added there must not turn
every local dev run into a self-comparison that passes for the wrong reason.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_wheel_completeness import evaluate_wheel_completeness

# `platform` marks this a TOOLKIT-SELF test: it needs the toolkit checkout (and/or a
# wheel built from it), which a consumer repo does not have. `atdd validate <phase>`
# adds `-m "not platform"` outside the source repo (E025), so this is deselected there
# and runs here. Without the marker these ship in the wheel and ERROR in every
# consumer's sweep — the #954 self-test-leak pathology, which this issue must not add to.
pytestmark = [pytest.mark.coach, pytest.mark.platform]


def test_c008_unit_003_editable_install_short_circuits(tmp_path: Path):
    """When the package dir IS src/atdd, the gate skips rather than self-comparing."""
    root = tmp_path / "checkout"
    src_atdd = root / "src" / "atdd"
    src_atdd.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'atdd'\n")
    (src_atdd / "coach").mkdir()
    (src_atdd / "coach" / "schemas.json").write_text("{}")

    outcome = evaluate_wheel_completeness(
        repo_src_atdd=src_atdd,
        installed_atdd_dir=src_atdd,  # the editable-install identity
    )

    assert outcome.status == "skip", (
        f"the gate ran a scan where source and wheel root are the same directory. "
        f"Every assertion there is trivially true, so it must short-circuit. "
        f"status={outcome.status!r}"
    )
    assert "editable" in (outcome.reason or "").lower(), (
        f"the skip does not name the editable install as its reason, so a reader "
        f"cannot tell this skip from the vacuous ones: {outcome.reason!r}"
    )

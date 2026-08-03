# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E071-UNIT-003-eligibility-derived-from-the-convention
# Acceptance: acc:govern-lifecycle:E071-UNIT-003-eligibility-derived-from-the-convention
# WMBT: wmbt:govern-lifecycle:E071
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""E071-UNIT-003 — the enforcement derives its verdict; it does not restate it.

The defect's seam was a Python literal:

    _BLOCKED_PHASES = frozenset({"INIT", "PLANNED", "RED", "GREEN"})

a second copy of a decision the convention already carried. Two copies of one
decision drift, and this pair did. A validator that *reads* the table cannot
disagree with it — the precedent is ``phase_machine.convention.yaml``, whose
phase order is walked out of the authored convention rather than forked
(``test_phase_ladder_matches_projection_phases``).

The copy is also the wrong half. ``merge_blocked`` enumerated the phases that
are *not* eligible, so every phase the machine grew had to be remembered here.
One set is authoritative — ``phase_labels.merge_allowed`` — and blocked is its
complement, computed. There is no list left to forget to extend.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils import pr_merge_eligibility as elig
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod

# Every assertion here reads the toolkit's own conventions under src/atdd/, which
# no consumer checkout has — so the whole module is toolkit-self and carries the
# platform marker wholesale (coach.source-layout.platform-marker-on-toolkit-selftest).
pytestmark = [pytest.mark.coach, pytest.mark.platform]

_CONVENTION = (
    find_repo_root() / "src" / "atdd" / "coach" / "conventions" / "pr.convention.yaml"
)
_PHASE_MACHINE = (
    find_repo_root()
    / "src"
    / "atdd"
    / "coach"
    / "conventions"
    / "phase_machine.convention.yaml"
)


def _phase_labels() -> dict:
    document = yaml.safe_load(_CONVENTION.read_text(encoding="utf-8")) or {}
    table = document.get("phase_labels")
    assert isinstance(table, dict), (
        "pr.convention.yaml must carry a phase_labels table — it is the one "
        f"representation of merge eligibility; got {table!r}"
    )
    return table


def test_the_answer_follows_the_convention_not_a_python_literal(tmp_path: Path) -> None:
    """Vary the table, and the verdict varies with it — with no Python edit."""
    convention = tmp_path / "pr.convention.yaml"
    convention.write_text(
        yaml.safe_dump({"phase_labels": {"merge_allowed": ["COMPLETE"]}}),
        encoding="utf-8",
    )

    allowed = elig.merge_allowed_phases(convention)
    assert tuple(allowed) == ("COMPLETE",)
    assert elig.is_merge_blocked("REFACTOR", allowed=allowed), (
        "REFACTOR is not in this table's merge_allowed, so the seam must call it "
        "blocked — otherwise the answer is coming from somewhere other than the table"
    )
    assert not elig.is_merge_blocked("COMPLETE", allowed=allowed)


def test_the_repository_table_admits_only_refactor_and_complete() -> None:
    """The authoritative statement, as the rule's description has always read it."""
    assert tuple(elig.merge_allowed_phases()) == ("REFACTOR", "COMPLETE"), (
        "phase_labels.merge_allowed is the one statement of which phases may carry "
        "an auto-closing PR; the rule description and the REFACTOR operator sign-off "
        "(#1611) put SMOKE outside it"
    )


def test_blocked_is_the_complement_over_the_whole_phase_machine() -> None:
    """Every phase the machine declares is decided, and decided by one rule."""
    machine = yaml.safe_load(_PHASE_MACHINE.read_text(encoding="utf-8")) or {}
    phases = list((machine.get("phases") or {}).keys())
    assert phases, "precondition failed: phase_machine.convention.yaml declares no phases"

    allowed = set(elig.merge_allowed_phases())
    for phase in phases:
        assert elig.is_merge_blocked(phase) is (phase not in allowed), (
            f"atdd:{phase} must be blocked exactly when it is outside merge_allowed"
        )
    assert elig.is_merge_blocked("A_PHASE_NOBODY_HAS_INVENTED_YET") is True


def test_the_convention_holds_no_second_list_to_drift_against() -> None:
    """merge_blocked and out_of_scope were the complement, written by hand."""
    table = _phase_labels()
    assert "merge_allowed" in table
    for key in ("merge_blocked", "out_of_scope"):
        assert key not in table, (
            f"phase_labels.{key} is a hand-maintained complement of merge_allowed — "
            "the drift seam this issue exists to remove. Derive it instead."
        )


def test_the_validator_declares_no_phase_set_of_its_own() -> None:
    """No literal phase names left in the enforcement to fall out of step."""
    source = Path(mod.__file__).read_text(encoding="utf-8")

    assert "_BLOCKED_PHASES" not in source, (
        "the frozenset of blocked phases is the second copy this acceptance removes"
    )
    for phase in ("INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"):
        assert f'"{phase}"' not in source and f"'{phase}'" not in source, (
            f"the validator still names {phase!r} as a literal; the phase set must "
            "come from pr.convention.yaml::phase_labels.merge_allowed"
        )

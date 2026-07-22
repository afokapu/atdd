# URN: test:enforce-conventions-ci:E003-SMOKE-001-real-baseline-neutralizes-the-live-debt
# Acceptance: acc:enforce-conventions-ci:E003-SMOKE-001-real-baseline-neutralizes-the-live-debt
# WMBT: wmbt:enforce-conventions-ci:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:enforce-conventions-ci:E003-SMOKE-001-real-baseline-neutralizes-the-live-debt.

Over the repository's REAL committed ``.atdd/enforce-ratchet.yaml`` and REAL
``.atdd/binding.lock.yaml``:

  * applying the real baseline to the verdicts it was recorded from yields PASS /
    exit 0 — the blocking job (E001) is green over the live debt;
  * regressing any single baselined rule by ONE violation flips that same run to
    FAIL / exit 1 — the ratchet is live, not a blanket exemption;
  * every rule the register names is a rule the real lock actually BINDS, so the
    register cannot drift into granting allowances to rules nobody enforces.

This drives the real ``atdd.enforce.ratchet`` reader over the real committed files
(no mocks). It deliberately does NOT re-run the full `atdd enforce` scan — that is
a multi-minute tree-sitter subprocess sweep whose live counts are what the CI job
itself asserts; what is proven here is that the committed REGISTER faithfully
neutralizes the debt it records and still bites on a regression.
"""
from __future__ import annotations

from dataclasses import replace

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.ratchet import BASELINED, RATCHET_PATH, apply_ratchet, load_baseline
from atdd.enforce.registry import _bound_convention_ids
from atdd.enforce.runner import EnforceResult, RuleVerdict

WS = "atdd.workspace.python-pytest"


def _recorded_result(baseline: dict[str, int]) -> EnforceResult:
    """The enforce result the committed baseline was recorded FROM.

    Each registered rule failing with exactly the violation count the register
    pins it at — i.e. the live state of the repository at the moment the enforce
    job was made blocking.
    """
    return EnforceResult(
        verdicts=[
            RuleVerdict(
                rule_id, WS, "fail",
                raw_violation_count=count,
                locations=[f"src/atdd/x.py:{i}:0" for i in range(min(count, 3))],
                detail=f"{count} violation(s)",
            )
            for rule_id, count in sorted(baseline.items())
        ],
        report="",
    )


def test_real_baseline_neutralizes_the_live_debt() -> None:
    repo = find_repo_root()
    baseline = load_baseline(repo / RATCHET_PATH)

    # The register is not empty — the repository genuinely carries enforcement debt,
    # which is the whole reason the blocking flip needs a ratchet.
    assert baseline, "the committed ratchet baseline registers no rule at all"

    recorded = _recorded_result(baseline)
    assert recorded.exit_code == 1, "un-ratcheted, the recorded debt fails the build"

    # 1. The real baseline holds the real debt flat -> the blocking job is GREEN.
    ratcheted = apply_ratchet(recorded, baseline)
    assert ratcheted.passed is True
    assert ratcheted.exit_code == 0
    assert all(v.status == BASELINED for v in ratcheted.verdicts)


def test_regressing_any_single_baselined_rule_by_one_violation_fails_the_gate() -> None:
    repo = find_repo_root()
    baseline = load_baseline(repo / RATCHET_PATH)
    recorded = _recorded_result(baseline)

    # 2. The ratchet is LIVE: +1 violation on ANY registered rule reds the build.
    for victim in sorted(baseline):
        regressed = EnforceResult(
            verdicts=[
                replace(v, raw_violation_count=v.raw_violation_count + 1)
                if v.rule_id == victim
                else v
                for v in recorded.verdicts
            ],
            report="",
        )
        ratcheted = apply_ratchet(regressed, baseline)
        assert ratcheted.exit_code == 1, (
            f"regressing {victim} by one violation did NOT fail the gate — "
            f"the ratchet is a blanket exemption, not a ratchet"
        )
        failing = [v.rule_id for v in ratcheted.verdicts if v.failed]
        assert failing == [victim], f"expected only {victim} to fail, got {failing}"


def test_every_registered_rule_is_a_rule_the_real_lock_actually_binds() -> None:
    repo = find_repo_root()
    baseline = load_baseline(repo / RATCHET_PATH)

    # 3. The register cannot drift into naming rules that are not enforced: an
    #    allowance for an unbound rule would be dead weight hiding a real gap.
    bound = _bound_convention_ids(repo)
    unbound = sorted(set(baseline) - set(bound))
    assert not unbound, (
        f"the ratchet baseline registers {len(unbound)} rule(s) the real "
        f"binding.lock does not bind: {unbound}"
    )

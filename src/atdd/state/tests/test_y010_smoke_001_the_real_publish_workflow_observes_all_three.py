# URN: test:govern-lifecycle:release-state-is-observed-not-inferred:Y010-SMOKE-001-the-real-publish-workflow-observes-all-three
# Acceptance: acc:govern-lifecycle:Y010-SMOKE-001-the-real-publish-workflow-observes-all-three
# WMBT: wmbt:govern-lifecycle:Y010
# Phase: SMOKE
# Layer: integration
"""Y010-SMOKE-001 — the shipped publish workflow, not a copy of it (#1924).

The UNIT tests prove the decision logic and the observers. Neither says anything
about the file that actually runs, and the defect lived entirely in the wiring:
the logic for "is this released" was one `git describe` in a YAML step.

This reads `.github/workflows/publish.yml` itself and asserts the shape, in the
same style as the existing #1285/#1326 publish-workflow smokes.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

pytestmark = [pytest.mark.platform]

WORKFLOW = pathlib.Path(__file__).resolve().parents[4] / ".github" / "workflows" / "publish.yml"


@pytest.fixture(scope="module")
def steps() -> list:
    assert WORKFLOW.is_file(), f"publish workflow not found at {WORKFLOW}"
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return doc["jobs"]["tag-release"]["steps"]


@pytest.fixture(scope="module")
def text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _step(steps: list, name_fragment: str) -> dict:
    for s in steps:
        if name_fragment.lower() in (s.get("name") or "").lower():
            return s
    raise AssertionError(f"no step matching {name_fragment!r} in {[s.get('name') for s in steps]}")


def test_the_gate_calls_release_state(text: str) -> None:
    """THE FIX: all three artifacts, observed."""
    assert "atdd state version release-state" in text, (
        "the publish gate does not consult release-state"
    )


def test_the_gate_no_longer_decides_from_git_describe_alone(steps: list) -> None:
    """THE DEFECT. `git describe` may still READ the tag — that is the version's
    identity, and the whole point of probe_reachable in the lab — but it must not
    be what decides `already_released`.

    Asserted over the step's executable lines, not the file text: the comment
    block above the step quotes the old `git describe ... already_released=true`
    to explain the defect, and a naive text search matches its own documentation.
    It did, first time.
    """
    gate = _step(steps, "Establish the release state")
    assignments = [
        line.strip() for line in gate["run"].splitlines()
        if "already_released=" in line and not line.strip().startswith("#")
    ]
    assert assignments, "the gate sets no already_released output at all"
    for line in assignments:
        assert "ACTION" in line, (
            f"already_released is derived from something other than the observed "
            f"action: {line}"
        )


def test_the_bump_runs_only_when_no_release_is_in_flight(steps: list) -> None:
    """THE TRAP the lab found: on PARTIAL, bumping abandons the half-published
    version. The bump must be gated on ABSENT, not merely on 'not skipped'."""
    bump = _step(steps, "Reconcile + bump")
    assert bump.get("if") == "steps.idem.outputs.state == 'ABSENT'", bump.get("if")


def test_a_partial_release_stops_the_run_loudly(steps: list) -> None:
    """Silence is what let two versions rot."""
    refuse = _step(steps, "Refuse to bump past a partial release")
    assert refuse.get("if") == "steps.idem.outputs.state == 'PARTIAL'"
    assert "::error" in refuse["run"], "a partial release must be an error annotation"
    assert "exit 1" in refuse["run"], "a partial release must fail the job"


def test_the_refusal_precedes_the_publish_steps(steps: list) -> None:
    """Ordering is load-bearing: the drain step is still conditioned on
    already_released == 'false', which is true for PARTIAL as well. The refusal
    has to run first, or a partial release would fall through to a publish."""
    names = [(s.get("name") or "") for s in steps]
    refuse_at = next(i for i, n in enumerate(names) if "Refuse to bump past" in n)
    drain_at = next(i for i, n in enumerate(names) if "Drain version_decided" in n)
    assert refuse_at < drain_at, f"refusal at {refuse_at}, drain at {drain_at}"


def test_the_gate_can_still_pass_a_clean_commit(steps: list) -> None:
    """The ordinary path must survive: nothing released yet -> bump and publish."""
    assert _step(steps, "Reconcile + bump").get("if") == "steps.idem.outputs.state == 'ABSENT'"
    assert _step(steps, "Drain version_decided") is not None


def test_the_gate_has_a_token_to_ask_github_with(steps: list) -> None:
    """The release lookup is an authenticated REST call; without GH_TOKEN it would
    return UNKNOWN on every run and refuse every release."""
    gate = _step(steps, "Establish the release state")
    assert "GH_TOKEN" in (gate.get("env") or {}), gate.get("env")

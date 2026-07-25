# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1602 Convergence A — the smoke-execution gate is OPT-IN, per issue.

Fail-closed is only half a gate. Applied to every issue in the repo it demands a
live-smoke attestation from work that never promised one — an obligation with no
way to discharge it, whose only exit is ``--force``. A gate you can only get past
by forcing is a rubber stamp, and it is *worse* than no gate, because now the
forcing is routine. So the check asks a prior question, and this file is the proof
that it asks the right one, in all three directions:

    issue declares NO live_smoke acceptance   -> PASS  (not applicable)
    issue declares one, and smoke RAN         -> PASS  (attested)
    issue declares one, and smoke did NOT run -> FAIL  (fail-closed, teeth intact)

Row 1 is the safety property that makes enabling the gate a non-event for the rest
of the repo. Row 3 is the teeth. Row 2 is the negative control without which the
other two are satisfied by a gate that is simply wrong in both directions.

THE TRAP THIS FILE EXISTS TO KEEP CLOSED.
``smoke_attestation.plan_declares_live_smoke`` answers "does the REPO declare any
live_smoke acceptance". It is the right question for the pytest hook and the wrong
one here: it went ``True`` for this repo the moment E069 landed, so an opt-in wired
to it would re-gate every issue in the repo on the very commit that made the gate
satisfiable. ``test_an_unrelated_issue_is_not_gated_by_someone_elses_acceptance``
is that trap, injected: a repo whose ``plan/`` genuinely declares a live_smoke
acceptance, and an issue that is simply not bound to it. Wire the opt-in
repo-level and that test — and only that test — goes red.

Every case runs the real ``SmokeExecutionGateCheck`` against a real migrated State
Store under an isolated Control Root. Attestations are written through the real
producer API (``record_smoke_execution``); nothing here hand-places a record the
gate then reads back.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from atdd.coach.gate.decision import GateContext
from atdd.coach.gate.live_smoke import (
    ACCEPTANCE_URN,
    FEATURE_URN,
    WMBT_URN,
    write_live_smoke_plan_scope,
)
from atdd.coach.gate.smoke_execution_check import SmokeExecutionGateCheck
from atdd.coach.gate.smoke_obligation import LIVE_SMOKE_KIND, live_smoke_obligation
from atdd.state.evidence import SmokeRun, open_state_store, record_smoke_execution

pytestmark = [pytest.mark.platform]

ISSUE = 1602
UID = "smoke-execution-gate-wiring"

#: A second issue in the same repo, bound to nothing. Stands in for #1595/#1596/
#: #1597 and the ~780 other work items that must not notice this gate exists.
OTHER_ISSUE = 1595
OTHER_UID = "interlocking-layout-config-driven"

#: A feature whose WMBT declares an acceptance that is NOT live_smoke. Declaring a
#: plan scope is not the same as declaring a live-smoke obligation, and a resolver
#: that confused the two would gate on ``execution_kind`` it never read.
HERMETIC_FEATURE_URN = "feature:quiet-wagon:no-live-smoke"
HERMETIC_FEATURE_YAML = """\
urn: feature:quiet-wagon:no-live-smoke
wmbts:
  - wmbt:quiet-wagon:E001
"""
HERMETIC_WMBT_YAML = """\
urn: wmbt:quiet-wagon:E001
acceptances:
  - identity:
      urn: acc:quiet-wagon:E001-UNIT-001-hermetic
      phase: GREEN
    execution_kind: hermetic_integration
"""


# --------------------------------------------------------------------------- #
# Fixtures — one repo, one store, issues bound to whatever the case needs      #
# --------------------------------------------------------------------------- #
@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated worktree whose Control Root is itself.

    ``ATDD_CONTROL_ROOT`` pins every store read and write inside ``tmp_path``, so
    no case here can consult — or disturb — the developer's real store.
    """
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


def _register(repo: Path, uid: str, issue: int, data: Optional[dict] = None) -> None:
    """Seed a work item in SMOKE and the GitHub ref the gate resolves it by."""
    with open_state_store(control_root=repo) as store:
        store.objects.upsert(uid, "work_item", state="SMOKE", data=data or {})
        store.external_refs.link(uid, "github", "issue", str(issue))


def _attest(repo: Path, uid: str) -> None:
    """Record one passing live-smoke run through the real producer API."""
    with open_state_store(control_root=repo) as store:
        record_smoke_execution(store, uid, SmokeRun(
            nodeid="tests/integration/test_live.py::test_chain",
            outcome="passed", duration_s=3.1, execution_kind=LIVE_SMOKE_KIND,
        ))


def _verdict(repo: Path, issue: int = ISSUE):
    """The real SMOKE->REFACTOR verdict for *issue* in *repo*."""
    return SmokeExecutionGateCheck().run(GateContext(
        issue_number=issue, from_phase="SMOKE", to_phase="REFACTOR", worktree=repo,
    ))


def _write_hermetic_scope(repo: Path) -> dict:
    """A plan scope that declares an acceptance, but not a live-smoke one."""
    wagon = repo / "plan" / "quiet_wagon"
    (wagon / "features").mkdir(parents=True, exist_ok=True)
    (wagon / "E001.yaml").write_text(HERMETIC_WMBT_YAML)
    (wagon / "features" / "no_live_smoke.yaml").write_text(HERMETIC_FEATURE_YAML)
    return {"feature": HERMETIC_FEATURE_URN}


# --------------------------------------------------------------------------- #
# Direction 1 — no obligation => PASS (the safety property)                    #
# --------------------------------------------------------------------------- #
def test_an_issue_that_declares_no_live_smoke_acceptance_is_not_gated(repo: Path) -> None:
    """The common case, and the one that makes enabling the gate safe.

    ~780 work items in this repo declare no plan scope at all. If the gate held
    them to a live-smoke run they could not produce one, and SMOKE->REFACTOR would
    be reachable for them only through ``--force``.
    """
    _register(repo, UID, ISSUE)

    verdict = _verdict(repo)

    assert verdict.passed, (
        f"an issue that never declared a live_smoke acceptance was gated on one — "
        f"this is the trap the opt-in exists to prevent: {verdict.message}"
    )
    assert "not applicable" in verdict.message
    assert "declares no live_smoke acceptance" in verdict.message


def test_declaring_a_plan_scope_is_not_declaring_a_live_smoke_acceptance(repo: Path) -> None:
    """A feature exists, a WMBT exists, an acceptance exists — none are live_smoke.

    The resolver must read ``execution_kind``, not merely find plan artifacts. A
    scope-shaped-therefore-obligated shortcut would gate every issue that ever had
    a feature written for it.
    """
    _register(repo, UID, ISSUE, _write_hermetic_scope(repo))

    verdict = _verdict(repo)

    assert verdict.passed, f"a hermetic acceptance was read as a live-smoke obligation: {verdict.message}"
    assert "not applicable" in verdict.message


def test_an_unrelated_issue_is_not_gated_by_someone_elses_acceptance(repo: Path) -> None:
    """THE regression guard: the repo declares live_smoke; this issue does not.

    This is exactly the shape of the repo after E069 landed — one live_smoke
    acceptance in ``plan/``, and hundreds of issues with nothing to do with it. A
    repo-level opt-in (``plan_declares_live_smoke``) passes every other test in
    this file and fails this one.
    """
    obligated_data = write_live_smoke_plan_scope(repo)
    _register(repo, UID, ISSUE, obligated_data)
    _register(repo, OTHER_UID, OTHER_ISSUE)

    assert not _verdict(repo, ISSUE).passed, (
        "precondition: the issue that DID declare the acceptance must still be gated, "
        "or the row below passes because the gate is inert"
    )

    other = _verdict(repo, OTHER_ISSUE)
    assert other.passed, (
        f"#{OTHER_ISSUE} was gated by an acceptance declared by #{ISSUE} — the "
        f"obligation is being read repo-wide instead of per issue: {other.message}"
    )
    assert "not applicable" in other.message


# --------------------------------------------------------------------------- #
# Direction 2 — obligation + a run => PASS (the negative control)              #
# --------------------------------------------------------------------------- #
def test_an_obligated_issue_with_a_passing_run_opens_the_gate(repo: Path) -> None:
    """Declared and discharged. Without this, refusing everything would "pass"."""
    _register(repo, UID, ISSUE, write_live_smoke_plan_scope(repo))
    _attest(repo, UID)

    verdict = _verdict(repo)

    assert verdict.passed, (
        f"a declared live_smoke acceptance was discharged by a real passing run and "
        f"the gate still refused: {verdict.message}"
    )
    assert ACCEPTANCE_URN in verdict.message, (
        "the pass must name what was owed, or an operator cannot tell an attested "
        "transition from a not-applicable one"
    )


# --------------------------------------------------------------------------- #
# Direction 3 — obligation, no run => FAIL (the teeth)                         #
# --------------------------------------------------------------------------- #
def test_an_obligated_issue_with_no_run_is_refused(repo: Path) -> None:
    """Declared and not discharged. Opt-in must not have filed the teeth off."""
    _register(repo, UID, ISSUE, write_live_smoke_plan_scope(repo))

    verdict = _verdict(repo)

    assert not verdict.passed, (
        "an issue declaring a live_smoke acceptance passed SMOKE->REFACTOR with no "
        "attestation — the opt-in check swallowed the fail-closed path"
    )
    assert ACCEPTANCE_URN in verdict.message, (
        f"the refusal must name the acceptance that is owed: {verdict.message}"
    )
    assert "no smoke-execution attestation" in verdict.message


# --------------------------------------------------------------------------- #
# The mapping itself — issue -> obligation, resolved by identity               #
# --------------------------------------------------------------------------- #
def test_the_obligation_is_resolved_through_the_features_wmbts(tmp_path: Path) -> None:
    """``data.feature`` -> feature file -> its WMBTs -> their live_smoke acceptances."""
    data = write_live_smoke_plan_scope(tmp_path)
    assert data == {"feature": FEATURE_URN}

    obligation = live_smoke_obligation(tmp_path, data)

    assert obligation.acceptance_urns == (ACCEPTANCE_URN,)
    assert obligation.scopes == (FEATURE_URN,)
    assert bool(obligation) is True


def test_a_train_scoped_live_smoke_acceptance_binds_the_trains_issues(tmp_path: Path) -> None:
    """Train files carry ``acceptances[]`` too, and they bind the same way.

    No train in this repo declares one today; leaving trains unread would make
    that a silent hole the first time one does.
    """
    trains = tmp_path / "plan" / "_trains"
    trains.mkdir(parents=True)
    (trains / "0003-author-substrate.yaml").write_text(
        "acceptances:\n"
        "  - identity:\n"
        "      urn: acc:author-substrate:TRAIN-SMOKE-001\n"
        f"    execution_kind: {LIVE_SMOKE_KIND}\n"
    )

    obligation = live_smoke_obligation(tmp_path, {"train": "0003-author-substrate"})

    assert obligation.acceptance_urns == ("acc:author-substrate:TRAIN-SMOKE-001",)


@pytest.mark.parametrize(
    "data, why",
    [
        ({}, "an empty data bag"),
        ({"feature": None, "train": None}, "explicit nulls"),
        ({"feature": "feature:gone:missing"}, "a feature URN with no file on disk"),
        ({"feature": "not-a-urn"}, "a value that is not a typed URN"),
        ({"train": "0000-never-existed"}, "a train id with no file on disk"),
    ],
)
def test_nothing_resolvable_means_nothing_owed(tmp_path: Path, data, why) -> None:
    """An obligation this resolver cannot SEE is one it must not INVENT.

    Fail-closed lives inside a declared obligation, not in front of it: turning an
    unresolvable reference into a blocked lifecycle would re-create the trap for a
    typo. The planner validators are what fail on a dangling plan reference.
    """
    obligation = live_smoke_obligation(tmp_path, data)

    assert obligation.acceptance_urns == (), f"{why} produced an obligation out of nothing"
    assert bool(obligation) is False


def test_an_unreadable_plan_file_owes_nothing_rather_than_exploding(tmp_path: Path) -> None:
    """Malformed YAML in ``plan/`` must not take the lifecycle down with it."""
    wagon = tmp_path / "plan" / "smoke_gate_probe"
    (wagon / "features").mkdir(parents=True)
    (wagon / "features" / "live_smoke_executes.yaml").write_text("{[not: valid: yaml")

    assert live_smoke_obligation(tmp_path, {"feature": FEATURE_URN}).acceptance_urns == ()


def test_the_scope_description_distinguishes_no_scope_from_an_empty_one() -> None:
    """"Owes nothing" reads differently depending on WHY, and operators need both."""
    from atdd.coach.gate.smoke_obligation import SmokeObligation

    assert "no plan scope" in SmokeObligation().describe_scope()
    assert FEATURE_URN in SmokeObligation(scopes=(FEATURE_URN,)).describe_scope()


def test_live_smoke_kind_matches_the_attestation_writer() -> None:
    """The opt-in and the attestation must agree on what "live smoke" means.

    ``smoke_obligation`` restates the literal rather than importing it, to keep
    coach off tester. This is the tie that makes the restatement safe: drift here
    would mean the gate demands a kind the hook never records, and every obligated
    issue would be permanently blocked.
    """
    from atdd.tester.substrate.smoke_attestation import (
        LIVE_SMOKE_KIND as WRITER_KIND,
    )

    assert LIVE_SMOKE_KIND == WRITER_KIND


def test_the_probe_wmbt_urn_resolves_to_where_the_harness_writes_it(tmp_path: Path) -> None:
    """The harness fixture obeys the URN->path mapping the resolver depends on.

    If ``write_live_smoke_plan_scope`` ever put the WMBT somewhere its URN does not
    name, the obligation above would silently become empty and every fail-closed
    test in this issue would go green for the wrong reason.
    """
    write_live_smoke_plan_scope(tmp_path)

    wagon = WMBT_URN.split(":")[1].replace("-", "_")
    assert (tmp_path / "plan" / wagon / "E001.yaml").is_file()

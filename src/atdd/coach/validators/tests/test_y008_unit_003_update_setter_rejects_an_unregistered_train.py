# URN: test:govern-lifecycle:bind-issue-train:Y008-UNIT-003-update-setter-rejects-an-unregistered-train
# Acceptance: acc:govern-lifecycle:Y008-UNIT-003-update-setter-rejects-an-unregistered-train
# WMBT: wmbt:govern-lifecycle:Y008
# Phase: GREEN
# Layer: presentation
# Runtime: python
# Assertion: behavioral
# Purpose: The deprecated `atdd update <N> --train` cross-references the registry on a BARE FIELD WRITE too, not only when a --status transition happens to run its gate.
"""GREEN test for acc:govern-lifecycle:Y008-UNIT-003-update-setter-rejects-an-unregistered-train.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:Y008

THE MEASURED DEFECT. ``IssueManager`` has owned a train cross-reference all along
(``_gate_train_crossref``), and ``update`` never called it on a bare field write:
the gate ran only from ``_transition_gates_pass``, which runs only when
``--status`` is supplied. So ``atdd update <N> --train train:bogus:does-not-exist``
wrote the string and printed "Updated". The command is deprecated but it is the
one the repository's own help text pointed operators at, so it must refuse too —
a deprecated path that still writes is still a write.

The registry reader behind that gate had a second defect this covers: it knew only
exact ``_trains.yaml`` entries and loose flat stems, so it REJECTED a legitimate
legacy alias — ``0042-couple-wagons`` here, ``0001-self-compliance-validate`` in
the live corpus — because it never opened ``_aliases.yaml``.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout

import pytest

from ._bind_issue_train_helpers import (
    ABSENT_TRAIN,
    CONSUMER_TRAIN,
    CONSUMER_TRAIN_LEGACY,
    control_root,
    write_consumer_plan_tree,
)

_ISSUE = 90160


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    """A real ``IssueManager`` over a NON-atdd plan tree, with its writes recorded.

    Only the two collaborators this acceptance is NOT about are stubbed: the
    GitHub read that resolves the issue, and the manifest-field writer. The train
    gate, the registry resolution and the ordering between them are all real.
    """
    from atdd.coach.commands.issue import IssueManager

    root = control_root(tmp_path)
    write_consumer_plan_tree(root)

    written: list = []
    mgr = IssueManager.__new__(IssueManager)
    mgr.target_dir = root
    monkeypatch.setattr(
        IssueManager, "_check_initialized", lambda self: True, raising=False
    )
    monkeypatch.setattr(
        IssueManager, "_resolve_issue",
        lambda self, issue_id: (_ISSUE, {"labels": [], "body": ""}, object()),
        raising=False,
    )
    monkeypatch.setattr(
        IssueManager, "_update_manifest_fields",
        lambda self, number, fields: written.append((number, dict(fields))),
        raising=False,
    )
    monkeypatch.setattr(
        IssueManager, "_branch_prefix_allowed", lambda self, branch: True, raising=False
    )
    return mgr, written


def _update(mgr, **kwargs) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        rc = mgr.update(issue_id=str(_ISSUE), **kwargs)
    return rc, out.getvalue()


def test_a_registered_train_is_written(manager) -> None:
    mgr, written = manager

    rc, out = _update(mgr, train=CONSUMER_TRAIN)

    assert rc == 0, f"a registered train was refused (exit {rc}): {out!r}"
    assert written == [(_ISSUE, {"train": CONSUMER_TRAIN})], (
        f"the registered train did not reach the writer: {written!r}"
    )


def test_a_resolvable_legacy_alias_is_written(manager) -> None:
    """The old reader never opened the alias map, so it rejected exactly this."""
    mgr, written = manager

    rc, out = _update(mgr, train=CONSUMER_TRAIN_LEGACY)

    assert rc == 0, (
        f"a legacy id the alias map resolves was refused (exit {rc}): {out!r}"
    )
    assert written == [(_ISSUE, {"train": CONSUMER_TRAIN_LEGACY})]


def test_an_unregistered_train_is_refused(manager) -> None:
    """The proven defect: this used to exit 0 and print "Updated"."""
    mgr, written = manager

    rc, out = _update(mgr, train=ABSENT_TRAIN)

    assert rc != 0, (
        f"`atdd update --train {ABSENT_TRAIN}` exited 0 — it still writes any "
        f"string at all: {out!r}"
    )
    assert written == [], f"a refused update still wrote: {written!r}"


def test_a_refused_update_writes_none_of_its_other_fields(manager) -> None:
    """Fail closed across the whole request, not per field.

    A refusal that let ``--branch`` through would leave the issue half-updated by
    a command that reported failure.
    """
    mgr, written = manager

    rc, _out = _update(
        mgr, train=ABSENT_TRAIN, branch="feat/some-branch", archetypes="coach"
    )

    assert rc != 0
    assert written == [], (
        f"a request refused for its train still applied its other fields: {written!r}"
    )


def test_the_refusal_names_the_registry_and_a_candidate(manager) -> None:
    """Parity with the create and revise refusals — one failure, one explanation."""
    mgr, _written = manager

    _rc, out = _update(mgr, train=ABSENT_TRAIN)

    assert "plan/_trains.yaml" in out, f"the registry is not named: {out!r}"
    assert CONSUMER_TRAIN in out, f"no resolvable candidate is listed: {out!r}"
    assert "atdd author train" in out, (
        f"the refusal does not say how to author the train instead: {out!r}"
    )


def test_a_write_naming_no_train_is_unaffected(manager) -> None:
    """The guard costs the other fields nothing."""
    mgr, written = manager

    rc, out = _update(mgr, branch="feat/unrelated")

    assert rc == 0, f"a train-free update was refused (exit {rc}): {out!r}"
    assert written == [(_ISSUE, {"branch": "feat/unrelated"})]


def test_the_gate_resolves_through_the_shared_primitive(manager) -> None:
    """One resolution, or the three setters disagree about the same value.

    Asserted through behaviour rather than by reading the import: the alias case
    above only passes if the gate went through the primitive, because nothing
    else in coach reads ``_aliases.yaml``.
    """
    mgr, _written = manager

    valid, messages = mgr._validate_train_against_trains_yaml(CONSUMER_TRAIN_LEGACY)

    assert valid, f"the gate did not resolve the alias: {messages!r}"
    assert any(CONSUMER_TRAIN in message for message in messages), (
        f"the gate's own message does not name the canonical train it resolved "
        f"to: {messages!r}"
    )

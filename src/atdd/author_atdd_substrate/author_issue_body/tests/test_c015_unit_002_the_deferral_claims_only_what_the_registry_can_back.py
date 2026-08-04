# URN: test:govern-lifecycle:honest-outbox-deferral:C015-UNIT-002-the-deferral-claims-only-what-the-registry-can-back
# Acceptance: acc:govern-lifecycle:C015-UNIT-002-the-deferral-claims-only-what-the-registry-can-back
# WMBT: wmbt:govern-lifecycle:C015
# Phase: GREEN
# Runtime: python
# Layer: application
# Assertion: behavioral
# Purpose: The sentence an operator reads on deferral is derived from the registered providers at the moment of enqueue instead of asserted.
"""C015-UNIT-002 — the deferral claims only what the registry can back.

``_print_publish_outcome`` prints "github projection deferred to the outbox
(durable retry)" whenever ``projection_deferred`` is set. It consults nothing and
decides nothing. Measured 2026-08-03: ``discover_providers()`` returns ``{}``, so
every one of the 30 rows that sentence was printed over had nowhere to go — and
the oldest has been there since 2026-07-09.

The correction is to the claim, not to the behaviour behind it. The store write
must still stand and the exit code must not move; what changes is that the
operator is told which of the two situations they are in, decided from the
registry at the moment the row is enqueued.

RED state: ``PublishResult``/``RevisionResult`` carry no deliverability, and the
printed line says "durable retry" unconditionally.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from atdd.planner.commands.author import _print_publish_outcome, _print_revise_outcome
from atdd.planner.commands.author_publish import publish_issue, revise_issue
from atdd.state.providers import clear_providers, register_provider

ISSUE_NUMBER = 1711
SLUG = "deferral-probe"


class _AcceptingProvider:
    """A registered SyncProvider. It is never called here — only its registration
    is under test, because that is what the deferral message must consult."""

    name = "github"

    def push(self, operation, payload) -> None:  # pragma: no cover - never invoked
        return None


@pytest.fixture(autouse=True)
def _empty_registry():
    """Every leg states its own registry, and none leaks into the next."""
    clear_providers()
    yield
    clear_providers()


@pytest.fixture()
def control_root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


def _seed_issue(control_root: Path) -> None:
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=control_root))
    try:
        create_work_item(
            conn, SLUG, state="INIT",
            data={"title": "probe", "type": "implementation", "body": "old body"},
            github_number=ISSUE_NUMBER,
        )
    finally:
        conn.close()


def _fail_the_projection(monkeypatch) -> None:
    """The deferral branch is the one under test, so the projection must not land."""
    def _boom(*_args, **_kwargs):
        raise RuntimeError("github unreachable")

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_body", _boom, raising=False)
    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.create_issue", _boom, raising=False)


def _revise(control_root: Path, monkeypatch, *, body: str = "new body"):
    _fail_the_projection(monkeypatch)
    return revise_issue(body=body, issue_number=ISSUE_NUMBER, control_root=control_root)


def _rendered(capsys) -> str:
    return capsys.readouterr().err


# --------------------------------------------------------------------------- #
# No provider registered — the live repository's state                        #
# --------------------------------------------------------------------------- #
def test_with_no_provider_the_line_does_not_claim_a_durable_retry(
    control_root, monkeypatch, capsys
):
    """The promise that let 30 rows sit for 25 days."""
    _seed_issue(control_root)

    result = _revise(control_root, monkeypatch)
    _print_revise_outcome(result)

    assert result.projection_deferred is True
    assert result.deferral_deliverable is False
    line = _rendered(capsys)
    assert "durable retry" not in line
    assert "github" in line


def test_with_no_provider_the_line_says_the_write_did_not_land(
    control_root, monkeypatch, capsys
):
    """"Deferred" implies later. With an empty registry there is no later, and the
    operator has to be told that rather than left to infer it."""
    _seed_issue(control_root)

    _print_revise_outcome(_revise(control_root, monkeypatch))

    line = _rendered(capsys).lower()
    assert "no" in line and "provider" in line, (
        "the line must name the absent registration as the reason nothing will send it"
    )


def test_the_create_path_carries_the_same_verdict(control_root, monkeypatch, capsys):
    """`publish_issue` defers through the same seam and must not claim more than it."""
    _fail_the_projection(monkeypatch)

    result = publish_issue(
        "created-probe", "body", title="probe", control_root=control_root,
    )
    _print_publish_outcome("created-probe", result)

    assert result.projection_deferred is True
    assert result.deferral_deliverable is False
    assert "durable retry" not in _rendered(capsys)


# --------------------------------------------------------------------------- #
# A provider registered — the claim becomes backable                          #
# --------------------------------------------------------------------------- #
def test_with_a_provider_registered_the_line_names_the_drain(
    control_root, monkeypatch, capsys
):
    """Naming `atdd state sync --push` is the whole of "deferred to a retry": the
    command exists, and today the message leaves the operator to already know it."""
    _seed_issue(control_root)
    register_provider("github", _AcceptingProvider)

    result = _revise(control_root, monkeypatch)
    _print_revise_outcome(result)

    assert result.deferral_deliverable is True
    assert "atdd state sync --push" in _rendered(capsys)


def test_the_claim_is_read_from_the_registry_and_not_from_a_constant(
    control_root, monkeypatch, capsys
):
    """The two legs differ by one registration and nothing else. If the verdict were
    a constant, this pair could not disagree."""
    _seed_issue(control_root)

    unregistered = _revise(control_root, monkeypatch).deferral_deliverable
    register_provider("github", _AcceptingProvider)
    registered = _revise(control_root, monkeypatch).deferral_deliverable

    assert (unregistered, registered) == (False, True)


# --------------------------------------------------------------------------- #
# What must NOT change                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("register", [False, True])
def test_the_store_write_stands_either_way(control_root, monkeypatch, register):
    """This corrects the claim, not the store-first guarantee behind it."""
    _seed_issue(control_root)
    if register:
        register_provider("github", _AcceptingProvider)

    _revise(control_root, monkeypatch, body="revised body")

    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=control_root))
    try:
        obj = StateStore(conn).objects.get(SLUG)
        pending = StateStore(conn).sync.pending_outbox()
    finally:
        conn.close()
    assert obj is not None and obj.data["body"] == "revised body"
    assert len(pending) == 1, "the row is still enqueued; only the sentence changed"


@pytest.mark.parametrize("register", [False, True])
def test_a_deferral_still_raises_nothing_and_returns_a_result(
    control_root, monkeypatch, register
):
    """The exit code is unchanged: a failed projection was never an error and must
    not become one here."""
    _seed_issue(control_root)
    if register:
        register_provider("github", _AcceptingProvider)

    result: Optional[object] = _revise(control_root, monkeypatch)

    assert result is not None and result.slug == SLUG

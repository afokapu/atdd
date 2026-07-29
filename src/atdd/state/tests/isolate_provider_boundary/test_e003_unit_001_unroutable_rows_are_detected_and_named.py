# URN: test:isolate-provider-boundary:surface-undrainable-outbox:E003-UNIT-001-unroutable-rows-are-detected-and-named
# Acceptance: acc:isolate-provider-boundary:E003-UNIT-001-unroutable-rows-are-detected-and-named
# WMBT: wmbt:isolate-provider-boundary:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Core names the non-empty-outbox + no-registered-receiver conjunction as a first-class condition — counting unroutable rows per routing key, dating the oldest, and flipping the same rows to routable the moment a receiver is registered — so a supported provider-free state can no longer be reported as health. Refs #1655.
"""Provider-free is supported. Provider-free *and silent* is the defect (E003-UNIT-001).

wagon: isolate-provider-boundary | feature: surface-undrainable-outbox | phase: RED
WMBT: wmbt:isolate-provider-boundary:E003

Zero registered providers is what this wagon exists to make safe, so this acceptance
must not assert that an empty registry is wrong. It asserts something narrower and
harder: that core can *tell the difference* between "provider-free and idle" and
"provider-free with decisions piling up behind it", and says which one it is in.

The routing rule is asserted against ``push_outbox`` itself rather than restated,
because a report that disagreed with a real drain would be a new way to mislead an
operator rather than a fix for the old one.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from atdd.state import providers as drain_registry
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore
from atdd.state.sync_engine import assess_drainability, push_outbox


class RecordingProvider:
    """A receiver that records what it was asked to push. Never raises."""

    name = "github"

    def __init__(self) -> None:
        self.pushed: list[tuple[str, Dict[str, Any]]] = []

    def push(self, operation: str, payload: Dict[str, Any]) -> Optional[Any]:
        self.pushed.append((operation, payload))
        return None


@pytest.fixture(autouse=True)
def empty_drain_registry():
    """The drain registry is process-global too — start and end at zero (#1655)."""
    drain_registry.clear_providers()
    yield
    drain_registry.clear_providers()


@pytest.fixture()
def store(tmp_path) -> StateStore:
    conn = connect(init_state_store(db_path=tmp_path / "state.sqlite"))
    return StateStore(conn)


def test_an_empty_outbox_with_no_providers_is_not_stranded(store: StateStore) -> None:
    """Provider-free and idle is healthy, and must not be reported as a fault."""
    report = assess_drainability(store, {})

    assert report.stranded is False, "zero providers with nothing queued is a supported state"
    assert report.pending == 0
    assert report.unroutable == 0
    assert "STRANDED" not in report.render()


def test_pending_rows_with_no_registered_receiver_are_named_unroutable(store: StateStore) -> None:
    """The conjunction — non-empty AND unroutable — is what gets reported."""
    store.sync.enqueue_outbox("github", "version_decided", {"version": "4.23.0"})
    store.sync.enqueue_outbox("github", "create_issue", {"title": "something"})
    store.sync.enqueue_outbox("gitlab", "create_issue", {"title": "elsewhere"})

    report = assess_drainability(store, {})

    assert report.stranded is True
    assert report.pending == 3
    assert report.unroutable == 3
    assert report.routable == 0
    # Counted per routing key, because "3 stranded" does not tell an operator which
    # provider they are missing.
    assert report.unroutable_by_provider == {"github": 2, "gitlab": 1}
    assert report.registered == []

    rendered = report.render()
    assert "STRANDED OUTBOX" in rendered
    assert "github (2)" in rendered and "gitlab (1)" in rendered
    # The remedy the old surface offered is explicitly withdrawn, not merely omitted.
    assert "CANNOT drain these" in rendered


def test_the_oldest_unroutable_row_is_dated(store: StateStore) -> None:
    """How long the silence has run is part of the finding, not a detail."""
    store.sync.enqueue_outbox("github", "create_issue", {"title": "first"})
    store.sync.enqueue_outbox("github", "create_issue", {"title": "second"})

    report = assess_drainability(store, {})

    assert report.oldest_unroutable_at is not None
    assert report.oldest_unroutable_at in report.render()


def test_registering_a_receiver_flips_the_same_rows_to_routable(store: StateStore) -> None:
    """Registration is the other fix, and the report must reflect it without a re-queue."""
    store.sync.enqueue_outbox("github", "create_issue", {"title": "a"})
    store.sync.enqueue_outbox("gitlab", "create_issue", {"title": "b"})

    before = assess_drainability(store, {})
    assert before.unroutable == 2

    after = assess_drainability(store, {"github": RecordingProvider()})

    assert after.stranded is True, "the gitlab row is still unroutable"
    assert after.routable == 1
    assert after.unroutable == 1
    assert after.unroutable_by_provider == {"gitlab": 1}
    assert after.registered == ["github"]


def test_the_report_agrees_with_what_a_real_drain_does_about_routing(store: StateStore) -> None:
    """The routing rule is push_outbox's, not a second implementation that can drift."""
    store.sync.enqueue_outbox("github", "create_issue", {"title": "routed"})
    store.sync.enqueue_outbox("gitlab", "create_issue", {"title": "unrouted"})
    provider = RecordingProvider()
    registry = {"github": provider}

    predicted = assess_drainability(store, registry)
    actual = push_outbox(store, registry)

    # What the report called routable is exactly what the drain pushed, and what it
    # called unroutable is exactly what the drain skipped for want of a provider.
    assert predicted.routable == actual.pushed == len(provider.pushed) == 1
    assert predicted.unroutable == actual.skipped_no_provider == 1

    # And the skipped row is still pending afterwards — core never assumes a provider.
    still_pending = {m.provider for m in store.sync.pending_outbox()}
    assert still_pending == {"gitlab"}

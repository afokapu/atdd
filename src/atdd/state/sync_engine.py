"""Provider-agnostic sync engine (#1201; refactor of #1184 Phase 5).

Synchronization is **agnostic**. Core owns the queues (`outbox`/`inbox`) and the
engine that drains them; it has **no GitHub (or any provider) knowledge**. A
provider — GitHub, Jira, cmux, … — is only needed for the *remote* side of a
push, and is supplied as a registered :class:`SyncProvider` keyed by name. The
inbox-apply side is fully generic: canonical events resolve an `external_ref`
and mutate local state, no provider required.

Consequences:
- a pure-local consumer with no provider installed still has a working sync
  substrate — outbox messages simply stay pending (no provider → skipped), and
  `apply_inbox` works for whatever canonical events exist;
- extensions implement provider-specific syncing compliant with this contract;
- **core never imports or needs GitHub.**

Dependency discipline: stdlib only + ``atdd.state`` (foundational layer).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Protocol

from atdd.state.store import StateStore

_log = logging.getLogger(__name__)

# Canonical, provider-neutral inbox event kinds.
EVENT_EXTERNAL_STATE = "external_state"        # remote state change → set local object state
EVENT_EXTERNAL_IMPORTED = "external_imported"  # remote item imported → upsert local object + ref


@dataclass(frozen=True)
class PushOutcome:
    """What a provider's push produced — an optional external ref for core to record."""

    object_uid: Optional[str] = None
    ref_kind: Optional[str] = None
    ref_value: Optional[str] = None
    ref_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def records_ref(self) -> bool:
        return bool(self.object_uid and self.ref_kind and self.ref_value)


class SyncProvider(Protocol):
    """Remote side of sync. Implemented by extensions (GitHub, Jira, …).

    A provider MUST implement :meth:`push` (local→remote). It MAY additionally
    implement an ``ingest(store)`` method (remote→local) that fills the inbox with
    canonical events from its remote; :func:`ingest_inbox` drives it via ``hasattr``
    so push-only providers stay valid. Core never knows what the provider polls — it
    only calls these hooks, so the engine remains fully provider-agnostic.
    """

    name: str

    def push(self, operation: str, payload: Dict[str, Any]) -> Optional[PushOutcome]:
        """Perform one local→remote operation; return an external ref to record (or None)."""


class OutboxVerdict(str, Enum):
    """What a drain run has to say, in four states rather than an exit code (#1711/C015).

    ``PushResult`` carried counts only, and its one caller returned non-zero on
    ``failed`` alone. So the two outcomes an operator most needs to tell apart —
    "the queue is empty" and "there is nowhere to send it" — produced the same
    answer: ``0 pushed, 0 failed``, exit 0. Measured 2026-08-03, that answer had
    been correct-looking and wrong for 25 days over 30 undeliverable rows.

    ==================  =========================================  ===============
    verdict             means                                      at the CLI
    ==================  =========================================  ===============
    ``PASS``            every pending row reached the provider     exits 0
    ``FAIL``            a provider rejected a row                  exits non-zero
    ``COULD_NOT_CHECK`` rows remain pending; nothing sent them     exits non-zero
    ``NOT_APPLICABLE``  there was nothing to drain                 exits 0
    ==================  =========================================  ===============

    NOT A SECOND VOCABULARY. These are the four names #1719/C013 gave the
    enforcing transition gate, for the same distinction one layer down: there a
    check that could not observe had only ``True`` available, here a drain that
    could not deliver had only exit 0. Core cannot import that module (it lives
    in ``atdd.coach``, and this layer is foundational), so the alignment is by
    name and is asserted by C015-UNIT-001 rather than left to this paragraph.

    ``COULD_NOT_CHECK`` is deliberately NOT ``FAIL``. Nothing was rejected and
    nothing is broken — the rows are intact and the remedy is to register a
    provider, not to debug one. Both refuse, because a drain that reports success
    over a queue it did not move is the defect; reporting them apart is what lets
    an operator tell "your provider is erroring" from "you have no provider".
    """

    PASS = "pass"
    FAIL = "fail"
    COULD_NOT_CHECK = "could_not_check"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class PushResult:
    pending: int
    pushed: int
    failed: int
    skipped_no_provider: int
    errors: List[str] = field(default_factory=list)
    #: Provider names the outbox holds rows for and the registry does not know.
    #: Sorted and de-duplicated so the refusal is attributable without re-querying.
    unregistered_providers: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> OutboxVerdict:
        """What this run can honestly claim about the queue it was given.

        Derived from what the run moved rather than from why it did not, so a
        row left behind for a reason nobody has thought of yet still refuses.
        """
        if self.pending == 0:
            return OutboxVerdict.NOT_APPLICABLE
        if self.failed:
            return OutboxVerdict.FAIL
        if self.pushed == self.pending:
            return OutboxVerdict.PASS
        return OutboxVerdict.COULD_NOT_CHECK

    @property
    def drained(self) -> bool:
        """True only when the queue is now empty for a reason this run produced."""
        return self.verdict in (OutboxVerdict.PASS, OutboxVerdict.NOT_APPLICABLE)


@dataclass
class IngestResult:
    providers: int
    ingested: int             # providers whose ingest() ran
    skipped_no_ingest: int    # push-only providers (no ingest method)
    errors: List[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    pending: int
    applied: int
    skipped: int
    notes: List[str] = field(default_factory=list)


def push_outbox(
    store: StateStore,
    providers: Mapping[str, SyncProvider],
    *,
    dry_run: bool = False,
) -> PushResult:
    """Drain the outbox, dispatching each message to its registered provider.

    A message whose ``provider`` has no registered provider is left **pending**
    (counted as ``skipped_no_provider``) — core never assumes a provider exists.
    A provider error also leaves its message pending (isolated per message).

    The result carries a :class:`OutboxVerdict` (#1711/C015): counts alone could
    not distinguish a drained queue from one nothing was able to move, and the
    single caller read only ``failed``. Resolving the provider happens even under
    ``dry_run`` — it is a registry lookup with no side effect, and reporting
    "nothing here is deliverable" is the whole value of a dry run.
    """
    pending = store.sync.pending_outbox()
    pushed = failed = skipped = 0
    errors: List[str] = []
    unregistered: set = set()
    for msg in pending:
        provider = providers.get(msg.provider)
        if provider is None:
            skipped += 1
            unregistered.add(msg.provider)
            continue
        if dry_run:
            continue
        try:
            outcome = provider.push(msg.operation, msg.payload)
            if outcome is not None and outcome.records_ref:
                store.external_refs.link(  # noqa: N+1 — one ref per queued message
                    outcome.object_uid, msg.provider, outcome.ref_kind, outcome.ref_value,
                    data=outcome.ref_data,
                )
            store.sync.mark_sent(msg.id)  # noqa: N+1 — one provider op per queued message
            pushed += 1
        except Exception as exc:  # noqa: BLE001 — per-message isolation; one failure must not abort the drain
            failed += 1
            errors.append(f"outbox#{msg.id} {msg.provider}/{msg.operation}: {exc}")
            _log.warning(
                "outbox push failed",
                extra={"outbox_id": msg.id, "provider": msg.provider,
                    "operation": msg.operation, "error": str(exc)},
            )
    return PushResult(
        pending=len(pending), pushed=pushed, failed=failed,
        skipped_no_provider=skipped, errors=errors,
        unregistered_providers=sorted(unregistered),
    )


def ingest_inbox(store: StateStore, providers: Mapping[str, SyncProvider]) -> IngestResult:
    """Ask each provider to fill the inbox from its remote (provider-specific poll).

    Core stays agnostic: it only invokes an optional ``ingest(store)`` hook — the
    provider decides what remote to poll and enqueues canonical events via
    ``store.sync.enqueue_inbox``. A provider without ``ingest`` is push-only and
    skipped. One provider's failure is isolated (logged, counted) so a single bad
    remote never aborts the others. Call :func:`apply_inbox` afterwards to drain.
    """
    ingested = skipped = 0
    errors: List[str] = []
    for name, provider in providers.items():
        ingest = getattr(provider, "ingest", None)
        if not callable(ingest):
            skipped += 1
            continue
        try:
            ingest(store)  # noqa: N+1 — one poll per registered provider
            ingested += 1
        except Exception as exc:  # noqa: BLE001 — per-provider isolation
            errors.append(f"ingest {name}: {exc}")
            _log.warning(
                "provider ingest failed",
                extra={"provider": name, "error": str(exc)},
            )
    return IngestResult(
        providers=len(providers), ingested=ingested,
        skipped_no_ingest=skipped, errors=errors,
    )


def apply_inbox(store: StateStore, *, dry_run: bool = False) -> ApplyResult:
    """Drain the inbox, applying canonical events to local state (provider-agnostic)."""
    pending = store.sync.pending_inbox()
    applied = skipped = 0
    notes: List[str] = []
    for msg in pending:
        kind = msg.payload.get("kind")
        try:
            handled = _apply_event(store, msg.provider, msg.payload)
        except Exception as exc:  # noqa: BLE001 — per-message isolation
            skipped += 1
            notes.append(f"inbox#{msg.id} {kind}: {exc}")
            continue
        if handled:
            applied += 1
        else:
            skipped += 1
            notes.append(f"inbox#{msg.id}: {kind} not applicable (no local ref?)")
        if not dry_run:
            store.sync.mark_processed(msg.id)  # noqa: N+1 — one event per queued message
    return ApplyResult(pending=len(pending), applied=applied, skipped=skipped, notes=notes)


def _apply_event(store: StateStore, provider: str, payload: Dict[str, Any]) -> bool:
    """Apply one canonical inbox event. Returns True if local state changed."""
    kind = payload.get("kind")
    if kind == EVENT_EXTERNAL_STATE:
        ref = store.external_refs.resolve(provider, payload["ref_kind"], str(payload["ref_value"]))
        if ref is None:
            return False
        store.objects.set_state(ref.object_uid, payload.get("state"))
        return True
    if kind == EVENT_EXTERNAL_IMPORTED:
        uid = payload.get("uid") or f"{provider}-{payload['ref_kind']}-{payload['ref_value']}"
        store.objects.upsert(
            uid, payload.get("object_kind", "work_item"),
            state=payload.get("state"), data=payload.get("data") or {},
        )
        store.external_refs.link(
            uid, provider, payload["ref_kind"], str(payload["ref_value"]),
            data={"source": "inbox-import"},
        )
        return True
    return False

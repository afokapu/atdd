"""Surface unanswered escalations for ``atdd coach status`` (WMBT L008).

An escalated decision is written to the daemon's ``escalations.jsonl`` with no
auto-reply (by design, C004/C007). Without surfacing, the operator is never told
there is something to answer and the worker stalls forever. This pure read joins
the escalation records (request_id) with the pending feed items (which carry the
prompt/options) and returns the UNANSWERED escalations — an escalation is
answered (and therefore omitted) once its request_id is no longer pending in the
Feed.

Skeleton: body lands in GREEN.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Tuple

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    FeedItem,
)


@dataclass(frozen=True)
class UnansweredEscalation:
    """One unanswered escalation, enriched with its prompt/options for display."""

    request_id: str
    prompt: Optional[str]
    options: Tuple[str, ...]


def list_unanswered_escalations(
    escalations: Iterable[Mapping[str, Any]],
    pending_items: Iterable[FeedItem],
) -> List[UnansweredEscalation]:
    """Return the still-unanswered escalations, in ledger order.

    ``escalations`` are the records read from ``escalations.jsonl`` (each carrying
    a ``request_id``). ``pending_items`` are the Feed items still pending. An
    escalation whose request_id is still pending is UNANSWERED and is returned
    (enriched with the pending item's prompt/options); one whose request_id is no
    longer pending has been answered/resolved and is OMITTED.
    """
    raise NotImplementedError("wmbt:mediate-worker-decisions:L008")

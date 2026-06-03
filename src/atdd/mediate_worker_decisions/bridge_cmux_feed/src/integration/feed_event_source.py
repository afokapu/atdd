"""FeedSource adapter: read pending decisions from the cmux Feed (WMBT L002).

Shells out via ``commons.cmux_cli.run_cmux`` to ``cmux rpc feed.list '{}'``,
parses the JSON, and maps each pending entry to a frozen ``FeedItem``. Only
pending items are returned (already-resolved ones are skipped).
"""
from __future__ import annotations

import json
from typing import List, Optional

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    EXIT_PLAN,
    PERMISSION,
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux, strip_ansi

_PENDING = "pending"
# ``feed.list`` is global and also carries already-executed tool-use telemetry
# (kind "toolUse", status "telemetry"); a *blocked decision* is one of these.
_DECISION_KINDS = (QUESTION, PERMISSION, EXIT_PLAN)


class CmuxFeedSource:
    def list_pending(self) -> List[FeedItem]:
        raw = strip_ansi(run_cmux("rpc", "feed.list", "{}")).strip()
        if not raw:
            return []
        payload = json.loads(raw)
        entries = payload.get("items", payload) if isinstance(payload, dict) else payload
        items: List[FeedItem] = []
        for entry in entries or []:
            if entry.get("kind") not in _DECISION_KINDS:
                continue  # skip toolUse / telemetry, keep only blocked decisions
            if entry.get("status") not in (None, _PENDING):
                continue
            items.append(_to_feed_item(entry))
        return items


def _to_feed_item(entry: dict) -> FeedItem:
    options = tuple(
        {
            "id": str(o.get("id", "")),
            "label": str(o.get("label", "")),
            "description": str(o.get("description", "")),
        }
        for o in (entry.get("question_options") or [])
    )
    return FeedItem(
        id=str(entry.get("id", "")),
        request_id=str(entry.get("request_id", "")),
        kind=str(entry.get("kind", "")),
        question_prompt=entry.get("question_prompt"),
        question_options=options,
        tool_name=entry.get("tool_name"),
        tool_input=_as_text(entry.get("tool_input")),
    )


def _as_text(tool_input) -> Optional[str]:
    """cmux may send tool_input as a string or a structured object; the safety
    gate matches on text, so normalize non-strings to JSON (preserving the
    command verbatim for danger-pattern matching)."""
    if tool_input is None or isinstance(tool_input, str):
        return tool_input
    return json.dumps(tool_input, ensure_ascii=False)

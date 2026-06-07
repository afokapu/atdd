"""FeedSource adapter: read pending decisions from the cmux Feed (WMBT L002).

Shells out via ``commons.cmux_cli.run_cmux`` to ``cmux rpc feed.list '{}'``,
parses the JSON, and maps each pending entry to a frozen ``FeedItem``. Only
pending items are returned (already-resolved ones are skipped).

When constructed with a ``workspace_id`` the source is SCOPED (WMBT D003): cmux
``feed.list`` is global and ignores any filter param (verified live — the item
count is identical with and without one), so a per-workspace daemon must map each
global item to a workspace and keep only its own. The workspace identity (its
claude session/workstream + worktree cwd) is read from ``cmux rpc surface.list``:
``resume_binding.checkpoint_id`` is the session uuid that an item's
``workstream_id`` (``claude-<uuid>``) is built from, and
``requested_working_directory`` is the cwd. cmux specifics stay here; the
membership predicate is the pure ``WorkspaceScope``. Without a ``workspace_id``
the source returns the global set (back-compat).
"""
from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    EXIT_PLAN,
    PERMISSION,
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.workspace_scope import (
    WorkspaceScope,
)
from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux, strip_ansi

_PENDING = "pending"
# ``feed.list`` is global and also carries already-executed tool-use telemetry
# (kind "toolUse", status "telemetry"); a *blocked decision* is one of these.
_DECISION_KINDS = (QUESTION, PERMISSION, EXIT_PLAN)

_log = logging.getLogger("atdd.mediate_worker_decisions.feed_source")


class CmuxFeedSource:
    def __init__(
        self,
        *,
        workspace_id: Optional[str] = None,
        runner: Callable[..., str] = run_cmux,
    ) -> None:
        """``workspace_id`` scopes the read to one workspace (WMBT D003); None
        keeps the global behaviour. ``runner`` is the cmux CLI seam (injectable
        for hermetic tests)."""
        self._ws = workspace_id
        self._run = runner

    def list_pending(self) -> List[FeedItem]:
        raw = strip_ansi(self._run("rpc", "feed.list", "{}")).strip()
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
        if self._ws is None:
            return items  # unscoped: the global pending set (back-compat)
        return self._resolve_scope().filter(items)

    def _resolve_scope(self) -> WorkspaceScope:
        """Resolve the configured workspace's identity from ``surface.list``.

        Collects, for every surface in the workspace, the agent's workstream id
        (``<kind>-<checkpoint_id>``, matching the Feed item's ``workstream_id``)
        and the worktree cwd. A garbled/empty tree degrades to an empty scope
        (filters everything out) rather than silently leaking the global set —
        logged so the miss is visible.
        """
        params = json.dumps({"workspace": self._ws})
        raw = strip_ansi(self._run("rpc", "surface.list", params)).strip()
        workstream_ids: set = set()
        cwds: set = set()
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError as exc:
            _log.warning(
                "could not parse surface.list; scoping to an empty set",
                extra={"workspace_id": self._ws, "error": repr(exc)},
            )
            return WorkspaceScope(frozenset(), frozenset())
        surfaces = (
            payload.get("surfaces", payload) if isinstance(payload, dict) else payload
        )
        for surface in surfaces or []:
            cwd = surface.get("requested_working_directory")
            binding = surface.get("resume_binding") or {}
            checkpoint = binding.get("checkpoint_id")
            kind = binding.get("kind")
            binding_cwd = binding.get("cwd")
            if checkpoint:
                # cmux builds the Feed workstream_id as ``<kind>-<checkpoint_id>``
                # (e.g. ``claude-<session-uuid>``); fall back to the bare id when
                # the kind is absent.
                workstream_ids.add(f"{kind}-{checkpoint}" if kind else str(checkpoint))
            if cwd:
                cwds.add(cwd)
            if binding_cwd:
                cwds.add(binding_cwd)
        return WorkspaceScope(frozenset(workstream_ids), frozenset(cwds))


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
        # the FULL multi-question payload, so the mapper preserves every
        # question as a block instead of flattening to the mirror (WMBT L003)
        questions=tuple(_normalize_question(q) for q in (entry.get("questions") or [])),
        # provenance used for per-workspace scoping (WMBT D003)
        workstream_id=entry.get("workstream_id"),
        cwd=entry.get("cwd"),
    )


def _normalize_question(question: dict) -> dict:
    """Normalize one cmux ``questions[]`` entry to the mapper's expected shape.

    cmux may send ``multi_select`` as ``multiSelect``; options carry id/label.
    The optional ``kind`` is passed through so an agent can mark a question as a
    confirm/free_text block explicitly.
    """
    return {
        "id": str(question.get("id", "")),
        "header": question.get("header"),
        "prompt": str(question.get("prompt", "")),
        "multi_select": bool(
            question.get("multi_select", question.get("multiSelect", False))
        ),
        "kind": question.get("kind"),
        "options": [
            {"id": str(o.get("id", "")), "label": str(o.get("label", ""))}
            for o in (question.get("options") or [])
        ],
    }


def _as_text(tool_input) -> Optional[str]:
    """cmux may send tool_input as a string or a structured object; the safety
    gate matches on text, so normalize non-strings to JSON (preserving the
    command verbatim for danger-pattern matching)."""
    if tool_input is None or isinstance(tool_input, str):
        return tool_input
    return json.dumps(tool_input, ensure_ascii=False)

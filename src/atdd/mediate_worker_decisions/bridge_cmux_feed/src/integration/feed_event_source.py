"""FeedSource adapter: read pending decisions from the cmux Feed (WMBT L002).

Shells out via ``commons.cmux_cli.run_cmux`` to ``cmux rpc feed.list '{}'``,
parses the JSON, and maps each pending entry to a frozen ``FeedItem``. Only
pending items are returned (already-resolved ones are skipped).

When constructed with a ``workspace_id`` the source is SCOPED (WMBT L005): cmux
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
import os
import subprocess
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


def _git_worktrees(cwd: str) -> List[str]:
    """Return the worktree directories of the git repo containing ``cwd``.

    A real worker is launched at the surface's launch cwd (a repo root) and then
    ``cd``s into a flat-sibling git worktree where it runs claude (WMBT L007). The
    surface only ever reports the launch cwd, so to match the worktree the worker
    actually cd'd into we resolve the repo's worktrees via ``git worktree list``
    (the launch cwd's own worktree is included). Returns ``[]`` when ``cwd`` is not
    a git repo, git is unavailable, or the call errors — the caller degrades
    gracefully (it never raises through a poll)."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    paths: List[str] = []
    for line in out.stdout.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):].strip()
            if path:
                paths.append(path)
    return paths


class CmuxFeedSource:
    def __init__(
        self,
        *,
        workspace_id: Optional[str] = None,
        runner: Callable[..., str] = run_cmux,
        worktrees: Callable[[str], List[str]] = _git_worktrees,
    ) -> None:
        """``workspace_id`` scopes the read to one workspace (WMBT L005); None
        keeps the global behaviour. ``runner`` is the cmux CLI seam and
        ``worktrees`` resolves a launch cwd to its git worktrees (WMBT L007) — both
        injectable for hermetic tests."""
        self._ws = workspace_id
        self._run = runner
        self._worktrees = worktrees

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

        ``cmux rpc surface.list`` with ``{"workspace_id": <ws>}`` returns ONLY
        that workspace's surfaces (it accepts the ``workspace:N`` ref under that
        key — verified live; the bare ``workspace`` key is ignored and leaks the
        caller's surfaces). For each surface we collect the agent's workstream id
        (``<kind>-<checkpoint_id>`` from ``resume_binding``, matching the Feed
        item's ``workstream_id`` e.g. ``claude-<session-uuid>``) and the cwd, both
        symlink-resolved (the Feed reports the realpath — ``/private/tmp/x`` vs a
        surface's ``/tmp/x``).

        Worktree-aware (WMBT L007): the surface only ever reports the LAUNCH cwd,
        but a real worker ``cd``s from there into a flat-sibling git worktree and
        runs claude under a NEW session — so its Feed item carries the worktree cwd
        and a workstream that is NOT the surface's resume checkpoint. We therefore
        also add the launch cwd's git worktrees to the cwd set so the worktree the
        worker cd'd into still matches.

        Never silently empty-scope (WMBT L007): if ``surface.list`` is garbled or
        yields NO usable identity for a workspace we were explicitly told to watch,
        we degrade to a LOUD permissive scope (owns everything) rather than an empty
        scope that silently swallows the watched workspace's decisions — a
        watched-but-empty scope is a bug, not a no-op.
        """
        params = json.dumps({"workspace_id": self._ws})
        raw = strip_ansi(self._run("rpc", "surface.list", params)).strip()
        workstream_ids: set = set()
        cwds: set = set()
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError as exc:
            _log.warning(
                "could not parse surface.list for a watched workspace; degrading "
                "to a permissive scope so its decisions are not silently swallowed",
                extra={"workspace_id": self._ws, "error": repr(exc)},
            )
            return WorkspaceScope(frozenset(), frozenset(), permissive=True)
        surfaces = (
            payload.get("surfaces", payload) if isinstance(payload, dict) else payload
        )
        for surface in surfaces or []:
            binding = surface.get("resume_binding") or {}
            checkpoint = binding.get("checkpoint_id")
            kind = binding.get("kind")
            if checkpoint:
                # cmux builds the Feed workstream_id as ``<kind>-<checkpoint_id>``
                # (e.g. ``claude-<session-uuid>``); fall back to the bare id when
                # the kind is absent.
                workstream_ids.add(f"{kind}-{checkpoint}" if kind else str(checkpoint))
            for cwd in (
                surface.get("requested_working_directory"),
                binding.get("cwd"),
            ):
                if cwd:
                    self._add_cwd_and_worktrees(cwd, cwds)
        if not workstream_ids and not cwds:
            _log.warning(
                "surface.list yielded no usable identity for a watched workspace; "
                "degrading to a permissive scope rather than silently empty-scoping "
                "its decisions",
                extra={"workspace_id": self._ws},
            )
            return WorkspaceScope(frozenset(), frozenset(), permissive=True)
        return WorkspaceScope(frozenset(workstream_ids), frozenset(cwds))

    def _add_cwd_and_worktrees(self, cwd: str, cwds: set) -> None:
        """Add a launch cwd, its realpath, and the cwd's git worktrees (+realpaths)
        to the scope's cwd set — so a worker that cd'd from the launch cwd into a
        flat-sibling worktree is matched (WMBT L007). The Feed reports realpaths, so
        every entry is stored both raw and symlink-resolved."""
        cwds.add(cwd)
        cwds.add(os.path.realpath(cwd))
        for worktree in self._worktrees(cwd):
            cwds.add(worktree)
            cwds.add(os.path.realpath(worktree))


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
        # provenance used for per-workspace scoping (WMBT L005)
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

"""WorkerAdvance adapter: prove a reply advanced the worker, send-key if not.

A ``feed.*.reply`` resolving the Feed item is NOT proof the worker proceeded: a
cmux-native worker can lose the race against its native interactive TUI menu and
stay parked while the item is marked non-pending (verified live, #986 — the
``expired`` case carries no ``decision``). ``CmuxWorkerAdvance`` reads the real
oracle off ``cmux rpc feed.list`` — *advanced* iff the item reaches
``status == "resolved"`` with a populated ``decision`` (NOT merely "no longer
pending", which the false ``expired`` state also satisfies) — and ``nudge``
delivers the pre-highlighted selection via ``cmux send-key <ws> Enter`` so the
parked worker proceeds. cmux specifics live here, behind the application's
``WorkerAdvance`` port.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable, Optional, Tuple

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux, strip_ansi

_RESOLVED = "resolved"
_EXPIRED = "expired"

_log = logging.getLogger("atdd.mediate_worker_decisions.advance")


class CmuxWorkerAdvance:
    def __init__(
        self,
        *,
        workspace_id: str,
        runner: Callable[..., str] = run_cmux,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout_s: float = 4.0,
        interval_s: float = 0.5,
    ) -> None:
        self._ws = workspace_id
        self._run = runner
        self._sleep = sleeper
        self._clock = clock
        self._timeout = timeout_s
        self._interval = interval_s

    def confirm_advanced(self, item: FeedItem) -> bool:
        """Poll the Feed until the item is provably consumed by the worker.

        Advanced iff the item reaches ``status == "resolved"`` with a populated
        ``decision``. ``status == "expired"`` (delivered but the worker never
        consumed the reply) returns False immediately — it is terminal, polling
        longer cannot turn it into an advance. A still-``pending`` / not-yet-seen
        item is polled up to ``timeout_s``; on timeout it reports not-advanced.
        """
        deadline = self._clock() + self._timeout
        while True:
            status, has_decision = self._read_item(item.request_id)
            if status == _RESOLVED and has_decision:
                return True
            if status == _EXPIRED:
                return False  # delivered but never consumed — terminal stuck
            if self._clock() >= deadline:
                return False
            self._sleep(self._interval)

    def nudge(self, item: FeedItem) -> None:
        """Deliver the pre-highlighted selection to the parked worker.

        The Feed reply already highlighted the correct option in the worker's
        native menu; a single Enter commits it. Targets the worker's terminal
        surface in this workspace (cmux defaults to the selected surface when one
        is not resolvable).
        """
        surface = self._resolve_surface()
        args = ["send-key", "--workspace", self._ws]
        if surface:
            args += ["--surface", surface]
        args.append("Enter")
        self._run(*args)

    def _read_item(self, request_id: str) -> Tuple[Optional[str], bool]:
        """Return ``(status, has_decision)`` for ``request_id`` from feed.list.

        ``(None, False)`` when the item is not present (treated as still-unknown
        by the caller, which keeps polling until timeout).
        """
        raw = strip_ansi(self._run("rpc", "feed.list", "{}")).strip()
        if not raw:
            return None, False
        payload = json.loads(raw)
        entries = payload.get("items", payload) if isinstance(payload, dict) else payload
        for entry in entries or []:
            if entry.get("request_id") == request_id:
                return entry.get("status"), bool(entry.get("decision"))
        return None, False

    def _resolve_surface(self) -> Optional[str]:
        """Resolve this workspace's selected terminal surface ref, if discoverable."""
        try:
            raw = strip_ansi(
                self._run("tree", "--workspace", self._ws, "--json")
            ).strip()
            tree = json.loads(raw) if raw else {}
        except (ValueError, OSError) as exc:
            # Degrade, don't fail: cmux send-key falls back to the workspace's
            # selected surface when no explicit surface is resolved. Log so a
            # missing/garbled tree is visible rather than silently swallowed.
            _log.warning(
                "could not resolve worker surface; send-key will target the "
                "selected surface",
                extra={"workspace_id": self._ws, "error": repr(exc)},
            )
            return None
        for window in tree.get("windows", []) or []:
            for workspace in window.get("workspaces", []) or []:
                if workspace.get("ref") not in (None, self._ws):
                    continue
                for pane in workspace.get("panes", []) or []:
                    selected = pane.get("selected_surface_ref")
                    if selected:
                        return selected
                    for surface in pane.get("surfaces", []) or []:
                        if surface.get("type") == "terminal":
                            return surface.get("ref")
        return None

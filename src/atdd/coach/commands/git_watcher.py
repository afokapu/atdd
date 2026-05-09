"""Git watcher (#J5) — observes new commits on each worktree's HEAD and
PR-state transitions; emits ``commit_observed``, ``pr_opened``, and
``pr_closed`` onto the shared ``CoachEventQueue``.

Commit detection uses ``git rev-parse HEAD`` polling against the last
seen value. PR-state detection is delegated to an injectable
``gh_pr_view`` callback so the test surface does not depend on live
GitHub API access.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from atdd.coach.commands.event_queue import CoachEventQueue


_TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.+)\s*$")


def parse_commit_trailers(message: str) -> dict[str, str]:
    """Parse RFC-2822-style trailers from the tail of a commit message.

    Trailers are the last contiguous block of ``Key: value`` lines at
    the end of the message. Recognized keys per spec §6.4 step 1
    (``Agent-Id``, ``Issue``, ``WMBT-Urn``, ``Phase``) are returned
    along with any other trailer keys present.
    """
    lines = message.rstrip("\n").splitlines()
    trailers: dict[str, str] = {}
    for line in reversed(lines):
        if not line.strip():
            if trailers:
                break
            continue
        m = _TRAILER_RE.match(line)
        if not m:
            break
        trailers[m.group(1)] = m.group(2).strip()
    return trailers


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class GitWatcher:
    """Observes new commits + PR-state transitions per worktree."""

    def __init__(
        self,
        worktree_paths: Iterable[Path],
        queue: CoachEventQueue,
        *,
        gh_pr_view: Optional[Callable[[Path], Optional[dict]]] = None,
    ) -> None:
        self.worktree_paths = [Path(p) for p in worktree_paths]
        self.queue = queue
        self._gh_pr_view = gh_pr_view
        self._last_sha: dict[Path, str] = {}
        self._last_pr_state: dict[Path, str] = {}

    def scan_once(self) -> int:
        emitted = 0
        for wt in self.worktree_paths:
            emitted += self._scan_commits(wt)
            emitted += self._scan_pr_state(wt)
        return emitted

    def _scan_commits(self, wt: Path) -> int:
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return 0
        prev = self._last_sha.get(wt)
        self._last_sha[wt] = sha
        if prev is None or sha == prev:
            return 0
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip()
            message = subprocess.run(
                ["git", "log", "-1", "--format=%B", sha],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout
            parents = subprocess.run(
                ["git", "log", "-1", "--format=%P", sha],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip().split()
            author = subprocess.run(
                ["git", "log", "-1", "--format=%an <%ae>", sha],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return 0
        event = {
            "event_type": "commit_observed",
            "agent_id": None,
            "timestamp": _now_iso(),
            "payload": {
                "sha": sha,
                "parent_sha": parents[0] if parents else None,
                "branch": branch,
                "worktree_path": str(wt),
                "author": author,
                "trailers": parse_commit_trailers(message),
            },
        }
        return 1 if self.queue.put(event) else 0

    def _scan_pr_state(self, wt: Path) -> int:
        if self._gh_pr_view is None:
            return 0
        try:
            state = self._gh_pr_view(wt)
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return 0
        if state is None:
            return 0
        terminal = state.get("state")
        prev = self._last_pr_state.get(wt)
        self._last_pr_state[wt] = terminal
        if prev is None and terminal == "OPEN":
            event = {
                "event_type": "pr_opened",
                "agent_id": None,
                "timestamp": _now_iso(),
                "payload": {
                    "pr_number": state.get("number"),
                    "sha": state.get("headRefOid"),
                    "base": state.get("baseRefName"),
                    "head": state.get("headRefName"),
                },
            }
            return 1 if self.queue.put(event) else 0
        if prev == "OPEN" and terminal != "OPEN":
            event = {
                "event_type": "pr_closed",
                "agent_id": None,
                "timestamp": _now_iso(),
                "payload": {
                    "pr_number": state.get("number"),
                    "sha": state.get("headRefOid"),
                    "terminal_state": terminal,
                },
            }
            return 1 if self.queue.put(event) else 0
        return 0

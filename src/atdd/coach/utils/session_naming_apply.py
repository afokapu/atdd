from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from atdd.coach.utils.multiplexer import MultiplexerError
from atdd.coach.utils.session_naming import target_grid_label

CANONICAL_SESSION_NAME_RULE_ID = "coach.session.canonical-session-name"
LAYOUT_CONFORMANCE_RULE_ID = "coach.session.layout-conformance"

_UUID_FILENAME_PATTERN = re.compile(r"^([a-f0-9-]{36})\.jsonl$")


def _claude_project_key(cwd: Path) -> str:
    """Compute Claude Code's project-key from a cwd path.

    Claude Code stores per-project session jsonl files under
    ~/.claude/projects/<key>/, where <key> is the absolute cwd path with
    each slash and dot replaced by a dash. e.g. /Users/foo/Github/atdd
    becomes -Users-foo-Github-atdd.
    """
    return str(cwd.resolve()).replace("/", "-").replace(".", "-")


def _find_latest_session_uuid(worktree_cwd: Path) -> Optional[str]:
    """Return the UUID of the most recently created Claude session jsonl in this project.

    Returns None if no session files exist for this project yet (typically the
    case if Claude is still starting up). Caller may want to retry with a delay.
    """
    home = Path(os.path.expanduser("~"))
    project_key = _claude_project_key(worktree_cwd)
    project_dir = home / ".claude" / "projects" / project_key
    if not project_dir.is_dir():
        return None
    candidates: list[tuple[float, str]] = []
    for entry in project_dir.iterdir():
        m = _UUID_FILENAME_PATTERN.match(entry.name)
        if not m:
            continue
        try:
            candidates.append((entry.stat().st_mtime, m.group(1)))
        except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def apply_canonical_name_and_layout(
    backend: Any,
    ref: str,
    canonical_name: str,
    surface_count: int,
    *,
    verify_after_send: bool = False,
    verify_timeout_s: float = 10.0,
    verify_poll_s: float = 0.25,
) -> None:
    """Apply canonical name via multiplexer-level rename (tab/window title only).

    M001 (#829): The Claude /rename slash-command injection is removed. Session
    naming is delegated to the cmux-native launch metadata (#978). Only the
    multiplexer-level backend.rename() call (which sets the tab/window title) is
    retained as a best-effort cosmetic. The ``verify_after_send`` parameter is
    preserved in the signature for call-site compat but is now a no-op since
    there is no /rename send to verify.
    """
    if not canonical_name:
        return
    try:
        rename = getattr(backend, "rename", None)
        if rename is not None:
            rename(ref, canonical_name)
        print(
            f"   rename target: {canonical_name} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})"
        )
    except MultiplexerError as exc:
        print(
            f"⚠️  rename failed for {ref}: {exc} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )

    # Real layout pass (#865): invoke an ACTUAL multiplexer layout primitive.
    # The prior bare ``print("layout target …")`` was log-theater — it claimed
    # enforcement while nothing was invoked, so every worker landed as a tab in
    # the focused (coach) pane. Delegate to the enforce-surface-conformance
    # feature, which positions the worker's OWN workspace right of the coach via a
    # real cmux op (never-collapse: the worker keeps its own daemon scope).
    # Best-effort: a layout failure (or a backend double lacking the layout
    # primitives) must not abort the spawn — the rename half already succeeded.
    try:
        from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.presentation.apply_conformance import (  # noqa: E501
            place_worker_surface_right,
        )

        result = place_worker_surface_right(backend, ref)
        print(
            f"   layout applied ({result.layout_invocations} op[s]): {ref} "
            f"positioned right of coach ({LAYOUT_CONFORMANCE_RULE_ID})"
        )
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-01
        print(
            f"⚠️  layout not applied for {ref}: {exc} "
            f"(target: {target_grid_label(surface_count)}) "
            f"({LAYOUT_CONFORMANCE_RULE_ID})",
            file=sys.stderr,
        )


def capture_session_uuid(
    backend: Any,
    ref: str,
    *,
    issue: int,
    agent_id: str,
    canonical_name: str,
    persona: str,
    phase: Optional[str],
    runtime_root: Path,
    delay: float = 1.5,
    worktree_cwd: Optional[Path] = None,
) -> Optional[str]:
    """Read the claude --resume UUID for the spawned session and persist it.

    Strategy (post-#691 fix): Claude Code does NOT print "Resume this session
    with: claude --resume <UUID>" on startup — that line only appears on /quit
    or `claude --resume` listing. The original screen-scrape approach can never
    match at spawn time. Instead, look up the most-recently-created jsonl file
    in ~/.claude/projects/<project-key>/ — Claude writes one file per session
    using the UUID as the filename.

    Best-effort: never raises. Returns the UUID string or None.
    """
    time.sleep(delay)
    if worktree_cwd is None:
        worktree_cwd = Path.cwd()
    uuid = _find_latest_session_uuid(worktree_cwd)
    if uuid is None:
        print(
            f"⚠️  no claude session jsonl found for {ref} under "
            f"~/.claude/projects/{_claude_project_key(worktree_cwd)}/; "
            f"session cannot be resumed without it "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
        return None

    session_dir = runtime_root / "coach" / str(issue)
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / f"{agent_id}.session.json"
    session_data = {
        "issue": issue,
        "agent_id": agent_id,
        "canonical_name": canonical_name,
        "cmux_surface": ref,
        "claude_resume_uuid": uuid,
        "spawned_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "persona": persona,
        "phase": phase,
    }
    session_file.write_text(json.dumps(session_data, indent=2))
    return uuid


__all__ = [
    "CANONICAL_SESSION_NAME_RULE_ID",
    "LAYOUT_CONFORMANCE_RULE_ID",
    "apply_canonical_name_and_layout",
    "capture_session_uuid",
]

"""
Worker checkpoint helper — `atdd checkpoint <N>` (issue #378).

Each orchestrated agent writes a per-issue state file to
``.atdd/worker-state-{issue}.json`` after every phase transition. The file is
gitignored: it captures ephemeral session state so a `/clear`+reload cycle can
be rebuilt by `atdd session-template <N> --from-checkpoint` without manual
re-briefing.

Schema: ``src/atdd/coach/schemas/worker-state.schema.json``.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

VALID_PHASES = (
    "INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE", "BLOCKED",
)
SUMMARY_MAX_CHARS = 500
DEFAULT_TTL_SECONDS = 86_400  # 24h advisory window


def checkpoint_path(issue: int, *, root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    return base / ".atdd" / f"worker-state-{issue}.json"


def _detect_last_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _detect_branch() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def write_worker_checkpoint(
    issue: int,
    phase: str,
    summary: str,
    open_files: list[str],
    *,
    branch: Optional[str] = None,
    last_commit: Optional[str] = None,
    root: Optional[Path] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Path:
    """Write a worker checkpoint and return the path written.

    The write is atomic: payload is staged to ``<path>.tmp`` and renamed in a
    single ``Path.replace`` call, so a crash mid-write cannot leave a corrupt
    JSON document at the canonical path.
    """
    if phase not in VALID_PHASES:
        raise ValueError(
            f"phase {phase!r} not in {VALID_PHASES}"
        )
    payload: dict = {
        "issue": int(issue),
        "phase": phase,
        "summary": (summary or "")[:SUMMARY_MAX_CHARS],
        "open_files": list(open_files or []),
        "checkpointed_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        "ttl_seconds": int(ttl_seconds),
    }
    resolved_branch = branch if branch is not None else _detect_branch()
    if resolved_branch:
        payload["branch"] = resolved_branch
    resolved_commit = last_commit if last_commit is not None else _detect_last_commit()
    if resolved_commit:
        payload["last_commit"] = resolved_commit

    target = checkpoint_path(issue, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(target)
    return target


def read_worker_checkpoint(
    issue: int, *, root: Optional[Path] = None
) -> Optional[dict]:
    """Return the parsed checkpoint dict, or None if no file exists."""
    target = checkpoint_path(issue, root=root)
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def run(
    issue: int,
    phase: str,
    summary: str,
    open_files: Optional[list[str]] = None,
    *,
    branch: Optional[str] = None,
    last_commit: Optional[str] = None,
    root: Optional[Path] = None,
) -> int:
    """CLI entry point: `atdd checkpoint <N> --phase X --summary "..." --open-files ...`."""
    try:
        path = write_worker_checkpoint(
            issue=issue,
            phase=phase,
            summary=summary,
            open_files=open_files or [],
            branch=branch,
            last_commit=last_commit,
            root=root,
        )
    except ValueError as exc:
        print(f"❌ {exc}")
        return 2
    print(f"✓ checkpoint written: {path}")
    return 0

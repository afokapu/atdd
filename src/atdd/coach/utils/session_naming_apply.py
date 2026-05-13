from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from atdd.coach.utils.multiplexer import MultiplexerError
from atdd.coach.utils.session_naming import target_grid_label

CANONICAL_SESSION_NAME_RULE_ID = "coach.orchestration.canonical-session-name"
LAYOUT_CONFORMANCE_RULE_ID = "coach.orchestration.layout-conformance"

_UUID_PATTERN = re.compile(r"claude --resume ([a-f0-9-]{36})")


def apply_canonical_name_and_layout(
    backend: Any,
    ref: str,
    canonical_name: str,
    surface_count: int,
) -> None:
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
    try:
        backend.send(ref, f"/rename {canonical_name}")
        backend.send_key(ref, "Enter")
    except AttributeError as exc:
        print(
            f"⚠️  /rename injection unavailable for {ref}: {exc} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
    except MultiplexerError as exc:
        print(
            f"⚠️  /rename injection failed for {ref}: {exc} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
    layout = target_grid_label(surface_count)
    print(
        f"   layout target ({surface_count} surface[s]): {layout} "
        f"({LAYOUT_CONFORMANCE_RULE_ID})"
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
) -> Optional[str]:
    """Read the claude --resume UUID from the surface after spawn and persist it.

    Best-effort: never raises. Returns the UUID string or None.
    """
    time.sleep(delay)
    try:
        screen = backend.read_screen(ref, lines=30)
    except Exception as exc:  # noqa: BLE001 — best-effort; any backend failure is non-fatal
        print(
            f"⚠️  read_screen failed for {ref}: {exc} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
        return None

    m = _UUID_PATTERN.search(screen)
    if not m:
        print(
            f"⚠️  claude --resume UUID not found in screen for {ref}; "
            f"session cannot be resumed without it "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
        return None

    uuid = m.group(1)
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

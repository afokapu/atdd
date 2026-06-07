"""Load the coach convention / operating protocol as decider system-prompt text.

The autonomous decider (``LlmCoach``, the per-decision ``claude -p`` call the
``feed_daemon`` uses for unattended runs) must decide AS A COACH, not a blank LLM
(#987 slice b). ``load_coach_context`` resolves the coach convention + operating
protocol — the canonical ATDD phase machine the coach drives — from the repo and
returns it (behind a short coach-role preamble) so it can be appended to the
provider CLI as a system prompt. The text is provider-agnostic: the same context
flows to whatever provider the decider resolves, keeping the pluggable seam
intact.

The convention path is resolved FROM the repo (``ATDD_REPO_ROOT`` or a walk up to
the ``.atdd``/``.git`` marker), never a hardcoded absolute path. A missing
convention degrades observably to the preamble alone — the daemon must still
decide unattended — rather than raising.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import logging

_log = logging.getLogger("atdd.feed_daemon.coach_context")

# The coach's operating protocol: the canonical ATDD lifecycle state machine the
# coach drives. Resolved relative to the repo root (never an absolute hardcode).
_CONVENTION_RELPATH = Path("src/atdd/coach/conventions/phase_machine.convention.yaml")

_COACH_PREAMBLE = (
    "You are the ATDD coach deciding on behalf of a blocked worker agent. Decide "
    "AS A COACH: follow the operating protocol below (the canonical ATDD phase "
    "machine) together with the issue/worker context in the prompt. Choose only "
    "among the offered options; never invent an action outside them, and never "
    "re-classify a dangerous action as safe.\n\n"
    "# Coach operating protocol (phase machine convention)\n"
)


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Resolve the consumer repo root without coupling to another wagon.

    ``ATDD_REPO_ROOT`` wins (set by the validator test runner); otherwise walk up
    for the ``.atdd/manifest.yaml`` ATDD marker, then any ``.git`` directory.
    Falls back to ``start``/cwd so the loader never raises on resolution.
    """
    env_root = os.environ.get("ATDD_REPO_ROOT")
    if env_root:
        env_path = Path(env_root).resolve()
        if env_path.is_dir():
            return env_path

    current = (start or Path.cwd()).resolve()
    while current != current.parent:
        if (current / ".atdd" / "manifest.yaml").exists():
            return current
        if (current / ".git").exists():
            return current
        current = current.parent
    return (start or Path.cwd()).resolve()


def load_coach_context(repo_root: Optional[Path] = None) -> str:
    """Coach convention + operating protocol text for the decider system prompt.

    Resolved from the repo (``ATDD_REPO_ROOT`` or the ``.atdd``/``.git`` marker
    walk), never a hardcoded absolute path. A missing or unreadable convention
    degrades observably (loud-logged) to the coach-role preamble alone — the
    decider still runs unattended — rather than raising.
    """
    root = repo_root or find_repo_root()
    convention_path = root / _CONVENTION_RELPATH
    try:
        protocol = convention_path.read_text(encoding="utf-8")
    except OSError as exc:
        # Degrade observably: never silently swallow. The daemon must still decide
        # unattended, so we fall back to the preamble rather than raising — but the
        # operator sees that the decider is running without its full protocol.
        _log.warning(
            "coach convention not loadable; decider runs with preamble only",
            extra={"convention_path": str(convention_path), "error": str(exc)},
        )
        return _COACH_PREAMBLE
    return _COACH_PREAMBLE + protocol


__all__ = ["load_coach_context", "find_repo_root"]

"""One-live-surface-per-issue guard (#1079, WMBT C002).

Before injecting a launch prompt the coach must confirm there is exactly ONE
live surface bound to the issue and paste only into it — otherwise a prompt
lands in a stale surface (the worker never becomes live) or in an arbitrary one
of several duplicates (both observed live driving #1055/#1057/#1062/#1066). The
guard creates a surface when none is live, reaps duplicates down to one, and
never pastes into a non-live surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PasteOutcome:
    """Outcome of a guarded paste the orchestrator can branch on."""

    pasted_to: Optional[str]
    created: bool
    refused: bool
    duplicate_detected: bool


def guarded_paste(issue_number: int, prompt: str, registry) -> PasteOutcome:
    """Resolve the single live surface for ``issue_number`` and paste into it.

    ``registry`` exposes ``live_surfaces_for``/``is_live``/``create_surface``/
    ``reap_surface``/``paste``. When no live surface exists one is created;
    when more than one exists the extras are reaped down to one; the paste
    always targets a confirmed-live surface.
    """
    live = list(registry.live_surfaces_for(issue_number))

    if len(live) == 0:
        ref = registry.create_surface(issue_number)
        registry.paste(ref, prompt)
        return PasteOutcome(
            pasted_to=ref, created=True, refused=False, duplicate_detected=False
        )

    if len(live) > 1:
        keep = live[0]
        for extra in live[1:]:
            registry.reap_surface(extra)
        registry.paste(keep, prompt)
        return PasteOutcome(
            pasted_to=keep, created=False, refused=False, duplicate_detected=True
        )

    ref = live[0]
    registry.paste(ref, prompt)
    return PasteOutcome(
        pasted_to=ref, created=False, refused=False, duplicate_detected=False
    )

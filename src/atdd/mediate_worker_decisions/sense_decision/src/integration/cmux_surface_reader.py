"""SurfaceReader adapter over the existing CmuxBackend.

ANSI stripping and buffer assembly live here (integration), so the pure parser
stays deterministic. The ``MultiplexerRef`` construction is confined to this
tier — the application/domain tiers only ever see a ``str`` surface id.
"""
from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


class CmuxSurfaceReader:
    def __init__(self, backend: object, lines: int = 120) -> None:
        # backend is an atdd.coach.utils.multiplexer.CmuxBackend (duck-typed here
        # to keep this adapter import-light and unit-substitutable).
        self._backend = backend
        self._lines = lines

    def read(self, surface_id: str) -> str:
        # CmuxBackend.capture_pane_text(surface_ref) returns the surface text;
        # the ref is the opaque surface id string (e.g. "surface:3").
        raw = self._backend.capture_pane_text(surface_id)
        return strip_ansi(raw)

"""CoachClient adapter over the existing CmuxBackend.

``present`` pastes the structured request onto the coach surface; ``read_reply``
captures the surface's current text for the use case to poll. ANSI stripping is
applied so the pure reply parser stays deterministic.
"""
from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class CmuxCoachClient:
    def __init__(self, backend: object, coach_surface_id: str) -> None:
        self._backend = backend
        self._surface = coach_surface_id

    def present(self, request_text: str) -> None:
        self._backend.paste_text(self._surface, "\n" + request_text + "\n")

    def read_reply(self) -> str:
        raw = self._backend.read_screen(self._surface, lines=80)
        return _ANSI.sub("", raw or "")


class SystemClock:
    """Real Clock port."""

    def now(self) -> float:
        import time

        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        import time

        time.sleep(seconds)

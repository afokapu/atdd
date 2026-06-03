"""CoachClient adapter over the cmux CLI.

``present`` types the structured request onto the coach surface; ``read_reply``
reads the surface's current text for the use case to poll. cmux surface refs are
workspace-scoped, so both ``send`` and ``read-screen`` take ``--workspace``
(see CmuxSurfaceReader for why a bare ``--surface`` fails). ANSI stripping keeps
the pure reply parser deterministic.
"""
from __future__ import annotations

import re
import subprocess

_ANSI_PATTERN = r"\x1b\[[0-9;?]*[ -/]*[@-~]"


def _strip_ansi(text: str) -> str:
    return re.sub(_ANSI_PATTERN, "", text or "")


class CmuxCoachClient:
    def __init__(
        self, workspace_id: str, coach_surface_id: str, cmux_bin: str = "cmux"
    ) -> None:
        self._workspace = workspace_id
        self._surface = coach_surface_id
        self._cmux = cmux_bin

    def _run(self, *args: str) -> "subprocess.CompletedProcess":
        return subprocess.run(
            [self._cmux, *args], capture_output=True, text=True, timeout=15
        )

    def present(self, request_text: str) -> None:
        # Type the request line-by-line so the coach sees a clean multi-line block.
        self._run("send", "--workspace", self._workspace, "--surface", self._surface,
                  "\n" + request_text + "\n")

    def read_reply(self) -> str:
        result = self._run(
            "read-screen", "--workspace", self._workspace,
            "--surface", self._surface, "--lines", "80",
        )
        return _strip_ansi(result.stdout or "")


class SystemClock:
    """Real Clock port."""

    def now(self) -> float:
        import time

        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        import time

        time.sleep(seconds)

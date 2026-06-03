"""SurfaceReader adapter over the cmux CLI.

ANSI stripping and buffer assembly live here (integration), so the pure parser
stays deterministic. cmux surface refs are workspace-scoped indexes, so
``capture-pane`` MUST be given ``--workspace`` (a bare ``--surface`` raises
"Surface is not a terminal" against current cmux — the reason CmuxBackend's
workspace-less capture returns empty here). The workspace ref is therefore part
of this adapter's construction; the application/domain tiers only ever see a
plain ``str`` surface id.
"""
from __future__ import annotations

import re
import subprocess

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


class CmuxSurfaceReader:
    def __init__(self, workspace_id: str, lines: int = 200, cmux_bin: str = "cmux") -> None:
        self._workspace = workspace_id
        self._lines = lines
        self._cmux = cmux_bin

    def read(self, surface_id: str) -> str:
        result = subprocess.run(
            [
                self._cmux, "capture-pane",
                "--workspace", self._workspace,
                "--surface", surface_id,
                "--lines", str(self._lines),
            ],
            capture_output=True, text=True, timeout=15,
        )
        return strip_ansi(result.stdout or "")

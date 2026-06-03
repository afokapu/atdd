"""SurfaceReader adapter over the cmux CLI.

ANSI stripping and buffer assembly live here (integration), so the pure parser
stays deterministic. cmux surface refs are workspace-scoped, so ``capture-pane``
is given ``--workspace`` (a bare ``--surface`` raises "Surface is not a
terminal"); the workspace ref is part of this adapter's construction.

.. deprecated:: 3.88.0
   Part of the screen-scrape path, superseded by the bridge-cmux-feed Feed
   integration (``atdd.mediate_worker_decisions.bridge_cmux_feed``). Removal: 3.90.0.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux, strip_ansi


class CmuxSurfaceReader:
    def __init__(self, workspace_id: str, lines: int = 200) -> None:
        import warnings

        warnings.warn(
            "CmuxSurfaceReader is deprecated since 3.88.0; the cmux Feed is the "
            "channel now — use atdd.mediate_worker_decisions.bridge_cmux_feed."
            "composition.build_feed_runner. Removal: 3.90.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._workspace = workspace_id
        self._lines = lines

    def read(self, surface_id: str) -> str:
        out = run_cmux(
            "capture-pane", "--workspace", self._workspace,
            "--surface", surface_id, "--lines", str(self._lines),
        )
        return strip_ansi(out)

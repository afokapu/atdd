"""CoachClient adapter over the cmux CLI.

``present`` types the structured request onto the coach surface; ``read_reply``
reads the surface's current text for the use case to poll. Both ``send`` and
``read-screen`` take ``--workspace`` (cmux surface refs are workspace-scoped).
ANSI stripping keeps the pure reply parser deterministic.

.. deprecated:: 3.88.0
   ``CmuxCoachClient`` is part of the screen-scrape path, superseded by the
   bridge-cmux-feed Feed integration
   (``atdd.mediate_worker_decisions.bridge_cmux_feed``). Removal: 3.90.0.
   (``SystemClock`` below is a generic clock port and is NOT deprecated.)
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux, strip_ansi


class CmuxCoachClient:
    def __init__(self, workspace_id: str, coach_surface_id: str) -> None:
        import warnings

        warnings.warn(
            "CmuxCoachClient is deprecated since 3.88.0; the cmux Feed is the "
            "channel now — use atdd.mediate_worker_decisions.bridge_cmux_feed."
            "composition.build_feed_runner. Removal: 3.90.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._workspace = workspace_id
        self._surface = coach_surface_id

    def present(self, request_text: str) -> None:
        run_cmux("send", "--workspace", self._workspace,
                 "--surface", self._surface, "\n" + request_text + "\n")

    def read_reply(self) -> str:
        out = run_cmux("read-screen", "--workspace", self._workspace,
                       "--surface", self._surface, "--lines", "80")
        return strip_ansi(out)


class SystemClock:
    """Real Clock port (monotonic time + real sleep)."""

    def now(self) -> float:
        import time

        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        import time

        time.sleep(seconds)

"""SignalStop + RealSleeper — graceful-shutdown plumbing (WMBT R002, DG-3).

SignalStop installs SIGINT/SIGTERM handlers that set a threading.Event the poll
loop observes between ticks. RealSleeper is the production pacing sleeper.

is_set() / set() are real (trivial Event ops) so the loop and tests can read the
flag; install() (which touches process-global signal state) lands in GREEN.
"""
from __future__ import annotations

import signal
import threading
import time


class SignalStop:
    def __init__(self) -> None:
        self._event = threading.Event()

    def install(self) -> "SignalStop":
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._on_signal)
        return self

    def _on_signal(self, signum, frame) -> None:  # noqa: ANN001 - signal handler
        self._event.set()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


class RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))

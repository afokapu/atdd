# URN: test:mediate-worker-decisions:feed-daemon:R002-INTEGRATION-001-sigterm-sets-stop
# Acceptance: acc:mediate-worker-decisions:R002-INTEGRATION-001-sigterm-sets-stop
# WMBT: wmbt:mediate-worker-decisions:R002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""R002-INTEGRATION-001 — an installed SIGTERM handler sets the stop event.

SignalStop.install() registers SIGINT/SIGTERM handlers; invoking the handler
sets the event the loop observes. Original handlers are restored after the test.
"""
from __future__ import annotations

import signal

from atdd.mediate_worker_decisions.feed_daemon.src.integration.signal_stop import (
    SignalStop,
)


def test_sigterm_handler_sets_stop():
    original_int = signal.getsignal(signal.SIGINT)
    original_term = signal.getsignal(signal.SIGTERM)
    try:
        stop = SignalStop().install()
        assert stop.is_set() is False

        stop._on_signal(signal.SIGTERM, None)  # simulate delivery

        assert stop.is_set() is True
    finally:
        signal.signal(signal.SIGINT, original_int)
        signal.signal(signal.SIGTERM, original_term)

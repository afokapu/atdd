"""Shared test doubles + fixtures for feed-daemon (hermetic).

The daemon reuses the real ``FeedRunnerUseCase`` (built via bridge-cmux-feed's
``build_feed_runner``) so the decide/escalate path under test is production code;
only the Feed source/transport/coach and the daemon's own collaborators (sink,
ledger, sleeper, stop, lock) are faked here.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.feed_daemon.composition import build_feed_daemon
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY,
    SOURCE_COACH,
    Verdict,
)

SAFE_QUESTION = FeedItem(
    id="f-safe",
    request_id="req-safe",
    kind="question",
    question_prompt="Pick an option",
    question_options=(
        {"id": "Alpha", "label": "Alpha", "description": ""},
        {"id": "Beta", "label": "Beta", "description": ""},
    ),
    tool_name=None,
    tool_input=None,
)

DANGER_PERMISSION = FeedItem(
    id="f-danger",
    request_id="req-danger",
    kind="permissionRequest",
    question_prompt=None,
    question_options=(),
    tool_name="Bash",
    tool_input="git push origin main",
)


class FakeFeedTransport:
    """Records ``feed.*.reply`` calls instead of shelling out to cmux."""

    def __init__(self):
        self.calls = []  # list[tuple[verb, params]]

    def reply(self, verb, params):
        self.calls.append((verb, params))


class CountingFeedSource:
    """Returns a fixed item list each poll, counting how many times polled."""

    def __init__(self, items):
        self._items = list(items)
        self.calls = 0

    def list_pending(self):
        self.calls += 1
        return list(self._items)


class FakeCoach:
    """A coach that auto-approves (never reached on the dangerous path)."""

    def __init__(self):
        self.calls = []

    def mediate(self, request):
        self.calls.append(request)
        return Verdict(
            verdict_id="v-auto",
            request_id=request.request_id,
            decided_at="t",
            disposition=AUTO_APPLY,
            source=SOURCE_COACH,
            selected_option_id="Alpha",
            reason="auto",
        )


class RecordingEscalationSink:
    def __init__(self):
        self.records = []

    def record(self, escalation):
        self.records.append(escalation)


class RecordingVerdictLedger:
    def __init__(self):
        self.records = []

    def record(self, verdict):
        self.records.append(verdict)


class FakeSleeper:
    def __init__(self):
        self.calls = []

    def sleep(self, seconds):
        self.calls.append(seconds)


class FlipStop:
    """is_set() yields each value in ``sequence`` in turn (last value sticks)."""

    def __init__(self, sequence):
        self._seq = list(sequence)
        self._i = 0

    def is_set(self):
        value = self._seq[min(self._i, len(self._seq) - 1)]
        self._i += 1
        return value


class NeverStop:
    def is_set(self):
        return False


class RecordingLock:
    def __init__(self, acquired=True):
        self._acquired = acquired
        self.acquires = 0
        self.releases = 0

    def acquire(self):
        self.acquires += 1
        return self._acquired

    def release(self):
        self.releases += 1


def make_daemon(
    *,
    items,
    transport=None,
    coach=None,
    escalation_sink=None,
    verdict_ledger=None,
    sleeper=None,
    stop=None,
    lock=None,
    answered=None,
    poll_interval_s=0.0,
    source=None,
):
    """Build a daemon wrapping a REAL runner over fake Feed collaborators."""
    transport = transport if transport is not None else FakeFeedTransport()
    coach = coach if coach is not None else FakeCoach()
    src = source if source is not None else CountingFeedSource(items)
    runner = build_feed_runner(source=src, reply=transport, coach=coach)
    daemon = build_feed_daemon(
        source=src,
        runner=runner,
        escalation_sink=escalation_sink or RecordingEscalationSink(),
        verdict_ledger=verdict_ledger or RecordingVerdictLedger(),
        sleeper=sleeper or FakeSleeper(),
        stop=stop or NeverStop(),
        lock=lock or RecordingLock(),
        answered=answered,
        poll_interval_s=poll_interval_s,
    )
    return daemon, src, transport, coach

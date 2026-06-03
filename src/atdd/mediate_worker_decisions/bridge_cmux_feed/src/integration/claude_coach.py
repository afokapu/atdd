"""Coach adapter over the LLM coach (``claude -p``), one-shot and decide-only.

Implements the feed ``Coach`` port (``mediate(request) -> Verdict``): render the
DecisionRequest into a prompt, ask ``claude -p`` to pick the best option, and
parse the answer into an AUTO_APPLY Verdict sourced from the coach.

Decide-only by design: the dangerous-action safety gate already runs *ahead* of
the coach in ``FeedRunnerUseCase`` (WMBT C003), so a dangerous tool use never
reaches this adapter. ``ClaudeCoach`` therefore only chooses among the offered
options; it does not re-classify safety.

Coach logic mirrors the bridge-cmux-feed live smoke's ``_ClaudeCoach`` (render
-> ``claude -p`` -> parse selection), promoted here as the production adapter so
the feed path no longer reuses the deprecated screen-scrape
``build_mediate_use_case_from_repo`` / ``CmuxCoachClient``.
"""
from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timezone
from typing import Callable

from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY,
    SOURCE_COACH,
    Verdict,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
)

_COACH_TIMEOUT = 90.0


def _default_id_factory() -> str:
    return str(uuid.uuid4())


def _default_ts_factory() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_claude_cli(prompt: str, *, timeout: float) -> str:
    """Run ``claude -p <prompt>`` one-shot and return its stdout."""
    return subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    ).stdout


class ClaudeCoach:
    """A real coach: renders the request and asks ``claude -p`` to pick an option.

    The ``claude_cli`` / id / ts factories are injectable so the adapter is
    unit-testable without shelling out (the hermetic tests use a fake coach, but
    a fake CLI keeps this adapter exercisable in isolation too).
    """

    def __init__(
        self,
        *,
        claude_cli: Callable[..., str] = _default_claude_cli,
        id_factory: Callable[[], str] = _default_id_factory,
        ts_factory: Callable[[], str] = _default_ts_factory,
        timeout: float = _COACH_TIMEOUT,
    ) -> None:
        self._claude = claude_cli
        self._id = id_factory
        self._ts = ts_factory
        self._timeout = timeout

    def mediate(self, request: DecisionRequest) -> Verdict:
        prompt = _render_decision_prompt(request)
        output = self._claude(prompt, timeout=self._timeout)
        label = _parse_selection(output, request)
        return Verdict(
            verdict_id=self._id(),
            request_id=request.request_id,
            decided_at=self._ts(),
            disposition=AUTO_APPLY,
            source=SOURCE_COACH,
            selected_option_id=label,
            reason="coach decided via claude -p",
        )


def _render_decision_prompt(request: DecisionRequest) -> str:
    lines = [request.prompt.question, "", "Options:"]
    lines += [f"- {o.label}" for o in request.prompt.options]
    lines += ["", "Reply with ONLY the exact label of the best option, nothing else."]
    return "\n".join(lines)


def _parse_selection(output: str, request: DecisionRequest) -> str:
    """Pick the option whose label appears in the coach's reply (else the first)."""
    low = (output or "").lower()
    for opt in request.prompt.options:
        if opt.label.lower() in low:
            return opt.label
    return request.prompt.options[0].label if request.prompt.options else ""

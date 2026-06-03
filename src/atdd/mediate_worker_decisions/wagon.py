"""Wagon composition root for mediate-worker-decisions.

Glues the three features through their internal artifacts (request -> verdict ->
record): sense-decision senses a request, mediate-decision turns it into a
verdict or an escalation, and apply-decision applies an auto_apply verdict to
the worker (or records the escalation). Features are wired here in code — the
``to: internal`` artifacts never become inter-wagon contracts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from atdd.mediate_worker_decisions.apply_decision.composition import (
    build_apply_use_case_from_repo,
)
from atdd.mediate_worker_decisions.mediate_decision.composition import (
    build_mediate_use_case_from_repo,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY,
    Verdict,
)
from atdd.mediate_worker_decisions.sense_decision.composition import (
    build_sense_use_case_from_repo,
)
from atdd.mediate_worker_decisions.sense_decision.src.application.sense_use_case import (
    SOURCE_NOTIFICATION,
)


class WorkerDecisionBridge:
    def __init__(self, sense, mediate, apply) -> None:
        self._sense = sense
        self._mediate = mediate
        self._apply = apply

    def run_notification(self, surface_id: str, notification_hash: Optional[str] = None):
        """Full chain for a cmux notification; returns the terminal outcome or None."""
        request = self._sense.sense(
            surface_id=surface_id,
            source=SOURCE_NOTIFICATION,
            notification_hash=notification_hash,
        )
        if request is None:
            return None
        return self.run_request(request)

    def run_request(self, request):
        """Mediate then (only for an auto_apply verdict) apply."""
        outcome = self._mediate.handle(request)
        if isinstance(outcome, Verdict) and outcome.disposition == AUTO_APPLY:
            return self._apply.apply(request, outcome)
        return outcome  # Escalation, or a human_required verdict — never auto-applied


def build_bridge(
    repo_root: Optional[Path] = None,
    coach_surface_id: str = "surface:1",
) -> WorkerDecisionBridge:  # pragma: no cover - exercised by live smoke
    root = Path(repo_root or Path.cwd())
    return WorkerDecisionBridge(
        sense=build_sense_use_case_from_repo(root),
        mediate=build_mediate_use_case_from_repo(root, coach_surface_id=coach_surface_id),
        apply=build_apply_use_case_from_repo(root),
    )

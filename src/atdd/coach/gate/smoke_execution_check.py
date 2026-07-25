"""SmokeExecutionGateCheck — SPIKE (#1602): evidence-gated SMOKE->REFACTOR.

**THIS IS A DE-RISKING SPIKE, NOT THE PRODUCTION PRIMITIVE.** Its only job is to
prove that a check satisfying the #1020 ``GateCheck`` Protocol, registered for
``SMOKE->REFACTOR``, blocks the transition when no smoke-execution attestation
exists — and that fail-closed is inherited free from ``decision.run_checks``.

What the spike deliberately does NOT do (the full build owns these):

* it does not WRITE the attestation — no pytest hook exists yet, so the fixture
  is hand-placed to simulate "smoke ran";
* it does not check ``commit_sha`` staleness, a ``duration_s`` floor, or
  infrastructure identity (proposal §2.2's non-negotiables);
* its ``rule_id`` names ``coach.lifecycle.no-green-to-refactor-without-smoke``
  but that node is still ``disposition: documentation-only`` and absent from
  ``.atdd/binding.lock.yaml``. Flipping the disposition + adding the lock entry
  is the full build's edit 5. Named here only so the spike and the full build
  agree on the identifier.

ATTESTATION PATH — ``.atdd/smoke-runs/<issue>.json``, deliberately NOT the
existing ``.atdd/smoke-evidence/<issue>.yaml``. That file is the #358
presentation-ratchet's operator-typed stamp, producible by hand with
``atdd validate coder --smoke-required`` without running a single test. Reading
it would re-import the exact bug class this gate exists to close, so the
execution attestation gets its own namespace.

FAIL-CLOSED: absent file, unreadable file, unparseable JSON, wrong shape, or an
attestation whose every entry is ``skipped``/``failed`` all return
``passed=False``. Anything that raises is converted to a FAIL one level up by
``decision.run_checks`` — this check never has to catch to be safe.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from atdd.coach.gate.decision import GateCheckResult, GateContext

logger = logging.getLogger(__name__)

GATE_ID = "smoke-execution"
RULE_ID = "coach.lifecycle.no-green-to-refactor-without-smoke"

#: Directory (worktree-relative) holding per-issue smoke-execution attestations.
SMOKE_RUNS_DIR = ".atdd/smoke-runs"


def attestation_relpath(issue_number: int) -> str:
    """Worktree-relative path of the smoke-execution attestation for an issue."""
    return f"{SMOKE_RUNS_DIR}/{issue_number}.json"


def _entries(payload: Any) -> Sequence[Any]:
    """Normalize an attestation payload to its list of run entries.

    Accepts either a bare list of entries or ``{"runs": [...]}``. Any other
    shape yields no entries, which the caller treats as "smoke did not run".
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        runs = payload.get("runs")
        if isinstance(runs, list):
            return runs
    return ()


def _has_passing_run(entries: Sequence[Any]) -> bool:
    """True iff at least one entry records a smoke test that actually passed.

    Requiring ``passed`` (not merely "an entry exists") is what makes an
    all-skipped attestation block — the #1076 class, where C010-SMOKE-001
    "passed" by skipping itself.
    """
    return any(
        isinstance(e, dict) and str(e.get("outcome", "")).lower() == "passed"
        for e in entries
    )


@dataclass(frozen=True)
class SmokeExecutionGateCheck:
    """Passes iff a smoke-execution attestation records a passing smoke run."""

    gate_id: str = GATE_ID
    rule_id: str = RULE_ID

    def run(self, ctx: GateContext) -> GateCheckResult:
        rel = attestation_relpath(ctx.issue_number)
        path: Path = ctx.worktree / rel
        produce = (
            "smoke must actually execute: run the SMOKE-phase suite for "
            f"#{ctx.issue_number}; the run itself writes {rel} "
            "(it is NOT an operator-typed stamp)"
        )

        if not path.exists():
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"no smoke-execution attestation for "
                f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()} "
                f"(expected {rel}) — smoke is not proven to have run; {produce}",
            )

        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            logger.warning(
                "smoke-execution attestation unreadable; failing closed",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "path": rel, "issue": ctx.issue_number, "error": str(exc)},
            )
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"smoke-execution attestation at {rel} is unreadable/unparseable "
                f"(fail-closed): {exc}; {produce}",
            )

        entries = _entries(payload)
        if not entries:
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"smoke-execution attestation at {rel} records no runs "
                f"(fail-closed); {produce}",
            )
        if not _has_passing_run(entries):
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"smoke-execution attestation at {rel} has {len(entries)} run(s) "
                f"but none with outcome 'passed' (skipped/failed smoke is not "
                f"executed smoke); {produce}",
            )

        return GateCheckResult(
            self.gate_id, self.rule_id, True,
            f"smoke-execution attestation present at {rel} with a passing run "
            f"for {ctx.from_phase.upper()}->{ctx.to_phase.upper()}",
        )

"""Reference subprocess-backed gate check (#1020 scope D).

``CommandGateCheck`` is the impure, pluggable check that runs a CLI command in
the issue's worktree and passes iff it exits 0. It is the integration-layer
sibling of the pure ``decision`` module and demonstrates the ``GateCheck``
contract end-to-end (a registered command becomes a blocking check).

It is NOT registered into ``GATE_REGISTRY`` by default — the shipped registry is
empty for migration safety. #958/#1017 (and operators) register concrete checks.

FAIL-CLOSED (WMBT E046): a missing tool (FileNotFoundError) or a timeout
(subprocess.TimeoutExpired) is a FAIL, never a silent pass. The exception path is
handled here AND, as a backstop, by ``run_checks`` — either way the verdict is
``passed=False``.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Sequence

from atdd.coach.gate.decision import GateCheckResult, GateContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandGateCheck:
    """A gate check that passes iff ``command`` exits 0 in the worktree."""

    gate_id: str
    rule_id: str
    command: Sequence[str]
    timeout: float = 30.0

    def run(self, ctx: GateContext) -> GateCheckResult:
        try:
            result = subprocess.run(
                list(self.command),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=ctx.worktree,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "gate check timed out; failing closed",
                extra={
                    "gate_id": self.gate_id,
                    "rule_id": self.rule_id,
                    "timeout": self.timeout,
                    "issue": ctx.issue_number,
                },
            )
            return GateCheckResult(
                gate_id=self.gate_id,
                rule_id=self.rule_id,
                passed=False,
                message=(
                    f"gate check {self.gate_id} timed out after {self.timeout}s "
                    f"(fail-closed): {' '.join(self.command)}"
                ),
            )
        except (FileNotFoundError, OSError) as exc:
            logger.warning(
                "gate check could not run; failing closed",
                extra={
                    "gate_id": self.gate_id,
                    "rule_id": self.rule_id,
                    "error": str(exc),
                    "issue": ctx.issue_number,
                },
            )
            return GateCheckResult(
                gate_id=self.gate_id,
                rule_id=self.rule_id,
                passed=False,
                message=(
                    f"gate check {self.gate_id} could not run (fail-closed): {exc}"
                ),
            )

        if result.returncode == 0:
            return GateCheckResult(
                gate_id=self.gate_id,
                rule_id=self.rule_id,
                passed=True,
                message=f"gate check {self.gate_id} passed",
            )
        detail = (result.stderr or result.stdout or "").strip()
        return GateCheckResult(
            gate_id=self.gate_id,
            rule_id=self.rule_id,
            passed=False,
            message=(
                f"gate check {self.gate_id} failed (exit {result.returncode}): {detail}"
            ),
        )

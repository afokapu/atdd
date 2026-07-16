# URN: component:enforce-conventions-ci:enforce-conventions-ci:ratchet:backend:domain
# Runtime: python
# Purpose: The enforcement ratchet — a per-rule violation-count baseline that holds
#          pre-existing debt FLAT so the enforce job can go blocking without reding
#          the first build, while any rule climbing above its baseline still fails.
"""The enforcement ratchet baseline (#1428 E003).

The problem this exists to solve: ``atdd enforce`` reports a real FAIL over this
repository today — 23 of its 51 enforced rules carry violations (dead code,
complexity, silent-swallow logging, …). Turning the CI job BLOCKING (E001) over
that state would red the build on commit one and the gate would be reverted
within the hour. Staying advisory forever is the other failure — a check nobody
is accountable to.

The ratchet is the third way, and it is a **debt register, not an exemption**:

  * record each failing rule's CURRENT violation count as its baseline;
  * a rule reporting **at or below** its baseline is held FLAT — its verdict is
    neutralized (``baselined``), so the aggregate passes and the blocking job is
    green over the known debt;
  * a rule reporting **above** its baseline still FAILS, naming the baseline, the
    current count, and the excess;
  * a rule with **no baseline entry** is held to a baseline of ZERO — a clean rule
    that starts failing fails, so new debt cannot be smuggled in under the register.

It can therefore only ever be TIGHTENED: paying debt down never breaks the build,
and no rule ever gets a free pass it has not already earned. A held-flat rule is
still NAMED in the report with its baselined count, so the debt stays visible
rather than being silently forgiven.

The verdict aggregation itself is NOT re-implemented here: this module rewrites
verdicts and hands them back to :class:`~atdd.enforce.runner.EnforceResult`, whose
``exit_code`` remains the single source of the process exit code (the behaviour
#1428 E002 pins).
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Mapping

import yaml

from atdd.enforce.runner import EnforceResult, RuleVerdict

_log = logging.getLogger(__name__)

#: Canonical location of the committed baseline, relative to the repo root.
RATCHET_PATH: str = ".atdd/enforce-ratchet.yaml"

#: Status carried by a failing rule whose count is at or below its baseline. It is
#: deliberately NOT ``pass`` (the debt is real and stays visible) and NOT ``fail``
#: (it must not gate the build) — ``RuleVerdict.failed`` is False for it, so
#: ``EnforceResult.exit_code`` is 0 when only baselined rules remain.
BASELINED: str = "baselined"


class RatchetError(Exception):
    """A malformed or unreadable ratchet baseline — a usage/wiring error (exit 2)."""


def load_baseline(path: Path) -> Dict[str, int]:
    """Read the committed baseline's ``rules:`` mapping (``rule_id -> count``).

    A MISSING file is an error, never an empty baseline: silently treating an
    absent register as "everything must be clean" would red the build, and
    silently treating it as "everything is forgiven" would be far worse. Say so.
    """
    if not path.is_file():
        raise RatchetError(
            f"ratchet baseline not found at {path} — record one with "
            f"`atdd enforce --record-ratchet {path}` before enforcing under a ratchet"
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RatchetError(f"malformed ratchet baseline {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RatchetError(f"malformed ratchet baseline {path}: expected a mapping")

    rules = data.get("rules") or {}
    if not isinstance(rules, dict):
        raise RatchetError(f"malformed ratchet baseline {path}: `rules` must be a mapping")

    baseline: Dict[str, int] = {}
    for rule_id, count in rules.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise RatchetError(
                f"malformed ratchet baseline {path}: rule {rule_id!r} has a "
                f"non-integer / negative count {count!r}"
            )
        baseline[str(rule_id)] = count
    return baseline


def record_baseline(result: EnforceResult, *, scope: List[str] | None = None) -> str:
    """Render the YAML baseline registering every rule that FAILS in *result*.

    Only failing rules are registered — a passing rule is held to zero implicitly,
    which is what keeps a clean rule from silently acquiring an allowance.
    """
    failing = sorted(
        (v for v in result.verdicts if v.failed),
        key=lambda v: v.rule_id,
    )
    lines = [
        "# Enforcement ratchet baseline (#1428 E003) — a DEBT REGISTER, not an exemption.",
        "#",
        "# Each entry records the violation count a rule carried when the enforce job was",
        "# made BLOCKING (#1428 E001). A rule at or below its count is held FLAT; a rule",
        "# ABOVE it FAILS; a rule absent from this register is held to ZERO.",
        "#",
        "# The ratchet may only ever be TIGHTENED. To pay debt down, fix violations and",
        "# re-record:  atdd enforce --paths <scope> --record-ratchet .atdd/enforce-ratchet.yaml",
        "# NEVER raise a count to make a red build green — that is what the gate is for.",
        "",
        "version: 1",
    ]
    if scope:
        lines.append("# The scan scope these counts were recorded over (CI uses the same).")
        lines.append("scope:")
        lines.extend(f"  - {s}" for s in scope)
    lines.append("")
    lines.append("rules:")
    if failing:
        width = max(len(v.rule_id) for v in failing)
        for v in failing:
            lines.append(f"  {v.rule_id + ':':<{width + 1}} {v.raw_violation_count}")
    else:
        lines.append("  {}  # no rule fails — the ratchet is fully paid down")
    return "\n".join(lines) + "\n"


def _ratchet_one(verdict: RuleVerdict, baseline: Mapping[str, int]) -> RuleVerdict:
    """Judge ONE failing verdict against its baseline: held flat, or a regression."""
    allowed = baseline.get(verdict.rule_id, 0)
    count = verdict.raw_violation_count
    if count <= allowed:
        return replace(
            verdict,
            status=BASELINED,
            detail=f"{count} violation(s) held flat at ratchet baseline {allowed}",
        )
    return replace(
        verdict,
        detail=(
            f"{count} violation(s) — ABOVE ratchet baseline {allowed} "
            f"(+{count - allowed}); a rule may only ever improve"
        ),
    )


def apply_ratchet(result: EnforceResult, baseline: Mapping[str, int]) -> EnforceResult:
    """Hold every failing rule at or below its baseline FLAT; fail the rest.

    Returns a NEW :class:`EnforceResult` — the runner's own verdicts are never
    mutated, so the un-ratcheted truth stays available to any other caller.
    """
    ratcheted = [
        _ratchet_one(v, baseline) if v.failed else v for v in result.verdicts
    ]
    return EnforceResult(verdicts=ratcheted, report=render(ratcheted, baseline))


def _verdict_lines(verdict: RuleVerdict) -> List[str]:
    """The report lines for one verdict (a preserved exemption stays silent — V4)."""
    if verdict.status == "exempt":
        return []
    lines = [
        f"[{verdict.status.upper()}] {verdict.rule_id} "
        f"[{verdict.workspace_id}] {verdict.detail}".rstrip()
    ]
    # Only a genuine regression lists its locations — dumping the baselined debt's
    # thousands of locations would bury the one line that matters.
    if verdict.failed:
        lines.extend(f"    {verdict.rule_id} @ {loc}" for loc in verdict.locations)
    return lines


def _summary_lines(
    failed: List[RuleVerdict], baselined: List[RuleVerdict], registered: int
) -> List[str]:
    """The trailing summary — the held-flat debt stays VISIBLE, never silent."""
    lines = [""]
    if baselined:
        held = sum(v.raw_violation_count for v in baselined)
        lines.append(
            f"[RATCHET] {len(baselined)} rule(s) / {held} violation(s) held flat at "
            f"baseline — known debt, may only be paid down (see {RATCHET_PATH})."
        )
    if failed:
        lines.append(
            f"[RATCHET] {len(failed)} rule(s) ABOVE baseline — this is a REGRESSION, "
            f"not pre-existing debt."
        )
    lines.append(
        f"enforce verdict (ratcheted): {'FAIL' if failed else 'PASS'} — "
        f"{len(failed)} rule(s) above baseline, {len(baselined)} held flat, "
        f"{registered} registered."
    )
    return lines


def render(verdicts: List[RuleVerdict], baseline: Mapping[str, int]) -> str:
    """Render the ratcheted report."""
    lines: List[str] = []
    for verdict in verdicts:
        lines.extend(_verdict_lines(verdict))
    lines.extend(
        _summary_lines(
            [v for v in verdicts if v.failed],
            [v for v in verdicts if v.status == BASELINED],
            len(baseline),
        )
    )
    return "\n".join(lines)

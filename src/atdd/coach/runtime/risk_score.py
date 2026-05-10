# URN: component:govern-lifecycle:enforcement-substrate:risk_score:backend:domain
# Runtime: python
# Purpose: Per-phase-exit risk score computation and schema-validated persistence (spec §6.8).

"""
Risk-score computer and writer (issue #521 / spec §6.8).

Computes the per-commit risk score from active violations and stale suppressions,
then validates against ``risk-score.schema.json`` before persisting to
``.atdd/runtime/validations/<sha>/risk-score.json``.

Consumers:
  - Coach COMPLETE handler (threshold routing per ``coach.risk_threshold_block``)
  - Judge (risk score is part of every ``atdd judge`` call's context, §6.9)
  - PR description renderer (embeds score + breakdown)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from atdd.coach.utils.risk_score import compute_risk_breakdown
from atdd.coach.validators._violation import Violation

try:
    from atdd.coach.utils.rule_binding import bind_rule
except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
    print("[risk_score] bind_rule import failed — dispositions will be empty", file=sys.stderr)
    bind_rule = None  # type: ignore[assignment]

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "risk-score.schema.json"


@dataclass(frozen=True)
class RiskScore:
    """Per-phase-exit risk-score document (spec §6.8).

    Attributes:
        sum: Total severity over all active violations.
        by_severity: Count of violations per severity level (keys "1".."5").
        by_archetype: Severity sum per archetype. Always includes ``repo``.
        by_disposition: Count per disposition (strict, suppress-and-clean, etc.).
        stale_suppressions: Count of stale suppression markers (not in sum).
        phase: Optional ATDD phase this score was emitted at.
        generated_at: ISO-8601 UTC timestamp.
        sha: Commit SHA the score is anchored on.
    """

    sum: int
    by_severity: Dict[str, int]
    by_archetype: Dict[str, int]
    by_disposition: Dict[str, int]
    stale_suppressions: int
    phase: Optional[str] = None
    generated_at: Optional[str] = None
    sha: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "sum": self.sum,
            "by_severity": dict(self.by_severity),
            "by_archetype": dict(self.by_archetype),
            "by_disposition": dict(self.by_disposition),
            "stale_suppressions": self.stale_suppressions,
        }
        if self.phase is not None:
            d["phase"] = self.phase
        if self.generated_at is not None:
            d["generated_at"] = self.generated_at
        if self.sha is not None:
            d["sha"] = self.sha
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _resolve_disposition(rule_id: str) -> Optional[str]:
    """Look up disposition for a rule via bind_rule."""
    if bind_rule is None:
        return None
    try:
        meta = bind_rule(rule_id)
        return meta.disposition
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def compute_risk_score(
    active_violations: Iterable[Violation],
    stale_suppression_count: int,
    *,
    phase: Optional[str] = None,
    sha: Optional[str] = None,
) -> RiskScore:
    """Compute the per-phase-exit risk score.

    Args:
        active_violations: Post-suppression-filter violations (output of #520).
        stale_suppression_count: Count of stale suppression markers.
        phase: Optional ATDD phase (RED, GREEN, SMOKE, REFACTOR).
        sha: Optional commit SHA.
    """
    violations = list(active_violations)

    # sum: total severity
    total = sum(v.severity for v in violations)

    # by_severity: count per severity level
    by_severity: Dict[str, int] = {}
    for v in violations:
        key = str(v.severity)
        by_severity[key] = by_severity.get(key, 0) + 1

    # by_archetype: severity sums per archetype (reuses utils/risk_score.py)
    by_archetype = compute_risk_breakdown(violations)

    # by_disposition: count per disposition via bind_rule
    by_disposition: Dict[str, int] = {}
    for v in violations:
        disp = _resolve_disposition(v.rule_id)
        if disp is not None:
            by_disposition[disp] = by_disposition.get(disp, 0) + 1

    generated_at = datetime.now(timezone.utc).isoformat()

    return RiskScore(
        sum=total,
        by_severity=by_severity,
        by_archetype=by_archetype,
        by_disposition=by_disposition,
        stale_suppressions=stale_suppression_count,
        phase=phase,
        generated_at=generated_at,
        sha=sha,
    )


def _load_schema() -> dict:
    """Load and cache the risk-score JSON Schema."""
    return json.loads(_SCHEMA_PATH.read_text())


def _validate_against_schema(data: dict) -> list[str]:
    """Validate data against risk-score.schema.json. Returns list of errors."""
    try:
        import jsonschema as _js
    except ImportError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print("[risk_score] jsonschema not installed — skipping validation", file=sys.stderr)
        return []

    schema = _load_schema()
    validator = _js.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(data)]


def write_risk_score(
    risk_score: RiskScore,
    *,
    sha: str,
    runtime_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Path:
    """Validate against schema and atomically write risk-score.json.

    On schema violation: abort write, emit error to stderr, return path
    (file will not exist).

    On success: write to ``<runtime_dir>/validations/<sha>/risk-score.json``.

    Returns the target path regardless of whether write succeeded.
    """
    if runtime_dir is None:
        if repo_root is None:
            repo_root = Path.cwd()
        runtime_dir = repo_root / ".atdd" / "runtime"

    target = runtime_dir / "validations" / sha / "risk-score.json"
    data = risk_score.to_dict()

    # Schema validation before write
    errors = _validate_against_schema(data)
    if errors:
        for err in errors:
            print(f"[risk_score] schema validation error: {err}", file=sys.stderr)
        return target

    # Atomic write: write to temp then rename
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(target)
    except Exception:
        # Clean up temp file on write failure
        try:
            tmp.unlink()
        except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            pass
        raise

    return target


__all__ = ["RiskScore", "compute_risk_score", "write_risk_score"]

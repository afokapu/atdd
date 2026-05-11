"""Validator-dispatch handler — M3 wiring (issue #588, spec §6.4 step 5).

Invokes the M3/M2/M4/M5 validation pipeline at each phase-exit gate:
  1. Select validators for the exited phase (M3 archetype directories).
  2. Dispatch via subprocess pytest with the violation_collector plugin (M2).
  3. Apply suppression filtering (M4).
  4. Compute and write risk score (M5).
  5. Gate the transition: strict violations, stale suppressions, or a
     risk-threshold breach return BLOCKED; clean runs return HANDLED.

Suppress-and-clean violations that are absorbed are appended to
`.atdd/runtime/coach/backlog/suppressed.jsonl` for later decommission.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import atdd

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition
from atdd.coach.runtime.dispatcher import dispatch_validators
from atdd.coach.runtime.suppression_filter import apply_suppression
from atdd.coach.runtime.risk_score import compute_risk_score, write_risk_score
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation

_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

# Maps the exited phase (transition.src) to the validator-selection phase name
# per spec §6.4: run validators for the work done in the exited phase.
_SRC_TO_VALIDATOR_PHASE: dict[Phase, str] = {
    Phase.INIT: "PLANNED",
    Phase.PLANNED: "PLANNED",
    Phase.RED: "RED",
    Phase.GREEN: "GREEN",
    Phase.SMOKE: "SMOKE",
    Phase.REFACTOR: "REFACTOR",
}

# Fallback archetype→directory mapping when validator_selection is unavailable.
_PHASE_ARCHETYPES: dict[str, list[str]] = {
    "PLANNED": ["planner"],
    "RED": ["tester"],
    "GREEN": ["coder"],
    "SMOKE": ["tester"],
    "REFACTOR": ["coder"],
}


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    """Invoke M3 validator dispatch at phase-exit gates per spec §6.4 step 5."""
    validator_phase = _SRC_TO_VALIDATOR_PHASE.get(transition.src)
    if validator_phase is None:
        return HandlerResult.NOOP

    try:
        repo_root = find_repo_root()
    except (RuntimeError, OSError) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(f"[validator_dispatch] repo root not found: {e}", file=sys.stderr)
        return HandlerResult.ERROR

    sha = _get_head_sha(repo_root)
    validator_dirs = _resolve_validator_dirs(validator_phase, repo_root)

    if not validator_dirs:
        return HandlerResult.NOOP

    if ctx.dry_run:
        return HandlerResult.HANDLED

    dispatch_result = dispatch_validators(
        sha=sha,
        validator_paths=validator_dirs,
        repo_root=repo_root,
    )

    raw_records = _read_violation_records(dispatch_result.violations_path)
    violations = [v for r in raw_records if (v := _record_to_violation(r)) is not None]

    suppression_result = apply_suppression(violations, repo_root, sha)

    if suppression_result.suppressed:
        _write_suppressed_backlog(suppression_result.suppressed, repo_root)

    phase_name = transition.src.value
    risk = compute_risk_score(
        suppression_result.active,
        len(suppression_result.stale_suppressions),
        phase=phase_name,
        sha=sha,
    )
    write_risk_score(risk, sha=sha, repo_root=repo_root)

    # Gate 1: stale suppressions block unless opted out.
    if suppression_result.stale_suppressions and not ctx.allow_stale_suppressions:
        return HandlerResult.BLOCKED

    # Gate 2: strict violations block.  Disposition is read from the raw JSONL
    # records so the check is independent of bind_rule registry availability.
    if _has_strict_active(raw_records, suppression_result.suppressed):
        return HandlerResult.BLOCKED

    # Gate 3: risk-threshold breach blocks (strictly greater than, not equal).
    if ctx.risk_threshold_block is not None and risk.sum > ctx.risk_threshold_block:
        return HandlerResult.BLOCKED

    return HandlerResult.HANDLED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_head_sha(repo_root: Path) -> str:
    """Resolve HEAD SHA via git, falling back to 'unknown' on failure."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip() or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(f"[validator_dispatch] git rev-parse HEAD failed: {e}", file=sys.stderr)
        return "unknown"


def _resolve_validator_dirs(phase_name: str, repo_root: Path) -> List[Path]:
    """Return archetype validator directories for the given phase."""
    archetypes = _phase_archetypes(phase_name, repo_root)
    dirs: List[Path] = []
    for archetype in sorted(archetypes):
        d = _ATDD_PKG_DIR / archetype / "validators"
        if d.is_dir():
            dirs.append(d)
    return dirs


def _phase_archetypes(phase_name: str, repo_root: Path) -> set[str]:
    """Derive archetype set from ValidatorSet; fall back to static mapping."""
    try:
        from atdd.coach.runtime.validator_selection import build_validator_set  # noqa: PLC0415
        from atdd.coach.utils.coach_config import load_coach_config  # noqa: PLC0415

        config = load_coach_config(repo_root)
        if not config.validators.enabled:
            return set()
        vset = build_validator_set(phase_name, config)
        archetypes: set[str] = set()
        for rule in vset.toolkit_slice:
            archetype = rule.rule_id.split(".")[0]
            if archetype in ("planner", "tester", "coder", "coach"):
                archetypes.add(archetype)
        return archetypes if archetypes else set(_PHASE_ARCHETYPES.get(phase_name, []))
    except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(f"[validator_dispatch] phase archetype resolution failed: {e}", file=sys.stderr)
        return set(_PHASE_ARCHETYPES.get(phase_name, []))


def _read_violation_records(path: Path) -> List[dict]:
    """Parse violations.jsonl into raw dicts (preserving the disposition field)."""
    if not path.exists():
        return []
    records: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"[validator_dispatch] skipping malformed violation record: {e}", file=sys.stderr)
    return records


def _record_to_violation(record: dict) -> Optional[Violation]:
    """Convert a raw violations.jsonl record to a Violation, or None on error."""
    try:
        return Violation(
            rule_id=record["rule_id"],
            severity=int(record["severity"]),
            location=record["location"],
            detail=record["detail"],
            fix_hint_ref=record.get("fix_hint_ref"),
        )
    except (KeyError, ValueError) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(f"[validator_dispatch] invalid violation record: {e}", file=sys.stderr)
        return None


def _has_strict_active(raw_records: List[dict], suppressed: List[Violation]) -> bool:
    """Return True if any strict-disposition violation is not suppressed.

    Disposition is read directly from the raw JSONL so this check works
    even when the rule_id is not yet in the bind_rule registry.
    """
    suppressed_keys = {(v.rule_id, v.location) for v in suppressed}
    for r in raw_records:
        if r.get("disposition") == "strict":
            key = (r.get("rule_id", ""), r.get("location", ""))
            if key not in suppressed_keys:
                return True
    return False


def _write_suppressed_backlog(violations: List[Violation], repo_root: Path) -> None:
    """Append absorbed suppress-and-clean violations to the backlog JSONL."""
    backlog_path = (
        repo_root / ".atdd" / "runtime" / "coach" / "backlog" / "suppressed.jsonl"
    )
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with backlog_path.open("a", encoding="utf-8") as fh:
            for v in violations:
                record = {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "location": v.location,
                    "detail": v.detail,
                }
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError as e:
        print(f"[validator_dispatch] backlog write failed: {e}", file=sys.stderr)

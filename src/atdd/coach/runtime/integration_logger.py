# URN: component:integrate-end-to-end:end-to-end-coach-cycle:integration_logger:backend:application
# Runtime: python
# Purpose: Structured INFO logging for every substrate↔coach boundary crossing (issue #533).

"""Substrate↔coach boundary integration logger (issue #533, #Q1 done-line).

Writes one JSON Lines entry per boundary crossing to
``.atdd/runtime/coach/integration.log`` so that any cross-boundary
integration bug surfaced during the first end-to-end coach-driven cycle
is diagnosable from the log alone.

Four boundary classes are instrumented:
  - ``validator-invocation``     — coach → violation_collector pytest plugin
  - ``bind_rule-lookup``         — coach → rule registry
  - ``spawn-harness-rendering``  — coach → render_*_rules_block
  - ``gate-verdict-consumption`` — coach → assert_disposition_satisfied

The logger is **opt-in**: call ``enable(runtime_dir)`` before running a
cycle. Without calling ``enable()``, every ``log_handoff()`` call is a
no-op so existing code paths are unaffected.

Entry schema (JSON Lines):
  {
    "timestamp": "2026-05-11T12:00:00.000000+00:00",  # ISO 8601 UTC
    "level": "INFO",
    "boundary_class": "<one of four classes above>",
    ... boundary-class-specific fields ...
  }
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------
_log_path: Optional[Path] = None


def enable(runtime_dir: Optional[Path] = None) -> Path:
    """Enable integration logging and return the log path.

    Creates parent directories as needed.  Idempotent — calling again
    with a different *runtime_dir* re-points the logger.

    Args:
        runtime_dir: Root of the ATDD runtime directory.  Defaults to
            ``<repo-root>/.atdd/runtime``.

    Returns:
        The resolved log path (``.atdd/runtime/coach/integration.log``).
    """
    global _log_path  # noqa: PLW0603
    if runtime_dir is None:
        runtime_dir = _default_runtime_dir()
    log_path = Path(runtime_dir) / "coach" / "integration.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_path = log_path
    return log_path


def disable() -> None:
    """Disable integration logging (no-op after call)."""
    global _log_path  # noqa: PLW0603
    _log_path = None


def is_enabled() -> bool:
    """Return True when integration logging is active."""
    return _log_path is not None


def log_handoff(boundary_class: str, **fields: Any) -> None:
    """Write one JSON Lines entry to the integration log.

    A no-op when logging is disabled (``enable()`` not called).

    Args:
        boundary_class: One of ``"validator-invocation"``,
            ``"bind_rule-lookup"``, ``"spawn-harness-rendering"``,
            ``"gate-verdict-consumption"``.
        **fields: Boundary-class-specific payload fields.
    """
    if _log_path is None:
        return
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "INFO",
        "boundary_class": boundary_class,
        **fields,
    }
    try:
        with _log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except OSError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        print(f"[integration_logger] write failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Boundary-class convenience helpers
# ---------------------------------------------------------------------------


def log_validator_invocation(
    *,
    validator_id: str,
    rule_id: str,
    phase: str,
    commit_sha: str,
    outcome: str,
) -> None:
    """Log a coach → violation_collector boundary crossing."""
    log_handoff(
        "validator-invocation",
        validator_id=validator_id,
        rule_id=rule_id,
        phase=phase,
        commit_sha=commit_sha,
        outcome=outcome,
    )


def log_bind_rule_lookup(
    *,
    rule_id: str,
    resolved_severity: Optional[int] = None,
    resolved_disposition: Optional[str] = None,
) -> None:
    """Log a coach → rule registry boundary crossing."""
    log_handoff(
        "bind_rule-lookup",
        rule_id=rule_id,
        resolved_severity=resolved_severity,
        resolved_disposition=resolved_disposition,
    )


def log_spawn_harness_rendering(
    *,
    renderer_name: str,
    persona: str,
    rule_count: int = 0,
) -> None:
    """Log a coach → render_*_rules_block boundary crossing."""
    log_handoff(
        "spawn-harness-rendering",
        renderer_name=renderer_name,
        persona=persona,
        rule_count=rule_count,
    )


def log_gate_verdict(
    *,
    validator_id: str,
    disposition_tier: str,
    passed: bool,
    violation_count: int,
    driving_violations: Optional[list[str]] = None,
) -> None:
    """Log a coach → assert_disposition_satisfied boundary crossing."""
    log_handoff(
        "gate-verdict-consumption",
        validator_id=validator_id,
        disposition_tier=disposition_tier,
        passed=passed,
        violation_count=violation_count,
        driving_violations=driving_violations or [],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_runtime_dir() -> Path:
    from atdd.coach.utils.repo import find_repo_root

    try:
        return find_repo_root() / ".atdd" / "runtime"
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        print("[integration_logger] could not find repo root; using cwd", file=sys.stderr)
        return Path(".atdd") / "runtime"


# ---------------------------------------------------------------------------
# Hook wiring
# ---------------------------------------------------------------------------


def wire_hooks() -> None:
    """Register integration-logger callbacks into gate and rule-binding hooks.

    Call this after ``enable()`` to activate per-boundary logging.
    Both the gate verdict hook and the bind_rule hook are registered;
    they emit log entries only when ``is_enabled()`` is True (i.e. after
    ``enable()`` has been called).
    """
    from atdd.coach.utils.disposition_gate import register_gate_verdict_hook
    from atdd.coach.utils.rule_binding import register_bind_rule_hook

    def _gate_hook(
        validator_id: str,
        disposition_tier: str,
        passed: bool,
        violation_count: int,
        driving_ids: "list[str]",
    ) -> None:
        log_gate_verdict(
            validator_id=validator_id,
            disposition_tier=disposition_tier,
            passed=passed,
            violation_count=violation_count,
            driving_violations=driving_ids,
        )

    def _bind_hook(metadata: "object") -> None:
        log_bind_rule_lookup(
            rule_id=getattr(metadata, "rule_id", str(metadata)),
            resolved_severity=getattr(metadata, "severity", None),
            resolved_disposition=getattr(metadata, "disposition", None),
        )

    register_gate_verdict_hook(_gate_hook)
    register_bind_rule_hook(_bind_hook)


def unwire_hooks() -> None:
    """Remove all hooks registered by ``wire_hooks()`` (use in tests/teardown)."""
    from atdd.coach.utils.disposition_gate import clear_gate_verdict_hooks
    from atdd.coach.utils.rule_binding import clear_bind_rule_hooks

    clear_gate_verdict_hooks()
    clear_bind_rule_hooks()

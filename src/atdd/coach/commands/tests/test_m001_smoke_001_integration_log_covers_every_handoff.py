# URN: test:integrate-end-to-end:end-to-end-coach-cycle:M001-SMOKE-001-integration-log-covers-every-handoff
# Acceptance: acc:integrate-end-to-end:M001-SMOKE-001-integration-log-covers-every-handoff
# WMBT: wmbt:integrate-end-to-end:M001
# Phase: GREEN
# Layer: assembly
# Harness: smoke/backend
"""M001-SMOKE-001 — Integration log covers every substrate↔coach boundary class.

Verifies that ``.atdd/runtime/coach/integration.log`` is non-empty and
contains at least one structured JSON Lines entry for each of the four
substrate↔coach boundary classes:

  1. ``validator-invocation`` — coach → substrate pytest plugin
  2. ``bind_rule-lookup``    — coach → rule registry
  3. ``spawn-harness-rendering`` — coach → render_*_rules_block
  4. ``gate-verdict-consumption`` — coach → assert_disposition_satisfied

Each entry must be a valid JSON object with a ``boundary_class`` field
matching one of the four known classes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[5]
COACH_RUNTIME = REPO_ROOT / ".atdd" / "runtime" / "coach"
INTEGRATION_LOG = COACH_RUNTIME / "integration.log"

_EXPECTED_BOUNDARY_CLASSES = frozenset({
    "validator-invocation",
    "bind_rule-lookup",
    "spawn-harness-rendering",
    "gate-verdict-consumption",
})


def _skip_if_no_log() -> None:
    if not INTEGRATION_LOG.exists():
        pytest.skip(
            f"No integration log found at {INTEGRATION_LOG}. "
            "Run `atdd coach <N>` on the worked-example issue with integration logging enabled. "
            "The integration_logger module must be wired into the four boundary points before "
            "the log is produced."
        )


def test_integration_log_exists_and_nonempty() -> None:
    _skip_if_no_log()
    lines = [ln for ln in INTEGRATION_LOG.read_text().splitlines() if ln.strip()]
    assert lines, (
        f"integration.log exists at {INTEGRATION_LOG} but is empty. "
        "At least one boundary crossing must be logged."
    )


def test_integration_log_entries_are_valid_json() -> None:
    _skip_if_no_log()
    lines = [ln for ln in INTEGRATION_LOG.read_text().splitlines() if ln.strip()]
    invalid: list[str] = []
    for i, line in enumerate(lines):
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            invalid.append(f"line {i + 1}: {exc}")
    assert not invalid, (
        f"integration.log contains invalid JSON on {len(invalid)} line(s):\n"
        + "\n".join(invalid[:5])
    )


def test_integration_log_has_boundary_class_field() -> None:
    _skip_if_no_log()
    lines = [ln for ln in INTEGRATION_LOG.read_text().splitlines() if ln.strip()]
    entries = [json.loads(ln) for ln in lines]
    missing_field = [i + 1 for i, e in enumerate(entries) if "boundary_class" not in e]
    assert not missing_field, (
        f"integration.log entries at line(s) {missing_field[:10]} are missing the "
        f"'boundary_class' field. Every entry must declare which boundary class it crossed."
    )


def test_integration_log_covers_all_four_boundary_classes() -> None:
    _skip_if_no_log()
    lines = [ln for ln in INTEGRATION_LOG.read_text().splitlines() if ln.strip()]
    entries = [json.loads(ln) for ln in lines]
    observed_classes = {e.get("boundary_class") for e in entries if "boundary_class" in e}
    missing_classes = _EXPECTED_BOUNDARY_CLASSES - observed_classes
    assert not missing_classes, (
        f"integration.log is missing entries for boundary class(es): {sorted(missing_classes)}\n"
        f"Observed: {sorted(observed_classes)}\n"
        f"All four boundary classes must be logged:\n"
        f"  validator-invocation    — coach → violation_collector pytest plugin\n"
        f"  bind_rule-lookup        — coach → rule registry\n"
        f"  spawn-harness-rendering — coach → render_*_rules_block\n"
        f"  gate-verdict-consumption — coach → assert_disposition_satisfied"
    )

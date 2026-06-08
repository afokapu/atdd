# URN: test:observe-and-correct:observer-runtime-and-rules:observer-detectors-unit
# Phase: GREEN
# Layer: application
"""Direct unit coverage for the relocated observer detectors (issue #985).

These replace the retired parity tests: the classifier + drift correctors are now first-class
observer code in ``observer_rules/detectors.py`` and are covered here directly,
not by identity-comparison against a legacy module.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.observer_rules import detectors
from atdd.coach.observer_rules import (
    bash_auto_approve,
    canonical_naming_drift,
    layout_drift,
    smoke_skip,
)

pytestmark = [pytest.mark.platform]


_PROMPT = "Do you want to proceed?"


# ---------------------------------------------------------------------------
# Bash classifier (rule 13)
# ---------------------------------------------------------------------------
def test_bash_patterns_load_from_observer_convention():
    allow, deny = detectors._load_bash_patterns()
    assert allow and deny, "bash_classifier patterns must load from observer.convention.yaml"
    # Every entry carries a canonical coach.observer.* rule id.
    for p in allow + deny:
        assert p.rule_id.startswith("coach.observer.bash-")


def test_classify_prompt_idle_without_marker():
    assert detectors.classify_prompt("nothing here").action == "idle"


def test_classify_prompt_auto_approves_read_only_git():
    decision = detectors.classify_prompt(f"Bash(git status)\n{_PROMPT}")
    assert decision.action == "auto_approve"


def test_classify_prompt_escalates_destructive_bash():
    decision = detectors.classify_prompt(f"Bash(rm -rf build)\n{_PROMPT}")
    assert decision.action == "escalate"


def test_classify_prompt_escalates_network_egress_even_if_otherwise_safe():
    decision = detectors.classify_prompt(f"Bash(curl https://example.com)\n{_PROMPT}")
    assert decision.action == "escalate"


def test_classify_prompt_escalates_unknown_non_bash_tool():
    decision = detectors.classify_prompt(f"SomeTool(args)\n{_PROMPT}")
    assert decision.action == "escalate"


def test_classify_prompt_auto_approves_known_safe_tool():
    decision = detectors.classify_prompt(f"Read(file.py)\n{_PROMPT}")
    assert decision.action == "auto_approve"


def test_extract_bash_command_balances_parens():
    assert detectors.extract_bash_command(f"Bash(echo (nested))\n{_PROMPT}") == "echo (nested)"


# ---------------------------------------------------------------------------
# Violation scanner (rule 16)
# ---------------------------------------------------------------------------
def test_detect_violation_flags_atdd_hand_edit():
    decision = detectors.detect_violation("Edit(.atdd/config.yaml)")
    assert decision is not None and decision.matched == ".atdd/ hand-edit"


def test_detect_violation_flags_smoke_skip():
    decision = detectors.detect_violation("atdd issue 5 --status REFACTOR")
    assert decision is not None and decision.matched == "SMOKE skip"


def test_detect_violation_quiet_when_smoke_present():
    assert detectors.detect_violation("--status REFACTOR after SMOKE passed") is None


# ---------------------------------------------------------------------------
# Drift correctors (rules 14, 15)
# ---------------------------------------------------------------------------
class _FakeBackend:
    def __init__(self):
        self.renamed = []

    def rename(self, ref, name):
        self.renamed.append((ref, name))

    def send(self, ref, text):
        pass


def test_correct_naming_drift_renames_then_idempotent(tmp_path: Path):
    backend = _FakeBackend()
    cache: dict[str, str] = {}
    log = tmp_path / "log.jsonl"
    assert detectors.correct_naming_drift(
        backend, "surface:1", "ATDD985-decommission", cache, log_path=log
    ) is True
    assert backend.renamed == [("surface:1", "ATDD985-decommission")]
    # Second call is a no-op (already applied).
    assert detectors.correct_naming_drift(
        backend, "surface:1", "ATDD985-decommission", cache, log_path=log
    ) is False


def test_correct_layout_drift_announces_then_idempotent(tmp_path: Path):
    cache: dict[str, str] = {}
    log = tmp_path / "log.jsonl"
    assert detectors.correct_layout_drift(3, cache, log_path=log) is True
    assert detectors.correct_layout_drift(3, cache, log_path=log) is False


# ---------------------------------------------------------------------------
# Rule factories wire the detectors into ObserverRule objects
# ---------------------------------------------------------------------------
def test_rule_builders_resolve_canonical_ids():
    assert bash_auto_approve.build_rule().rule_id == "coach.observer.bash-auto-approve"
    assert canonical_naming_drift.build_rule().rule_id == "coach.observer.canonical-naming-drift"
    assert layout_drift.build_rule().rule_id == "coach.observer.layout-drift"
    assert smoke_skip.build_rule().rule_id == "coach.observer.smoke-skip"

# URN: test:observe-and-correct:observer-runtime-and-rules:M003-UNIT-001-rule-13-bash-auto-approve
# Acceptance: acc:observe-and-correct:M003-UNIT-001-rule-13-bash-auto-approve
# WMBT: wmbt:observe-and-correct:M003
# Phase: RED
# Layer: application
"""M003-UNIT-001 — Rule `coach.observer.bash-auto-approve` (rule 13).

Per spec §0.2 / §8.3, the rule absorbs ``babysit.classify_prompt``
(plus its ``_classify_bash_command`` / ``_load_bash_patterns`` /
``BashPattern`` helpers) into the observer substrate. The rule must
behave at parity with babysit's classifier:

  * known-safe bash prompt (matches an allow pattern) → auto-approve
  * deny-pattern bash prompt → escalate
  * unknown prompt → escalate
  * the bash-patterns YAML file is unchanged

Issue #513 (L4). Spec: ``atdd-coach-spec-v9.md`` §8.3.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands import babysit, observer

pytestmark = [pytest.mark.platform]


def _screen_with_bash(cmd: str) -> str:
    """Build a synthetic prompt screen that babysit.classify_prompt accepts.

    The marker ``Do you want to proceed?`` is one of the literal markers
    babysit checks (``_PROMPT_MARKERS``); ``Bash(<cmd>)`` is the syntax
    ``extract_bash_command`` parses.
    """
    return f"... earlier output ...\nBash({cmd})\nDo you want to proceed?\n❯ 1. Yes\n"


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_rule_13_module_exposes_build_rule_and_predicate():
    """Rule 13 module must export a ``build_rule()`` factory + ``predicate()``."""
    from atdd.coach.observer_rules import bash_auto_approve

    assert callable(bash_auto_approve.build_rule), (
        "rule 13 module must expose a build_rule() factory"
    )
    assert callable(bash_auto_approve.predicate), (
        "rule 13 module must expose a pure predicate(ctx) -> bool"
    )


def test_rule_13_build_rule_binds_canonical_rule_id():
    """The factory returns an ObserverRule whose rule_id is the canonical one."""
    from atdd.coach.observer_rules import bash_auto_approve

    rule = bash_auto_approve.build_rule()
    assert isinstance(rule, observer.ObserverRule)
    assert rule.rule_id == "coach.observer.bash-auto-approve"


# ---------------------------------------------------------------------------
# Parity with babysit.classify_prompt
# ---------------------------------------------------------------------------


def test_rule_13_parity_with_classify_prompt_safe_bash_does_not_fire():
    """A known-safe bash prompt (e.g. ``git status``) must NOT escalate.

    babysit.classify_prompt returns ``action="auto_approve"`` for this case;
    the observer rule mirrors that by NOT firing (no escalation correction
    written). The auto-approval side effect (sending "1\\n" to the surface)
    is the multiplexer's job and lives outside this rule.
    """
    from atdd.coach.observer_rules import bash_auto_approve

    screen = _screen_with_bash("git status")

    # Babysit baseline: classify_prompt → auto_approve
    decision = babysit.classify_prompt(screen)
    assert decision.action == "auto_approve", (
        "babysit baseline: known-safe bash command must auto-approve"
    )

    # Observer rule: predicate must NOT fire on auto-approve case.
    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=tuple(screen.splitlines()),
    )
    assert bash_auto_approve.predicate(ctx) is False


def test_rule_13_parity_with_classify_prompt_deny_pattern_fires():
    """A deny-pattern bash prompt (e.g. ``rm -rf /tmp/x``) must escalate."""
    from atdd.coach.observer_rules import bash_auto_approve

    screen = _screen_with_bash("rm -rf /tmp/x")

    decision = babysit.classify_prompt(screen)
    assert decision.action == "escalate", (
        "babysit baseline: rm command must escalate"
    )

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=tuple(screen.splitlines()),
    )
    assert bash_auto_approve.predicate(ctx) is True


def test_rule_13_parity_with_classify_prompt_unknown_bash_fires():
    """An unknown bash command escalates per the classifier's deny-then-allow rule."""
    from atdd.coach.observer_rules import bash_auto_approve

    screen = _screen_with_bash("some-unknown-binary --do-stuff")

    decision = babysit.classify_prompt(screen)
    assert decision.action == "escalate"

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=tuple(screen.splitlines()),
    )
    assert bash_auto_approve.predicate(ctx) is True


def test_rule_13_no_prompt_marker_does_not_fire():
    """Without a prompt marker, classify_prompt returns ``idle`` — rule must not fire."""
    from atdd.coach.observer_rules import bash_auto_approve

    screen = "just some output\nno prompt here\n"

    decision = babysit.classify_prompt(screen)
    assert decision.action == "idle"

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=tuple(screen.splitlines()),
    )
    assert bash_auto_approve.predicate(ctx) is False


def test_rule_13_uses_load_bash_patterns_verbatim():
    """The rule must reuse babysit's ``_load_bash_patterns`` /``BashPattern``
    so the bash-patterns YAML file remains the single source of truth."""
    from atdd.coach.observer_rules import bash_auto_approve

    # The rule module must import the absorbed helpers — not copy them.
    assert bash_auto_approve._load_bash_patterns is babysit._load_bash_patterns, (
        "rule 13 must reuse babysit._load_bash_patterns verbatim per spec §0.2"
    )
    assert bash_auto_approve.BashPattern is babysit.BashPattern, (
        "rule 13 must reuse babysit.BashPattern verbatim per spec §0.2"
    )
    assert bash_auto_approve.classify_prompt is babysit.classify_prompt, (
        "rule 13 must reuse babysit.classify_prompt verbatim per spec §0.2"
    )


def test_rule_13_bash_patterns_file_unchanged():
    """The orchestration convention's bash-patterns block must remain the
    single source of truth — rule 13 reads it via ``_load_bash_patterns``,
    it does not redeclare or override patterns."""
    import atdd as _atdd

    pkg_dir = Path(_atdd.__file__).resolve().parent
    convention = pkg_dir / "coach" / "conventions" / "orchestration.convention.yaml"
    text = convention.read_text(encoding="utf-8")
    assert "bash_auto_approve_patterns:" in text, (
        "orchestration.convention.yaml::babysit.bash_auto_approve_patterns must exist"
    )
    assert "bash_deny_patterns:" in text, (
        "orchestration.convention.yaml::babysit.bash_deny_patterns must exist"
    )

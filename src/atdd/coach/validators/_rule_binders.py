# Phase: GREEN
# Layer: backend.domain
"""Rule binders for coach rules whose enforcement is a binding roundtrip (#1385).

The `binding/emitted_identity_roundtrip` template proves a declaration→implementation
binding by observing that a rule's declared ``validator`` module emits the rule's id via
``bind_rule(<id>)`` at import time. The convention variants under
``validators/conventions/binding/`` *test* that roundtrip but do not *provide* the
emission, so these rules cannot be repointed at a variant — doing so makes the
fault-injection vacuous.

Before #1385 the emission lived inside three legacy persona validators. Those files were
retired by the #1207 sweep, so the emitters live here instead: a non-test module the rules
point at directly. ``_support/graph_loader`` scans ``bind_rule(...)`` across all
``src/atdd/**/*.py``, and this module sits under a ``validators/`` directory, so both the
forward binding and the roundtrip resolve against it.

The behavioural coverage those legacy files also carried did NOT move here — it moved to
``coach/validators/tests/``:

  * ``tests/test_no_hardcoded_rule_severity.py`` — the severity AST scan
  * ``tests/test_commit_trailers_emit.py``      — the GitWatcher emit assertion
  * ``tests/test_spawn_cli_surface.py``         — the spawn surface asserts
"""
from __future__ import annotations

from atdd.coach.utils.rule_binding import bind_rule

# --- coach.commit-trailers.* ------------------------------------------------
PHASE_RULE = bind_rule("coach.commit-trailers.phase-required")
WMBT_URN_RULE = bind_rule("coach.commit-trailers.wmbt-urn-required")
AGENT_ID_RULE = bind_rule("coach.commit-trailers.agent-id-required")
ISSUE_RULE = bind_rule("coach.commit-trailers.issue-required")

RULE_FOR_TRAILER = {
    "Phase": PHASE_RULE,
    "WMBT-Urn": WMBT_URN_RULE,
    "Agent-Id": AGENT_ID_RULE,
    "Issue": ISSUE_RULE,
}

# --- coach.spawn.atdd-spawn-cli ---------------------------------------------
SPAWN_CLI_RULE = bind_rule("coach.spawn.atdd-spawn-cli")

# --- coach.rule-id.no-hardcoded-rule-severity -------------------------------
NO_HARDCODED_RULE_SEVERITY_RULE = bind_rule("coach.rule-id.no-hardcoded-rule-severity")


def commit_trailers_rules() -> dict:
    """The bound ``coach.commit-trailers.*`` family, keyed by trailer name."""
    return RULE_FOR_TRAILER


def spawn_cli_rule():
    """The bound ``coach.spawn.atdd-spawn-cli`` rule."""
    return SPAWN_CLI_RULE


def no_hardcoded_rule_severity_rule():
    """The bound ``coach.rule-id.no-hardcoded-rule-severity`` rule."""
    return NO_HARDCODED_RULE_SEVERITY_RULE

# URN: test:govern-projection-fields:validate-field-writer:E001-UNIT-001-red-human-writes-external-refs
# Acceptance: acc:govern-projection-fields:E001-UNIT-001-red-human-writes-external-refs
# WMBT: wmbt:govern-projection-fields:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a human-authored projection diff that mutates external_refs.github.issue_number is refused by the field-writer validator, which names the offending leaf path and the legal writer extension-bot and exits non-zero — the GitHub mirror is presentation, never a second source of truth Refs #1400.
"""A human writing the bot's subtree is refused, by name (E001-UNIT-001).

wagon: govern-projection-fields | feature: validate-field-writer | phase: RED
WMBT: wmbt:govern-projection-fields:E001

``external_refs`` is where the GitHub mirror's issue number lives, and it is the extension
bot's alone (spec §7.1). A human hand-editing it is the corruption every *other* check waves
through: the document stays canonical, stays schema-valid, and every lifecycle transition in
it is legal. Nothing is wrong with the diff except who wrote it.

And the leaf matters. A report that says "external_refs changed" sends the operator off to
diff a subtree by hand; this one names ``external_refs.github.issue_number``.
"""
from __future__ import annotations

from atdd.state import ownership
from atdd.state.ownership import RULE_BOT_ONLY, WRITER_EXTENSION_BOT

from ._helpers import UID_X, document, projection

#: A human, as git records one: a name and an email, and no bot identity anywhere in it.
HUMAN = "Dev A <dev-a@example.invalid>"


def test_e001_unit_001_red_human_writes_external_refs() -> None:
    """The wrong-writer violation names the leaf path, the legal writer, and exits non-zero."""
    policy = ownership.default_policy()
    base = projection(document(external_refs={"github": {"issue_number": 1400}}))
    head = projection(document(external_refs={"github": {"issue_number": 1401}}))

    report = ownership.check_diff(policy, base, head, actor=HUMAN)

    assert not report.ok
    assert report.exit_code == 1, "CI reads the exit code, not the prose"

    violation = report.violations[0]
    assert violation.path == "external_refs.github.issue_number", "the LEAF, not the subtree"
    assert violation.writer == WRITER_EXTENSION_BOT
    assert violation.rule == RULE_BOT_ONLY
    assert violation.actor == HUMAN

    rendered = report.render()
    assert "external_refs.github.issue_number" in rendered
    assert WRITER_EXTENSION_BOT in rendered

    # The diff is otherwise beyond reproach — which is the point: no other check refuses it.
    assert ownership.check_coverage(ownership.DEFAULT_POLICY).ok
    assert head[UID_X]["phase"] == base[UID_X]["phase"], "no lifecycle claim is being made at all"

    # And the bot writing its own subtree is admitted, so the rule is about ownership rather
    # than about the field being untouchable.
    assert ownership.check_diff(policy, base, head, actor="bot:github").ok

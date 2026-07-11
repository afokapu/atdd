# URN: test:govern-projection-fields:validate-field-writer:E001-UNIT-002-green-blocks-both-directions
# Acceptance: acc:govern-projection-fields:E001-UNIT-002-green-blocks-both-directions
# WMBT: wmbt:govern-projection-fields:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the field-writer validator blocks a human writing external_refs (naming the legal writer extension-bot) and an extension bot writing the lifecycle field phase (naming the legal writer core-lifecycle), and passes the core-lifecycle diff that moves phase — one table, both directions Refs #1400.
"""Both directions, from one declaration (E001-UNIT-002).

wagon: govern-projection-fields | feature: validate-field-writer | phase: RED
WMBT: wmbt:govern-projection-fields:E001

The boundary has two sides and both leak (spec §8.2):

- a **human** writing ``external_refs`` makes the mirror a second source of truth that core
  will then disagree with;
- an **extension bot** writing ``phase`` makes presentation authoritative over lifecycle,
  which is the failure the whole projection model exists to remove.

One table refuses both, and admits the writer that owns the field it touched.
"""
from __future__ import annotations

import pytest

from atdd.state import ownership
from atdd.state.ownership import (
    RULE_MONOTONIC_GATED,
    WRITER_CORE_LIFECYCLE,
    WRITER_EXTENSION_BOT,
)

from ._helpers import PLANNED_TO_RED, UID_X, UID_Y, document, projection

HUMAN = "Dev A <dev-a@example.invalid>"
BOT = "github-actions[bot] <bot@users.noreply.github.com>"
CORE_LIFECYCLE = "core-lifecycle"


def test_e001_unit_002_green_blocks_both_directions() -> None:
    """Human→external_refs rejected, bot→phase rejected, core-lifecycle→phase admitted."""
    policy = ownership.default_policy()
    base = projection(document(phase="PLANNED", external_refs={"github": {"issue_number": 1400}}))
    refs_moved = projection(
        document(phase="PLANNED", external_refs={"github": {"issue_number": 1401}}))
    phase_moved = projection(
        document(phase="RED", external_refs={"github": {"issue_number": 1400}}))

    # 1. The human touching the bot's subtree: rejected, naming the field and its legal writer.
    human = ownership.check_diff(policy, base, refs_moved, actor=HUMAN)
    assert not human.ok
    assert human.violations[0].path.startswith("external_refs")
    assert human.violations[0].writer == WRITER_EXTENSION_BOT
    assert WRITER_EXTENSION_BOT in human.render()

    # 2. The extension bot touching a lifecycle field: rejected, naming the field and core.
    bot = ownership.check_diff(policy, base, phase_moved, actor=BOT)
    assert not bot.ok
    violation = bot.violations[0]
    assert violation.path == "phase"
    assert violation.writer == WRITER_CORE_LIFECYCLE
    assert violation.rule == RULE_MONOTONIC_GATED
    assert WRITER_CORE_LIFECYCLE in bot.render()
    assert "never lifecycle truth" in violation.detail

    # 3. Core moving the phase it owns: admitted, exit zero.
    core = ownership.check_diff(policy, base, phase_moved, actor=CORE_LIFECYCLE)
    assert core.ok, core.render()
    assert core.exit_code == 0

    # The bot is recognised however git spells its identity — the `bot:` namespace core uses,
    # GitHub's `…[bot]` author name, and a bot email all resolve to the same writer.
    for identity in ("bot:github", BOT, "mirror <ci-bot@example.invalid>"):
        assert ownership.allowed_writers(identity) == {WRITER_EXTENSION_BOT}, identity

    # ...and the evidence a lifecycle commit carries is a matter for the transition gate, not
    # for this one: ownership is about WHO wrote the field, never about whether they may.
    assert set(PLANNED_TO_RED) and core.ok


@pytest.mark.parametrize("actor", ["", "   "])
def test_e001_unit_002_green_blocks_both_directions_unattributed(actor) -> None:
    """An unattributed diff carries no wrong-writer claim — but uid is still immutable."""
    policy = ownership.default_policy()
    base = projection(document(external_refs={"github": {"issue_number": 1400}}))
    head = projection(document(external_refs={"github": {"issue_number": 1401}}))

    # No writer identity: accusing an unknown writer of being the wrong one would be a guess.
    assert ownership.check_diff(policy, base, head, actor=actor).ok

    # The writer-independent rules still hold, because they do not depend on knowing who wrote it.
    # A uid rewrite is the file keeping its name while the document inside it changes identity.
    rewritten = {UID_X: document(uid=UID_Y)}
    report = ownership.check_diff(policy, projection(document()), rewritten, actor=actor)
    assert not report.ok
    assert "immutable" in report.render()
    assert report.violations[0].path == "uid"

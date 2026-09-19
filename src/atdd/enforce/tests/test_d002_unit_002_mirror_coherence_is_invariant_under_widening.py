# URN: test:govern-registry:D002-UNIT-002-mirror-coherence-is-invariant-under-widening
# Acceptance: acc:govern-registry:D002-UNIT-002-mirror-coherence-is-invariant-under-widening
# WMBT: wmbt:govern-registry:D002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:govern-registry:D002-UNIT-002-mirror-coherence-is-invariant-under-widening.

``find_mirror_incoherences`` defaults its reference set to ``core_rule_ids()``. Once
the roots widen, that reference set contains the very nodes the check is auditing, so
a node that mirrors NOTHING resolves against itself and the check goes quiet. The
count must not move because of a roots change -- only because a mirror was fixed.
"""
from __future__ import annotations

from pathlib import Path

import atdd
from atdd.coach.utils import rule_binding
from atdd.enforce.registry import find_mirror_incoherences


def _substrate(root: Path) -> Path:
    """A substrate whose single extension node mirrors nothing (self-referential)."""
    nodes = root / ".atdd" / "extensions" / "pkg" / "0.1.0" / "conventions"
    nodes.mkdir(parents=True)
    (nodes / "ext.only.rule.convention.yaml").write_text(
        "rule_id: ext.only.rule\n"
        "severity: 3\n"
        "source:\n"
        "  legacy_rule_id: ext.only.rule\n",
        encoding="utf-8",
    )
    return root / ".atdd" / "extensions"


def test_mirror_coherence_is_invariant_under_widening(monkeypatch, tmp_path: Path) -> None:
    ext_root = _substrate(tmp_path)

    before = {m.extension_rule_id for m in find_mirror_incoherences(tmp_path)}
    assert before == {"ext.only.rule"}, (
        "a node whose legacy_rule_id names no live core rule must be reported"
    )

    # #1992's change: the extension tree enters the registry's default search roots.
    monkeypatch.setattr(
        rule_binding, "_default_roots", lambda: [Path(atdd.__file__).resolve().parent, ext_root]
    )

    after = {m.extension_rule_id for m in find_mirror_incoherences(tmp_path)}
    # Compare the SET, not the count: a regression that exchanged one incoherent node
    # for another would preserve the count and slip through a count-only assertion.
    assert after == before, (
        f"mirror-coherence set moved {sorted(before)} -> {sorted(after)} because the roots "
        "widened, not because a mirror was repaired -- the guard self-neutralized"
    )

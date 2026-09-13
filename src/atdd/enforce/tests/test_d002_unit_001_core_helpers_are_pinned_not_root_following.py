# URN: test:govern-registry:D002-UNIT-001-core-helpers-are-pinned-not-root-following
# Acceptance: acc:govern-registry:D002-UNIT-001-core-helpers-are-pinned-not-root-following
# WMBT: wmbt:govern-registry:D002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:govern-registry:D002-UNIT-001-core-helpers-are-pinned-not-root-following.

The enforce-side core helpers must answer "what is the CORE territory" from a pinned
root set, not from whatever the rule registry currently searches. Today they are a
pass-through to ``find_convention_files()`` with no roots, so they follow
``_default_roots()`` -- and #1992 widens exactly that. A guard that polices the
core/extension boundary must not be redefined by the roots it polices.
"""
from __future__ import annotations

from pathlib import Path

import atdd
from atdd.coach.utils import rule_binding
from atdd.enforce.registry import core_convention_files, core_rule_ids


def test_core_helpers_are_pinned_not_root_following(monkeypatch, tmp_path: Path) -> None:
    ext_root = tmp_path / "extensions"
    (ext_root / "pkg").mkdir(parents=True)
    (ext_root / "pkg" / "brand.new.rule.convention.yaml").write_text(
        "rule_id: brand.new.rule\nseverity: 3\n", encoding="utf-8"
    )

    pkg_dir = Path(atdd.__file__).resolve().parent
    narrow = core_rule_ids()
    assert narrow, "core registry unexpectedly empty"

    # #1992's change: the registry's default search roots now admit the extension tree.
    monkeypatch.setattr(rule_binding, "_default_roots", lambda: [pkg_dir, ext_root])

    # The guards must not move with it.
    assert core_rule_ids() == narrow, (
        "core_rule_ids() followed the widened default roots -- the guard is "
        "root-following, so widening redefines what it calls 'core'"
    )
    assert not any("extensions" in str(p) for p in core_convention_files()), (
        "a file under the extension tree was admitted into the CORE convention set"
    )

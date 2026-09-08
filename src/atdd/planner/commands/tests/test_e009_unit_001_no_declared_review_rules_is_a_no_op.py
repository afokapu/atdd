# URN: test:author-atdd-substrate:E009-UNIT-001-no-declared-review-rules-is-a-no-op
# Acceptance: acc:author-atdd-substrate:E009-UNIT-001-no-declared-review-rules-is-a-no-op
# WMBT: wmbt:author-atdd-substrate:E009
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:author-atdd-substrate:E009-UNIT-001-no-declared-review-rules-is-a-no-op.

The AGNOSTICISM guarantee. Core names no checker, no rule and no controlled-language
vocabulary — the gating rule ids come from the repo's own config. A repo that declares
none must author exactly as before and must not invoke enforcement at all, so an
install with no review extension pays nothing and behaves identically.
"""
from __future__ import annotations

from pathlib import Path

from atdd.planner.commands import author


def test_e009_unit_001_no_declared_review_rules_is_a_no_op(tmp_path: Path, monkeypatch):
    called: list = []
    monkeypatch.setattr(
        author, "review_authored_document",
        lambda *a, **k: called.append((a, k)), raising=False,
    )

    dest = tmp_path / "plan" / "demo" / "E001.yaml"
    # No .atdd/config.yaml at all — the "no review extension installed" case.
    written = author._write_yaml(dest, {"urn": "wmbt:demo:E001"}, artifact_kind="wmbt")

    assert written == dest and dest.is_file()
    # The seam must not even consult the review path when nothing is declared ...
    assert called == [], "review was invoked despite no declared review rules"
    # ... and the artifact is byte-identical to an unguarded write.
    assert "wmbt:demo:E001" in dest.read_text(encoding="utf-8")

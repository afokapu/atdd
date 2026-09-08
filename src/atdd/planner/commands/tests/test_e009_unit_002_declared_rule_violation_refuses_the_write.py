# URN: test:author-atdd-substrate:E009-UNIT-002-declared-rule-violation-refuses-the-write
# Acceptance: acc:author-atdd-substrate:E009-UNIT-002-declared-rule-violation-refuses-the-write
# WMBT: wmbt:author-atdd-substrate:E009
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:author-atdd-substrate:E009-UNIT-002-declared-rule-violation-refuses-the-write.

A declared review rule that fires must leave NO artifact at the canonical path — the
whole point of gating pre-write rather than post-commit — and the raised error must
carry the findings, because the authoring agent's only correction loop is reading them
and re-running the command.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.planner.commands import author


def _declare_review_rules(root: Path, rules: list) -> None:
    atdd = root / ".atdd"
    atdd.mkdir(parents=True, exist_ok=True)
    (atdd / "config.yaml").write_text(
        yaml.safe_dump({"author_review": {"rules": rules}}, sort_keys=False),
        encoding="utf-8",
    )


_FINDING = {
    "rule_id": "planner.controlled-language.ste-conformance",
    "location": "plan/demo/E001.yaml:statement",
    "evidence": 'offset=4 length=6 msg="Use an approved word."',
}


def test_e009_unit_002_declared_rule_violation_refuses_the_write(tmp_path: Path, monkeypatch):
    _declare_review_rules(tmp_path, ["planner.controlled-language.ste-conformance"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        author, "review_authored_document",
        lambda *a, **k: [_FINDING], raising=False,
    )

    dest = tmp_path / "plan" / "demo" / "E001.yaml"

    with pytest.raises(author.ArtifactReviewError) as excinfo:
        author._write_yaml(dest, {"urn": "wmbt:demo:E001", "statement": "utilise a widget"},
                           artifact_kind="wmbt")

    # Nothing reached the canonical path — a refused write leaves no artifact behind.
    assert not dest.exists()
    # The findings ride on the error, so the agent can correct and re-run.
    assert excinfo.value.findings == [_FINDING]

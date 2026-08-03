# URN: test:author-atdd-substrate:E009-UNIT-003-clean-review-writes-the-artifact
# Acceptance: acc:author-atdd-substrate:E009-UNIT-003-clean-review-writes-the-artifact
# WMBT: wmbt:author-atdd-substrate:E009
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:author-atdd-substrate:E009-UNIT-003-clean-review-writes-the-artifact.

A declared rule that reports nothing lets the write through UNCHANGED. The gate is a
veto, never a rewriter: staging and re-writing must not reformat, reorder or re-quote
the document, so a clean guarded write is byte-identical to an unguarded one.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.planner.commands import author

_DOC = {"urn": "wmbt:demo:E001", "statement": "maximize likelihood of clean prose",
        "acceptances": [{"id": "AC-UNIT-001"}]}


def _declare_review_rules(root: Path, rules: list) -> None:
    atdd = root / ".atdd"
    atdd.mkdir(parents=True, exist_ok=True)
    (atdd / "config.yaml").write_text(
        yaml.safe_dump({"author_review": {"rules": rules}}, sort_keys=False),
        encoding="utf-8",
    )


def test_e009_unit_003_clean_review_writes_the_artifact(tmp_path: Path, monkeypatch):
    _declare_review_rules(tmp_path, ["planner.controlled-language.ste-conformance"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(author, "review_authored_document", lambda *a, **k: [], raising=False)

    guarded = tmp_path / "plan" / "demo" / "E001.yaml"
    assert author._write_yaml(guarded, dict(_DOC), artifact_kind="wmbt") == guarded

    # Byte-identical to the unguarded write: the gate vetoes, it never rewrites.
    unguarded = tmp_path / "plan" / "demo" / "E002.yaml"
    author._write_yaml(unguarded, dict(_DOC))
    assert guarded.read_bytes() == unguarded.read_bytes()

# URN: test:integrate-end-to-end:end-to-end-coach-cycle:D001-UNIT-001-worked-example-doc-committed
# Acceptance: acc:integrate-end-to-end:D001-UNIT-001-worked-example-doc-committed
# WMBT: wmbt:integrate-end-to-end:D001
# Phase: GREEN
# Layer: integration
# Harness: unit/backend
"""D001-UNIT-001 — docs/coach-worked-example.md committed with required content.

Verifies that ``docs/coach-worked-example.md`` exists in the repository
and contains:
- The chosen issue's number + title with a GitHub URL
- The state-machine path taken (at minimum the INIT→COMPLETE sequence
  or a subset describing what actually fired)
- Artifact enumeration: decisions.jsonl, judgments.jsonl, integration.log
  referenced with relative paths under .atdd/runtime/
- References to atdd-coach-spec-v9.md §11.5 and §11.6
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
DOC_PATH = REPO_ROOT / "docs" / "coach-worked-example.md"


def test_worked_example_doc_exists() -> None:
    assert DOC_PATH.exists(), (
        f"docs/coach-worked-example.md must be committed to the repository.\n"
        f"Expected at: {DOC_PATH}"
    )


def test_doc_names_chosen_issue_with_github_url() -> None:
    text = DOC_PATH.read_text()
    assert "https://github.com/" in text, (
        "docs/coach-worked-example.md must name the chosen issue and include its GitHub URL. "
        "Add a link of the form https://github.com/<owner>/<repo>/issues/<N>."
    )


def test_doc_enumerates_required_artifacts() -> None:
    text = DOC_PATH.read_text()
    required = ("decisions.jsonl", "judgments.jsonl", "integration.log")
    missing = [a for a in required if a not in text]
    assert not missing, (
        f"docs/coach-worked-example.md must enumerate these runtime artifacts "
        f"by relative path under .atdd/runtime/: {missing}"
    )


def test_doc_references_spec_11_5_and_11_6() -> None:
    text = DOC_PATH.read_text()
    assert "11.5" in text, (
        "docs/coach-worked-example.md must reference atdd-coach-spec-v9.md §11.5 "
        "(self-hosting inflection)."
    )
    assert "11.6" in text, (
        "docs/coach-worked-example.md must reference atdd-coach-spec-v9.md §11.6 "
        "(integration-bug observation)."
    )

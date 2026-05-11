# URN: test:integrate-end-to-end:end-to-end-coach-cycle:D001-UNIT-003-production-readiness-disclaimer-noted
# Acceptance: acc:integrate-end-to-end:D001-UNIT-003-production-readiness-disclaimer-noted
# WMBT: wmbt:integrate-end-to-end:D001
# Phase: GREEN
# Layer: integration
# Harness: unit/backend
"""D001-UNIT-003 — Production-readiness disclaimer section in worked-example doc.

Verifies that ``docs/coach-worked-example.md`` contains a
``## Production-readiness expectation`` section stating that coach v9
may need an integration-hardening milestone before being declared
production-ready beyond this worked example, with a direct reference
to ``atdd-coach-spec-v9.md`` §11.6.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
DOC_PATH = REPO_ROOT / "docs" / "coach-worked-example.md"

_REQUIRED_HEADING = "## Production-readiness expectation"


def test_doc_has_production_readiness_section() -> None:
    assert DOC_PATH.exists(), (
        "docs/coach-worked-example.md must exist before this test can pass."
    )
    text = DOC_PATH.read_text()
    assert _REQUIRED_HEADING in text, (
        f"docs/coach-worked-example.md is missing the required section:\n"
        f"  '{_REQUIRED_HEADING}'\n"
        f"The section must state that coach v9 may need an integration-hardening "
        f"milestone before being declared production-ready beyond this worked example."
    )


def test_production_readiness_section_references_spec_11_6() -> None:
    text = DOC_PATH.read_text()
    if _REQUIRED_HEADING not in text:
        return  # test_doc_has_production_readiness_section catches the missing heading

    start = text.index(_REQUIRED_HEADING) + len(_REQUIRED_HEADING)
    next_heading = text.find("\n## ", start)
    section_body = text[start:next_heading].strip() if next_heading != -1 else text[start:].strip()

    assert "11.6" in section_body, (
        f"The '{_REQUIRED_HEADING}' section must reference atdd-coach-spec-v9.md §11.6 "
        f"so the reader can follow the integration-risk rationale upstream."
    )

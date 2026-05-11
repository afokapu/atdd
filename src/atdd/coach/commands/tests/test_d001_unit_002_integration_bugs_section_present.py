# URN: test:integrate-end-to-end:end-to-end-coach-cycle:D001-UNIT-002-integration-bugs-section-present
# Acceptance: acc:integrate-end-to-end:D001-UNIT-002-integration-bugs-section-present
# WMBT: wmbt:integrate-end-to-end:D001
# Phase: GREEN
# Layer: integration
# Harness: unit/backend
"""D001-UNIT-002 — Integration bugs section present in worked-example doc.

Verifies that ``docs/coach-worked-example.md`` contains an
``## Integration bugs discovered`` section. The section may be empty
(with the literal text "No integration bugs surfaced during the worked
example.") but must not be absent.

Per spec §11.6: an empty inventory is acceptable; a missing section is
not. The structural commitment to surfacing bugs survives even a clean
run.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
DOC_PATH = REPO_ROOT / "docs" / "coach-worked-example.md"

_REQUIRED_HEADING = "## Integration bugs discovered"
_EMPTY_SENTINEL = "No integration bugs surfaced during the worked example."


def test_doc_has_integration_bugs_section() -> None:
    assert DOC_PATH.exists(), (
        "docs/coach-worked-example.md must exist before this test can pass."
    )
    text = DOC_PATH.read_text()
    assert _REQUIRED_HEADING in text, (
        f"docs/coach-worked-example.md is missing the required section:\n"
        f"  '{_REQUIRED_HEADING}'\n"
        f"Either list discovered bugs there, or include the literal text:\n"
        f"  '{_EMPTY_SENTINEL}'\n"
        f"Per acc:integrate-end-to-end:D001-UNIT-002, a missing section fails the acceptance."
    )


def test_integration_bugs_section_has_content_or_sentinel() -> None:
    text = DOC_PATH.read_text()
    if _REQUIRED_HEADING not in text:
        return  # test_doc_has_integration_bugs_section catches this

    # Extract the section body (everything between this heading and the next ##)
    start = text.index(_REQUIRED_HEADING) + len(_REQUIRED_HEADING)
    next_heading = text.find("\n## ", start)
    section_body = text[start:next_heading].strip() if next_heading != -1 else text[start:].strip()

    assert section_body, (
        f"The '{_REQUIRED_HEADING}' section is completely empty.\n"
        f"Either list bugs or include the sentinel text:\n"
        f"  '{_EMPTY_SENTINEL}'"
    )

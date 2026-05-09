# URN: test:freeze-runtime-contracts:runtime-schema-freeze:D004-UNIT-001-event-semantics-doc-complete
# Acceptance: acc:freeze-runtime-contracts:D004-UNIT-001-event-semantics-doc-complete
# WMBT: wmbt:freeze-runtime-contracts:D004
# Phase: RED
# Layer: backend.integration
# Assertion: structural

"""
D004-UNIT-001 — ``src/atdd/coach/schemas/event-semantics.md`` exists and
specifies, for every one of the 12 event types, Producer + Triggering
condition + Idempotency contract + Ordering guarantees + Replay behavior.

The doc is cross-checked against ``runtime-event.schema.json``'s
``event_type`` enum so the two cannot drift.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SCHEMAS_DIR = ATDD_PKG_DIR / "coach" / "schemas"
DOC = SCHEMAS_DIR / "event-semantics.md"
SCHEMA = SCHEMAS_DIR / "runtime-event.schema.json"

# Frozen by spec §C0; D004 context_clarifier enumerates the same 12.
EVENT_TYPES = (
    "agent_spawned",
    "heartbeat",
    "commit_observed",
    "event_emitted",
    "escalation_emitted",
    "pr_opened",
    "pr_closed",
    "validation_pending",
    "validation_complete",
    "review_complete",
    "correction_emitted",
    "process_silence",
)

REQUIRED_SUBSECTION_LABELS = (
    "Producer",
    "Triggering",
    "Idempotency",
    "Ordering",
    "Replay",
)


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert DOC.exists(), (
        f"Missing {DOC}. Acceptance D004-UNIT-001 requires "
        f"event-semantics.md committed at "
        f"src/atdd/coach/schemas/event-semantics.md."
    )
    return DOC.read_text(encoding="utf-8")


def _section_for(event: str, doc_text: str) -> str:
    """Return the section body for ``event``, raising if not found.

    A section starts at a heading line (``#`` or ``##``) that contains
    the event type name (as a code span or bare token) and ends at the
    next same-or-higher-level heading line.
    """
    # Find a heading line that contains the event name. We accept any
    # heading depth from H2..H4 as long as it contains the event token.
    heading_re = re.compile(
        rf"^(#{{2,4}})\s.*\b{re.escape(event)}\b",
        re.MULTILINE,
    )
    m = heading_re.search(doc_text)
    if not m:
        return ""
    start = m.end()
    depth = m.group(1)
    # Next heading at same depth or shallower terminates this section.
    end_re = re.compile(rf"^#{{1,{len(depth)}}}\s", re.MULTILINE)
    e = end_re.search(doc_text, pos=start)
    return doc_text[start: e.start() if e else len(doc_text)]


@pytest.mark.parametrize("event", EVENT_TYPES)
def test_event_has_subsection(event: str, doc_text: str) -> None:
    """Every one of the 12 event types has its own subsection."""
    section = _section_for(event, doc_text)
    assert section, (
        f"event-semantics.md is missing a subsection for {event!r}. "
        f"WMBT D004-UNIT-001 requires per-event-type subsections."
    )


@pytest.mark.parametrize("event", EVENT_TYPES)
def test_event_subsection_specifies_all_five_facets(event: str, doc_text: str) -> None:
    """Producer / Triggering / Idempotency / Ordering / Replay all appear."""
    section = _section_for(event, doc_text)
    if not section:
        pytest.skip(f"section for {event!r} missing — covered by sibling test")
    for label in REQUIRED_SUBSECTION_LABELS:
        assert label in section, (
            f"event-semantics.md: {event!r} subsection is missing "
            f"{label!r}. WMBT D004-UNIT-001 requires all five facets "
            f"(Producer, Triggering, Idempotency, Ordering, Replay) "
            f"per event type."
        )


def test_doc_matches_schema_enumeration() -> None:
    """The 12 event types in event-semantics.md match runtime-event.schema.json's enum."""
    if not SCHEMA.exists():
        pytest.skip("runtime-event.schema.json missing — covered by D001 tests")
    if not DOC.exists():
        pytest.skip("event-semantics.md missing — covered by sibling test")
    with SCHEMA.open() as fh:
        schema = json.load(fh)
    enum = (schema.get("properties", {}).get("event_type") or {}).get("enum") or []
    text = DOC.read_text(encoding="utf-8")
    for e in enum:
        # Each enumerated event type appears at least once in the doc.
        assert e in text, (
            f"event-semantics.md does not document event type {e!r} "
            f"declared by runtime-event.schema.json."
        )
    # And conversely, the doc cannot introduce types not in the schema.
    # We don't enforce a hard equality here because future docs may
    # describe the schema-changing process — the schema enum is the
    # source of truth.
    assert sorted(enum) == sorted(EVENT_TYPES), (
        f"runtime-event.schema.json enum {sorted(enum)} drifted from "
        f"the spec §C0 list {sorted(EVENT_TYPES)}."
    )

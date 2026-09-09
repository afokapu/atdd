# URN: test:project-shared-state:mint-object-identity:Y002-UNIT-003-title-and-body-h1-move-together
# Acceptance: acc:project-shared-state:Y002-UNIT-003-title-and-body-h1-move-together
# WMBT: wmbt:project-shared-state:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A title rename must move data.title and the body's leading H1 together when an H1 exists, must never synthesise one when it does not, and must never mistake a '#' line inside a fenced code block for the heading. Refs #1653, #1654.
"""A title rename cannot mint a title/H1 divergence (Y002-UNIT-003).

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:Y002

The cross-lane interlock with **#1654**, settled by the #1652 orchestrator:

(a) body HAS a leading H1  -> rewrite it in the same write as ``data.title``.
(b) body has NO leading H1 -> write ``data.title`` only; do NOT synthesise one.
(c) ``--slug`` is untouched by any of this — a slug is not duplicated in a body.

Case (b) is the majority, not the edge: of the 822 live work items, **619 carry
no leading H1**, 179 agree with ``data.title``, 24 already disagree. Synthesising
a heading into those 619 bodies would be a corpus migration wearing a rename's
clothes.

The fenced-block case is not hypothetical either. Measured over the same 822
bodies, a naive ``^# `` regex reads a *different* heading than the fence-aware
parser on **78** of them — ATDD issue bodies are full of fenced shell blocks
whose lines begin with ``#``. #1654 was already burned by exactly this.
"""
from __future__ import annotations

from atdd.state.body_heading import first_h1
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.work_item_writer import rename_work_item

from ._helpers import memory_store

BODY_WITH_H1 = """# Old Heading

Some prose.

## A subheading

More prose.
"""

BODY_WITHOUT_H1 = """Some prose with no heading at all.

## Only a subheading

More prose.
"""

#: The trap: the only ``#``-leading lines sit inside fenced code blocks.
BODY_WITH_FENCED_HASHES = """Intro prose, no heading.

```bash
# install the thing
atdd state object rename wi_x --title Y
```

~~~python
# not a heading either
~~~

Closing prose.
"""


def _seed(store, uid, body, title="Old Title"):
    store.objects.upsert(
        uid, WORK_ITEM_KIND, state="INIT",
        data={"slug": "a-slug", "title": title, "body": body, "owner_actor": "dev-a"},
    )


def test_y002_unit_003_title_rename_moves_the_body_h1_with_it() -> None:
    """(a) When the body has a leading H1, title and H1 move together."""
    with memory_store() as (conn, store):
        _seed(store, "unverified:issue-1639", BODY_WITH_H1)

        renamed = rename_work_item(conn, "unverified:issue-1639", title="New Heading")

        assert renamed.data["title"] == "New Heading"
        assert first_h1(renamed.data["body"]) == "New Heading"
        # Only the heading line moved — the rest of the body is byte-identical.
        assert renamed.data["body"].splitlines()[1:] == BODY_WITH_H1.splitlines()[1:]


def test_y002_unit_003_title_rename_never_synthesises_a_missing_h1() -> None:
    """(b) When the body has no H1, the title moves alone and the body is untouched."""
    with memory_store() as (conn, store):
        _seed(store, "backfill-merged-issues-into-store", BODY_WITHOUT_H1)

        renamed = rename_work_item(
            conn, "backfill-merged-issues-into-store", title="New Title",
        )

        assert renamed.data["title"] == "New Title"
        assert renamed.data["body"] == BODY_WITHOUT_H1
        assert first_h1(renamed.data["body"]) is None


def test_y002_unit_003_a_hash_inside_a_fence_is_not_the_heading() -> None:
    """(b) A '#' line inside a fenced block is not an H1, so the body stays untouched."""
    with memory_store() as (conn, store):
        _seed(store, "unverified:issue-287", BODY_WITH_FENCED_HASHES)

        renamed = rename_work_item(conn, "unverified:issue-287", title="New Title")

        assert renamed.data["title"] == "New Title"
        assert renamed.data["body"] == BODY_WITH_FENCED_HASHES
        assert "# install the thing" in renamed.data["body"]
        assert "# not a heading either" in renamed.data["body"]


def test_y002_unit_003_slug_rename_leaves_the_body_alone() -> None:
    """(c) A slug rename is not a title rename — the H1 is not its business."""
    with memory_store() as (conn, store):
        _seed(store, "unverified:issue-1639", BODY_WITH_H1)

        renamed = rename_work_item(conn, "unverified:issue-1639", slug="new-slug")

        assert renamed.data["slug"] == "new-slug"
        assert renamed.data["title"] == "Old Title"
        assert renamed.data["body"] == BODY_WITH_H1
        assert first_h1(renamed.data["body"]) == "Old Heading"

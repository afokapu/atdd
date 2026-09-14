# URN: test:project-shared-state:mint-object-identity:Y002-SMOKE-001-rename-addressability
# Acceptance: acc:project-shared-state:Y002-SMOKE-001-rename-addressability
# WMBT: wmbt:project-shared-state:Y002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state object rename` CLI addresses a work item held under each live slug uid form, exits zero, and moves title and body H1 together. Refs #1653.
"""SMOKE — rename-addressability end-to-end through the real CLI (Y002-SMOKE-001).

wagon: project-shared-state | feature: mint-object-identity | phase: SMOKE
WMBT: wmbt:project-shared-state:Y002

This is the acceptance the issue's Done-when names: *"`atdd state object rename`
succeeds against a live work item."* It drives the installed command surface by
subprocess against a real checkout and a real ``.atdd/state/state.sqlite``.

**Hermetic by construction.** ``_live.atdd_state`` pins ``HOME`` inside
``tmp_path`` and passes ``--root`` at the temp checkout, so this test cannot read
or write the Control Root store at
``/Users/alecfokapu/Github/atdd/.atdd/state/state.sqlite``. That matters beyond
tidiness here: sibling issues #1654 and #1655 are measuring that store, and a
stray write from this test would perturb their baselines mid-flight.

The store is seeded through the same writer the authoring path uses
(``create_work_item``, which keys by slug), so the uids under test are the forms
the live corpus actually holds — not fixtures invented to match the fix.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from typing import Optional

from ._live import atdd_state, make_checkout

_SRC = Path(__file__).resolve().parents[4]

#: One uid of each live form, and the H1-bearing body the rename must carry along.
SEED_UIDS = ("unverified:issue-1639", "store-github-sync-token")
SEED_BODY = "# Old Heading\n\nProse that must survive the rename.\n"

#: Seeds the temp store through the real authoring writer, in the real process
#: the CLI will later open — no manual SQL, no patching.
_SEED = """
import sys
sys.path.insert(0, {src!r})
from atdd.state.db import connect, init_state_store
from atdd.state.work_item_writer import create_work_item

db = init_state_store(start={root!r})
conn = connect(db)
for uid in {uids!r}:
    create_work_item(
        conn, uid, state="INIT",
        data={{"slug": uid, "title": "Old Title", "body": {body!r}, "owner_actor": "dev-a"}},
    )
conn.commit()
"""


def _seed_store(repo: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _SEED.format(
            src=str(_SRC), root=str(repo), uids=SEED_UIDS, body=SEED_BODY)],
        cwd=str(repo), capture_output=True, text=True, timeout=120,
        env={"HOME": str(repo), "CI": "true", "PATH": ""},
    )
    assert result.returncode == 0, result.stderr


def _stored(repo: Path, key: str) -> Optional[dict]:
    """The object *key* addresses, or ``None`` — resolved the way the product resolves.

    ``key`` is a display slug, not a uid: it is what an operator types. Reading with a raw
    ``objects.get`` would assert that the slug is still the primary key, which is the exact
    thing this issue changes. Resolving here is what lets the test tell "renamed" apart from
    "vanished" after the slug moves.
    """
    read = """
import json, sys
sys.path.insert(0, {src!r})
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore
from atdd.state.work_item_writer import resolve_work_item
store = StateStore(connect(init_state_store(start={root!r})))
obj = resolve_work_item(store, {key!r})
print(json.dumps(None if obj is None
                 else {{"uid": obj.uid, "kind": obj.kind, "data": obj.data}}))
"""
    result = subprocess.run(
        [sys.executable, "-c", read.format(src=str(_SRC), root=str(repo), key=key)],
        cwd=str(repo), capture_output=True, text=True, timeout=120,
        env={"HOME": str(repo), "CI": "true", "PATH": ""},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


@pytest.mark.parametrize("uid", SEED_UIDS, ids=["unverified-form", "bare-slug-form"])
def test_y002_smoke_001_rename_addressability(tmp_path, uid) -> None:
    """The real CLI renames a work item held under a live slug uid, and exits zero."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0
    _seed_store(repo)

    # Identity BEFORE the rename, so "identity did not move" can be compared rather
    # than assumed. Under #1622 this is a minted wi_<ULID>, never the seeded slug.
    before = _stored(repo, uid)
    assert before is not None, f"the seeded work item {uid!r} must be addressable by slug"
    identity = before["uid"]

    renamed = atdd_state(
        repo, "object", "rename", uid, "--slug", "new-slug", "--title", "New Heading",
    )

    # The verb that addressed 0 of 822 live objects now exits zero.
    assert renamed.returncode == 0, f"stdout={renamed.stdout!r} stderr={renamed.stderr!r}"
    assert "not a work-item uid" not in renamed.stdout

    # It echoes the IDENTITY and the NEW name — the two strings that still address the
    # object afterwards. It must not echo back the key it was passed: `--slug` retires
    # that name, so returning it would hand the caller a string that no longer resolves.
    assert identity in renamed.stdout
    assert "new-slug" in renamed.stdout

    # Display metadata moved.
    obj = _stored(repo, "new-slug")
    assert obj is not None, "the work item must be addressable by its NEW slug"
    assert obj["kind"] == "work_item"
    assert obj["data"]["slug"] == "new-slug"
    assert obj["data"]["title"] == "New Heading"

    # Identity did not (Y001 still holds) — now a real before/after, not a restatement
    # of the old model in which the slug WAS the uid.
    assert obj["uid"] == identity

    # And the retired name stops addressing it, which is what makes the rename a rename
    # rather than an alias.
    assert _stored(repo, uid) is None

    # The body's H1 moved with the title — the #1654 interlock, end-to-end.
    assert obj["data"]["body"].startswith("# New Heading\n")
    assert "Prose that must survive the rename." in obj["data"]["body"]

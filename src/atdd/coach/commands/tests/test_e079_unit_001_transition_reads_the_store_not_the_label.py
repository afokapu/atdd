# Acceptance: acc:drive-state-machine:Y002-UNIT-003-transition-reads-the-store-not-the-label
"""#2011 — `update()` must derive the current phase from the STORE, not the label.

#1452 made `objects.state` authoritative for the lifecycle after a label race silently
no-opped a transition, and migrated every reader it listed. `IssueManager.update` was not
among them: it derives the phase at `issue.py:1667` through `_read_phase_labels(issue)`, a
pure function over the fetched GitHub payload. That stayed invisible for as long as the two
agreed, which they do whenever a human drives both.

CI is the first actor that can move one without the other. Observed on #1999's own merge:
`atdd auto-phase` ran in GitHub Actions and swapped the label to `atdd:COMPLETE`; it cannot
write a developer's SQLite, so the store stayed at `REFACTOR`. The operator's
`atdd coach transition 1999 COMPLETE` was then refused with *"Cannot transition from
COMPLETE to COMPLETE"* — a refusal that PROVES the label was the input, because the store
said REFACTOR and `REFACTOR->COMPLETE` is legal.

Neither direction could repair it: `update()` refuses because it reads the label it would be
reconciling from, and `reproject_phase_label` (#1338) drives label <- store, so it would have
pushed the CORRECT label back to REFACTOR.

The fix is the shape `auto_phase.resolve_pr_to_transition` already uses —
`current_phase = store_phase or label_phase`. A silent store means "cannot decide", never
"no phase", so an un-imported work item still answers from its label.

Hermetic: its own Control Root and store, `_resolve_issue` stubbed so the label is the only
manipulated variable. No network.

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.coach]

UID = "wi-2011-lab"
NUM = 424242


class _FakeClient:
    """The GitHub surface `_write_phase_label` touches, recording instead of calling."""

    def __init__(self) -> None:
        self.removed: list = []
        self.added: list = []

    def remove_label(self, number: int, labels) -> None:
        self.removed.append((number, list(labels)))

    def add_label(self, number: int, labels) -> None:
        self.added.append((number, list(labels)))


@pytest.fixture()
def control_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="atdd-2011-"))
    (root / ".atdd" / "state").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\ngithub:\n  repo: lab/lab\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _seed(root: Path, phase: Optional[str], *, register: bool = True) -> None:
    """A work item at `phase`, reachable from issue NUM — the merged-issue shape."""
    if not register:
        return
    with open_state_store(control_root=root) as store:
        store.objects.upsert(
            UID, "work_item", state=phase,
            data={
                "title": "lab", "branch": "feat/lab", "type": "feature",
                "train": "train:issue-lifecycle:drive-state-machine",
            },
        )
        store.external_refs.link(UID, "github", "issue", str(NUM))


def _store_phase(root: Path) -> Optional[str]:
    with open_state_store(control_root=root) as store:
        obj = store.objects.get(UID)
        return obj.state if obj else None


def _manager(root: Path, label_phase: str) -> IssueManager:
    """An IssueManager whose ONLY tie to GitHub is the phase its label reports."""
    manager = IssueManager(root)
    issue = {
        "number": NUM, "title": "lab", "body": "x", "state": "OPEN",
        "labels": [{"name": "atdd-issue"}, {"name": f"atdd:{label_phase}"}],
    }
    # `update()` obtains the issue through _resolve_issue, not _fetch_issue.
    manager._resolve_issue = lambda _i: (NUM, issue, _FakeClient())  # noqa: SLF001
    manager._fetch_issue = lambda _n: issue                          # noqa: SLF001
    manager._admit_train = lambda *a, **k: True                      # noqa: SLF001
    # NOT stubbed: _update_manifest_status, which IS the store write this asserts on.
    return manager


def test_a_store_behind_its_label_is_reconciled(control_root: Path) -> None:
    """The #1999 case: CI advanced the label, so the transition must repair the store."""
    _seed(control_root, "REFACTOR")

    rc = _manager(control_root, "COMPLETE").update(issue_id=str(NUM), status="COMPLETE")

    assert rc == 0, (
        "the transition was refused. The store says REFACTOR and REFACTOR->COMPLETE is "
        "legal, so a refusal means the phase was derived from the label — leaving the "
        "store permanently behind, with reproject_phase_label able only to corrupt the "
        "correct label in the other direction."
    )
    assert _store_phase(control_root) == "COMPLETE", (
        f"the command succeeded but the store still reads {_store_phase(control_root)!r}; "
        "a transition that reports success without moving the authoritative record is "
        "worse than the refusal it replaced."
    )


def test_a_stale_forward_label_does_not_advance_the_store(control_root: Path) -> None:
    """The fix must make the store decisive in BOTH directions, not open a bypass."""
    _seed(control_root, "RED")

    rc = _manager(control_root, "REFACTOR").update(issue_id=str(NUM), status="COMPLETE")

    assert rc != 0, (
        "a label claiming REFACTOR bought a COMPLETE the store never reached. The store "
        "is at RED; reading it store-first must refuse this exactly as it refuses any "
        "other skip."
    )
    assert _store_phase(control_root) == "RED"


def test_a_silent_store_still_answers_from_the_label(control_root: Path) -> None:
    """A store that has never seen the issue is silent, not contradictory.

    Asserted on the derivation rather than through `update()`: with no work item there is
    also no train, so the command refuses upstream of the phase question for an unrelated
    reason and could never answer this.
    """
    _seed(control_root, None, register=False)
    manager = _manager(control_root, "GREEN")

    _labels, derived = manager._read_phase_labels(  # noqa: SLF001
        {"labels": [{"name": "atdd-issue"}, {"name": "atdd:GREEN"}]}
    )

    assert derived == "GREEN", (
        f"derived {derived!r} for an issue the store has never seen. A consumer repo and "
        "an un-imported work item must behave exactly as they do today."
    )

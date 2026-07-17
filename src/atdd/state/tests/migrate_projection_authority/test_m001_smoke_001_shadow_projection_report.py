# URN: test:migrate-projection-authority:compare-shadow-projection:M001-SMOKE-001-shadow-projection-report
# Acceptance: acc:migrate-projection-authority:M001-SMOKE-001-shadow-projection-report
# WMBT: wmbt:migrate-projection-authority:M001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state shadow` command, run in a real checkout against a real store and a real committed projection, reports the drift it finds (naming the uid) and EXITS ZERO; and on a clean repo it reports no drift and also exits zero. Refs #1434.
"""SMOKE — the shipped shadow command reports drift and never blocks (M001-SMOKE-001).

wagon: migrate-projection-authority | feature: compare-shadow-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:M001

The claim "non-blocking" is a claim about a **process exit code**, so it is worthless until it is
tested as one. This drives the real command, in a real checkout, against a real store that has been
moved out from under a real committed projection — and asserts the shell sees 0.

It also pins *why shadow mode has to exist at all*, which is easy to miss: `atdd state canonicality`
**cannot see this drift**. Canonicality asks whether the committed projection is the canonical
projection of what it hydrates to — a question about the committed files alone, because CI cannot
read a gitignored developer store. Store-vs-committed divergence is invisible to it, and shadow mode
is the only check that reads the store and can therefore say "your store and your branch disagree"
*before* the projection is regenerated wrong. Two different questions, and the test asserts both
answers rather than assuming they are the same one. Refs #1434 / #1400.
"""
from __future__ import annotations

from ._live import atdd_state, make_checkout


def test_m001_smoke_001_shadow_projection_report(tmp_path) -> None:
    """The real command reports store-vs-branch drift and exits 0 — the drift no gate can see."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "widget", "--owner", "dev-a")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()
    assert atdd_state(repo, "project").returncode == 0

    # Clean: no drift, exit 0.
    clean = atdd_state(repo, "shadow")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "no drift" in clean.stdout

    # Now move the store out from under the committed projection — a real transition, through the
    # real CLI, with the projection left un-regenerated. This is the drift that actually happens:
    # a developer advances a work item and forgets to re-project before pushing.
    assert atdd_state(repo, "object", "rename", uid, "--slug", "widget-renamed").returncode == 0

    drifted = atdd_state(repo, "shadow")
    assert drifted.returncode == 0, (
        "shadow mode MUST exit 0 even when it finds drift — it reports, it does not gate (M001)"
    )
    assert uid in drifted.stdout, drifted.stdout
    assert "slug" in drifted.stdout
    assert "NON-BLOCKING" in drifted.stdout

    # And here is why shadow mode has to exist: the canonicality gate CANNOT SEE this drift. It
    # asks whether the committed projection is the canonical projection of what it hydrates to —
    # a question about the committed files alone, because CI cannot read a developer's store. The
    # branch is perfectly self-consistent and perfectly out of date, and only shadow mode says so.
    blind = atdd_state(repo, "canonicality")
    assert blind.returncode == 0, blind.stdout + blind.stderr
    assert "is canonical" in blind.stdout

    # Regenerating the projection is what resolves it — and shadow mode goes quiet, which is the
    # signal the rollout plan tells the operator to wait for.
    assert atdd_state(repo, "project").returncode == 0
    resolved = atdd_state(repo, "shadow")
    assert resolved.returncode == 0
    assert "no drift" in resolved.stdout

    # The gate that DOES block bites on the drift it CAN see: bytes that are not the canonical
    # output of the round-trip. A human who opens the file and annotates it has hand-authored a
    # DERIVED artifact, and invariant I2 says that is not a thing you may do — the comment survives
    # in the committed bytes and cannot survive project(hydrate(p)), so the two disagree and the
    # gate refuses. This is the division of labour: shadow sees the store, canonicality sees the
    # bytes, and between them nothing gets to be quietly wrong.
    projection = repo / ".atdd" / "state" / "projection" / f"{uid}.yaml"
    projection.write_bytes(b"# hand-edited by a well-meaning human\n" + projection.read_bytes())
    blocked = atdd_state(repo, "canonicality")
    assert blocked.returncode != 0, "the canonicality gate must refuse a hand-authored projection"
    assert "NOT canonical" in blocked.stdout + blocked.stderr

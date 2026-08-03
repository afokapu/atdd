# URN: test:migrate-projection-authority:migrate-store-projection:C002-SMOKE-001-first-committed-projection
# Acceptance: acc:migrate-projection-authority:C002-SMOKE-001-first-committed-projection
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Drive the first committed projection end-to-end through the shipped CLI against a real checkout and a real store — it is produced, it round-trips byte for byte through hydrate and re-projection, and `atdd state cutover` then reports projection-is-shared-state met. Refs #1622.

"""#1622 — the first committed projection, proved through the shipped commands.

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:C002

WHY A UNIT TEST COULD NOT REPLACE THIS

The C002 unit acceptances call ``project``/``hydrate`` in-process against an in-memory store
and a ``tmp_path`` directory. That proves the round trip as a function. It cannot prove the
thing the milestone actually claims: that an operator, running the shipped commands in a real
checkout, ends up with a projection on disk that reproduces itself and a cutover check that
agrees. Those are three different programs — ``atdd state project``, ``atdd state hydrate``,
``atdd state cutover`` — and the guarantee is that they concur.

Round-tripping is what separates shared state from a snapshot. If hydrating the committed
projection and re-projecting yields different bytes, two developers who both hydrate it hold
different truths, and the merge driver is adjudicating between artifacts that never agreed.
So the comparison here is over BYTES ON DISK, read back from the filesystem, not over
in-memory documents that never touched a serializer.

THE DISCRIMINATOR. ``test_the_criterion_is_unmet_before_the_projection_exists`` runs
``atdd state cutover`` BEFORE anything is projected and pins the unmet verdict. Without it,
the met verdict the later test asserts could have come from a check that reports met on an
empty repo — which is exactly the failure the criterion's own implementation warns about
("a check that called that canonical would report M8 complete on a repo that had not
started"). The before-case is what makes the after-case mean something.

HERMETIC, AND THE ISOLATION IS ASSERTED. Same three pins as the E002 smoke — ``--root``,
``HOME`` inside ``tmp_path``, and a ``PYTHONPATH`` naming this working copy — and the live
shared store is digested around the run. This module only reads the live store's *location*;
it never writes there, and the assertion proves it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ._live import atdd_state, make_checkout

pytestmark = [pytest.mark.platform]

_SLUGS = ("alpha-shared-state", "beta-shared-state")


def _projection_dir(root: Path) -> Path:
    from atdd.state.projection import PROJECTION_RELATIVE

    return Path(root) / PROJECTION_RELATIVE


def _bytes_on_disk(directory: Path) -> dict[str, bytes]:
    """Every ``<uid>.yaml`` as raw bytes — the unit CI actually compares."""
    if not directory.is_dir():
        return {}
    return {p.name: p.read_bytes() for p in sorted(directory.glob("*.yaml"))}


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


@pytest.fixture()
def repo(tmp_path) -> Path:
    """A real checkout whose real store was filled through the shipped mint command."""
    root = make_checkout(tmp_path / "checkout")
    for slug in _SLUGS:
        result = atdd_state(
            root, "object", "create", "--slug", slug, "--title", slug.replace("-", " "),
        )
        assert result.returncode == 0, f"could not mint {slug}:\n{result.stderr}"
    return root


class TestTheProjectionIsProducedAndReproducesItself:
    """``project(hydrate(p)) == p``, over bytes, through three separate programs."""

    def test_the_shipped_command_writes_one_document_per_work_item(self, repo):
        result = atdd_state(repo, "project")
        assert result.returncode == 0, f"project failed:\n{result.stderr}"

        written = _bytes_on_disk(_projection_dir(repo))
        assert len(written) == len(_SLUGS), f"expected one document each, got {list(written)}"
        assert all(name.startswith("wi_") for name in written), (
            f"the uid alone names the projection file, got {list(written)}"
        )

    def test_hydrating_and_re_projecting_is_byte_identical(self, repo, tmp_path):
        """The round trip, run as an operator would: three commands, bytes compared.

        The re-projection lands in a SEPARATE directory and is compared against the first,
        so this cannot pass by simply not writing: a command that wrote nothing the second
        time would produce an empty directory and fail the comparison.
        """
        assert atdd_state(repo, "project").returncode == 0
        original = _bytes_on_disk(_projection_dir(repo))
        assert original, "a projection with no files cannot be shared state"

        # A second, empty checkout: hydrate the first one's committed projection into a store
        # that has never seen these objects, then project it back out.
        peer = make_checkout(tmp_path / "peer")
        hydrated = atdd_state(peer, "hydrate", "--from", str(_projection_dir(repo)))
        assert hydrated.returncode == 0, f"hydrate failed:\n{hydrated.stderr}"

        out = peer / "reprojected"
        assert atdd_state(peer, "project", "--out", str(out)).returncode == 0
        assert _bytes_on_disk(out) == original, (
            "re-projection did not reproduce the committed bytes — the projection is a "
            "snapshot, not shared state, and two peers hydrating it hold different truths"
        )

    def test_the_digest_survives_the_round_trip(self, repo, tmp_path):
        """The stamp CI compares must not move across hydrate + re-project."""
        assert atdd_state(repo, "project").returncode == 0
        first = atdd_state(repo, "digest", "--from", str(_projection_dir(repo)))
        assert first.returncode == 0, first.stderr

        peer = make_checkout(tmp_path / "peer")
        assert atdd_state(peer, "hydrate", "--from", str(_projection_dir(repo))).returncode == 0
        out = peer / "reprojected"
        assert atdd_state(peer, "project", "--out", str(out)).returncode == 0

        second = atdd_state(peer, "digest", "--from", str(out))
        assert second.returncode == 0, second.stderr
        assert second.stdout.strip() == first.stdout.strip(), (
            f"the projection digest moved across the round trip:\n"
            f"  before {first.stdout.strip()}\n  after  {second.stdout.strip()}"
        )

    def test_the_canonicality_gate_agrees(self, repo):
        """The blocking CI gate, run against the projection the CLI just produced."""
        assert atdd_state(repo, "project").returncode == 0

        result = atdd_state(repo, "canonicality", "--from", str(_projection_dir(repo)))
        assert result.returncode == 0, (
            f"the canonicality gate refuses the projection the CLI produced:\n{result.stdout}"
        )


class TestTheCutoverCriterionTurnsOver:
    """M8's own exit test is the thing that decides the migration finished."""

    def test_the_criterion_is_unmet_before_the_projection_exists(self, repo):
        """The discriminator: without this, "met" could mean the check is vacuous."""
        result = atdd_state(repo, "cutover")

        assert result.returncode != 0, "a repo with no projection has not finished M8"
        report = result.stdout + result.stderr
        assert "projection-is-shared-state" in report
        assert "FAIL" in report, f"the unmet criterion must be named as failing:\n{report}"

    def test_the_criterion_reports_met_once_the_projection_is_committed(self, repo):
        """The verdict CORE-036 exists to turn over."""
        assert atdd_state(repo, "project").returncode == 0

        result = atdd_state(repo, "cutover")
        report = result.stdout + result.stderr
        assert "projection-is-shared-state" in report
        assert "[PASS] projection-is-shared-state" in report, (
            f"the criterion is still unmet after projecting:\n{report}"
        )


class TestTheSharedStoreIsNeverTouched:
    """This module reads the live store's location. It must never write there."""

    def test_a_full_project_run_leaves_the_live_store_byte_identical(self, repo):
        from atdd.state.db import STATE_STORE_RELATIVE
        from atdd.state.paths import resolve_control_root

        live = (
            resolve_control_root(Path(__file__).resolve().parent).control_root
            / STATE_STORE_RELATIVE
        )
        before = _digest(live)

        assert atdd_state(repo, "project").returncode == 0
        assert _bytes_on_disk(_projection_dir(repo)), "the run must really have written"

        assert _digest(live) == before, (
            f"the live shared store at {live} changed during the test run"
        )

    def test_the_projection_is_written_inside_the_tmp_root(self, repo, tmp_path):
        assert atdd_state(repo, "project").returncode == 0

        written = _projection_dir(repo).resolve()
        assert tmp_path.resolve() in written.parents, (
            f"the CLI wrote its projection to {written}, outside the test's tmp root"
        )

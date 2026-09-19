# URN: test:migrate-projection-authority:migrate-store-projection:C002-UNIT-004-the-criterion-reads-head
# Acceptance: acc:migrate-projection-authority:C002-UNIT-004-the-criterion-reads-head
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The projection-is-shared-state criterion judges the projection AT HEAD, byte for byte, and cannot be satisfied by an uncommitted directory by default or through --from. Refs #2024.
"""The cutover criterion reads HEAD, not the working tree (C002-UNIT-004).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C002

The criterion stamps this claim on its verdict:

    "the committed projection is the shared source of truth: project(hydrate(p)) == p,
     byte for byte, over the projection at HEAD"

and then globs the filesystem. So 3/3 can flip before a single byte is committed — the gate that
exists to prove the cutover happened will certify that it did when it did not.

Two further routes have to close with it, or the fix is cosmetic. ``--from`` forwards any
directory straight through, so a canonical tree outside the repository still earns a pass. And
"byte for byte" has to mean bytes: the only git reader available decodes blobs in **text mode**,
which normalises CRLF to LF — so a CRLF-corrupted commit, which is precisely what the projector
would never emit, compares equal to canonical output and passes. Refs #2024.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state import cutover
from atdd.state.projection import PROJECTION_RELATIVE

from atdd.state.projection import canonical_bytes

from atdd.state.tests._fixtures import checkout, commit_all, git
from ._helpers import UID_A, seed_disk_work_items

CRITERION = "projection-is-shared-state"

#: One projectable work item, in the shape the contract admits.
_DOC = {
    "uid": UID_A, "slug": "alpha", "owner_actor": "dev-a",
    "phase": "PLANNED", "state": "ACTIVE", "wmbts": [],
}
#: Its canonical bytes — what ``project()`` would emit for it.
_CANONICAL = canonical_bytes(_DOC)


def _verdict(root: Path, **kwargs) -> cutover.Criterion:
    report = cutover.check(root, **kwargs)
    return next(c for c in report.criteria if c.name == CRITERION)


def _repo(tmp_path: Path) -> Path:
    """A Control Root whose ON-DISK store holds the object the projection describes.

    The store is part of the given now: since #2042 the criterion compares the committed
    projection against the store of that control root, so a repo with a projection and no
    store describes objects nothing holds. These cases are about *which commit* the verdict
    reads, and the store keeps that the only thing under test.
    """
    repo = checkout(tmp_path / "repo", gitignore="")
    seed_disk_work_items(repo, [(UID_A, "PLANNED")])
    return repo


def _write(repo: Path, blob: bytes, *, into: Path | None = None) -> Path:
    directory = Path(into) if into is not None else repo / PROJECTION_RELATIVE
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{UID_A}.yaml").write_bytes(blob)
    return directory


def test_an_uncommitted_projection_does_not_satisfy_the_criterion(tmp_path: Path) -> None:
    """The defect: files on disk that no commit contains must not earn a verdict of met.

    RED: ``_projection_criterion`` globs the working tree, so it does.
    """
    repo = _repo(tmp_path)
    _write(repo, _CANONICAL)  # written, deliberately NOT committed

    assert not _verdict(repo).met, (
        "the criterion reported met over a projection that exists only in the working tree, "
        "while claiming to judge 'the projection at HEAD'"
    )


def test_committing_the_same_bytes_flips_it(tmp_path: Path) -> None:
    """The other half: the fix must not simply make the criterion unsatisfiable."""
    repo = _repo(tmp_path)
    _write(repo, _CANONICAL)
    commit_all(repo, "commit the projection")

    assert _verdict(repo).met, (
        "the criterion refused a projection that IS committed at HEAD; the fix must tighten "
        "the check, not break the passing case"
    )


def test_the_verdict_follows_head_not_the_working_tree(tmp_path: Path) -> None:
    """The sharpest form of the defect, in the direction the other tests cannot reach.

    Commit a canonical projection, then corrupt the file in the working tree. HEAD is still
    canonical, so the criterion — which claims to judge "the projection at HEAD" — must still
    report met.

    RED: it globs the working tree, sees the corruption, and reports unmet. Together with
    ``test_an_uncommitted_projection_does_not_satisfy_the_criterion`` this pins the verdict to
    HEAD in both directions, so an implementation cannot satisfy one by breaking the other.
    """
    repo = _repo(tmp_path)
    _write(repo, _CANONICAL)
    commit_all(repo, "commit a canonical projection")
    (repo / PROJECTION_RELATIVE / f"{UID_A}.yaml").write_bytes(b"corrupted in the working tree\n")

    assert _verdict(repo).met, (
        "HEAD carries a canonical projection and only the working-tree copy was corrupted, "
        "yet the criterion reported unmet — it is reading the working tree, not HEAD"
    )


def test_a_crlf_projection_is_not_canonical(tmp_path: Path) -> None:
    """"Byte for byte" has to mean bytes.

    RED: reading HEAD through a text-mode pipe normalises ``\\r\\n`` to ``\\n``, so a commit the
    projector would never produce compares equal to canonical output and passes.
    """
    repo = _repo(tmp_path)
    git(repo, "config", "core.autocrlf", "false")
    _write(repo, _CANONICAL.replace(b"\n", b"\r\n"))
    commit_all(repo, "commit a CRLF projection")

    assert not _verdict(repo).met, (
        "a projection committed with CRLF line endings is not what project() emits, so it is "
        "not canonical — the criterion reported met, which is a false pass on the gate"
    )


def test_non_utf8_bytes_yield_a_verdict_not_an_exception(tmp_path: Path) -> None:
    """A corrupt projection is an unmet criterion, not a crash."""
    repo = _repo(tmp_path)
    _write(repo, b"uid: " + UID_A.encode() + b"\nslug: \xff\xfe\n")
    commit_all(repo, "commit a non-utf8 projection")

    assert not _verdict(repo).met


def test_a_repository_with_no_commits_yields_a_verdict(tmp_path: Path) -> None:
    """A commit-less checkout is a legitimate cold start, not an error."""
    repo = _repo(tmp_path)
    git(repo, "update-ref", "-d", "refs/heads/main")

    assert not _verdict(repo).met


def test_from_cannot_pass_a_directory_outside_the_worktree(tmp_path: Path) -> None:
    """Fixing the default path is not enough while ``--from`` forwards anything.

    RED: a canonical projection written OUTSIDE the repository earns a met verdict.
    """
    repo = _repo(tmp_path)
    elsewhere = tmp_path / "outside-the-repo"
    _write(repo, _CANONICAL, into=elsewhere)

    assert not _verdict(repo, projection_dir=elsewhere).met, (
        f"{elsewhere} is outside the repository and has never been committed, yet --from "
        "earned a met verdict under a claim that reads 'at HEAD'"
    )


def test_from_cannot_pass_an_uncommitted_directory_inside_the_worktree(tmp_path: Path) -> None:
    """Containment is not the property under test — HEAD resolution is.

    An implementation that merely constrains ``--from`` to paths inside the worktree would
    satisfy the outside-the-worktree case above while still reading an uncommitted in-repo
    directory. That is the same bypass wearing a different hat, so it gets its own acceptance.
    """
    repo = _repo(tmp_path)
    inside = repo / "scratch-projection"
    _write(repo, _CANONICAL, into=inside)  # inside the worktree, never committed

    assert inside.is_relative_to(repo), "fixture error: the directory must be inside the worktree"
    assert not _verdict(repo, projection_dir=inside).met, (
        f"{inside} is inside the worktree but has never been committed, and --from earned a "
        "met verdict; constraining --from to the worktree does not close the bypass — only "
        "resolving the projection at HEAD does"
    )

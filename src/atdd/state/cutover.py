"""The M8 exit criteria, as a command (#1400 migrate-projection-authority, K001).

Spec §14, M8: *projection becomes the shared state; GitHub is an optional mirror; legacy manifest
no longer acts as fallback SoT.* Three sentences. This module is the check that they are true, and
it exists because a milestone whose exit criteria live only in a document is a milestone that gets
declared done by whoever is tired first.

Each criterion delegates to the guard that owns it — there is no second implementation here, and
that is deliberate: a cutover check that re-derived "is the manifest still read?" with its own
private logic could pass while the real gate failed.

===================================  =======================================================
:data:`CRITERION_PROJECTION`         the committed projection round-trips
                                     (:mod:`atdd.state.projection` — ``project(hydrate(p)) == p``)
:data:`CRITERION_NO_HOT_PATH_READ`   no lifecycle decision calls GitHub
                                     (:mod:`atdd.state.hot_path`)
:data:`CRITERION_NO_MANIFEST_READ`   no core reader consults the manifest
                                     (:mod:`atdd.state.manifest_fallback`)
===================================  =======================================================

The check fails while **any one** is unmet, and it names which — an operator staring at a red
cutover needs the criterion, not a boolean. It is deliberately *not* satisfied by "the manifest
file is gone": deleting the file while the readers survive is how you get a tool that works
perfectly until the first developer who still has one.

Dependency discipline: stdlib + ``atdd.state``. No provider (I7).
"""
from __future__ import annotations

import logging
import tempfile

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from atdd.state import gitstore, hot_path, manifest_fallback, projection
from atdd.state.projection import (
    PROJECTION_RELATIVE,
    ProjectionError,
    check_canonicality,
)

_log = logging.getLogger(__name__)

CRITERION_PROJECTION = "projection-is-shared-state"
CRITERION_NO_HOT_PATH_READ = "github-is-optional-mirror"
CRITERION_NO_MANIFEST_READ = "manifest-is-not-a-fallback"

#: The three, in the order §14 states them.
CRITERIA = (CRITERION_PROJECTION, CRITERION_NO_HOT_PATH_READ, CRITERION_NO_MANIFEST_READ)

#: What each criterion claims, quoted back to the operator when it fails.
CLAIMS = {
    CRITERION_PROJECTION:
        "the committed projection is the shared source of truth: project(hydrate(p)) == p, "
        "byte for byte, over the projection at HEAD",
    CRITERION_NO_HOT_PATH_READ:
        "GitHub is an optional mirror: no core lifecycle decision, validator, or gate calls the "
        "GitHub API (spec §12 non-goal 2, invariant I7)",
    CRITERION_NO_MANIFEST_READ:
        "the legacy manifest no longer acts as a fallback source of truth: no core reader opens, "
        "globs, or parses .atdd/manifest.yaml for lifecycle state",
}


@dataclass(frozen=True)
class Criterion:
    """One M8 exit criterion and its verdict."""

    name: str
    met: bool
    claim: str
    #: What is standing in the way. Empty when met.
    blockers: List[str] = field(default_factory=list)

    def render(self) -> str:
        mark = "PASS" if self.met else "FAIL"
        lines = [f"  [{mark}] {self.name} — {self.claim}"]
        lines.extend(f"         {blocker}" for blocker in self.blockers[:_MAX_BLOCKERS])
        if len(self.blockers) > _MAX_BLOCKERS:
            lines.append(f"         … and {len(self.blockers) - _MAX_BLOCKERS} more")
        return "\n".join(lines)


#: How many blockers a failing criterion prints before it summarises. A cutover check that dumps
#: 400 lines is a cutover check nobody reads — but it says how many it withheld (never silently).
_MAX_BLOCKERS = 10


@dataclass(frozen=True)
class CutoverReport:
    """Whether M8 is done. It is done when all three criteria are met, and not before."""

    criteria: List[Criterion] = field(default_factory=list)

    @property
    def met(self) -> bool:
        return all(criterion.met for criterion in self.criteria)

    @property
    def unmet(self) -> List[Criterion]:
        return [criterion for criterion in self.criteria if not criterion.met]

    @property
    def exit_code(self) -> int:
        return 0 if self.met else 1

    def render(self) -> str:
        header = (
            "M8 cutover: COMPLETE — all 3 exit criteria met"
            if self.met else
            f"M8 cutover: NOT COMPLETE — {len(self.unmet)}/{len(self.criteria)} exit "
            f"criteri{'on is' if len(self.unmet) == 1 else 'a are'} unmet"
        )
        return "\n".join([header, *(criterion.render() for criterion in self.criteria)])


def _committed_prefix(root: Path, projection_dir: Optional[Path]) -> Optional[str]:
    """The repo-relative prefix to judge at HEAD, or ``None`` if there cannot be one.

    ``--from`` names a directory, and an operator may legitimately point the check at a
    projection kept somewhere other than the default. What it must **not** do is turn the
    check into a working-tree read: a directory outside the repository has no commit behind
    it at all, so there is nothing at HEAD to judge and the answer is `unmet`, not `met`.

    Containment is not the property either — a directory *inside* the worktree that has never
    been committed also yields nothing at HEAD, and falls out of this for free: its prefix
    simply is not in the tree (#2024).
    """
    if projection_dir is None:
        return PROJECTION_RELATIVE.as_posix()
    try:
        return Path(projection_dir).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        # Observably react, do not merely return (coder.logging.coach-silent-swallow). The
        # criterion below renders this as a blocker the operator reads, but someone watching
        # logs while a cutover refuses would otherwise never learn that --from was the reason.
        _log.warning(
            "the projection directory is outside the repository, so nothing at HEAD can "
            "contain it",
            extra={"root": str(root), "projection_dir": str(projection_dir)},
        )
        return None


def _canonicality_over(committed: dict, root: Path, prefix: str) -> Criterion:
    """Run the round-trip over blobs read from git, written out verbatim.

    The blobs are staged into a scratch directory rather than parsed in memory so the
    existing ``check_canonicality`` runs unchanged — and written as **bytes**, because the
    claim is byte-for-byte and a text round-trip would normalise exactly the corruption the
    check exists to catch.

    A committed projection that cannot be hydrated at all is *unmet*, not a crash: an
    operator running the cutover gate needs the criterion and the offending file, not a
    traceback out of the YAML parser.
    """
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch)
        for filename, blob in committed.items():
            (staged / filename).write_bytes(blob)
        try:
            report = check_canonicality(staged)
        except (ProjectionError, UnicodeDecodeError, yaml.YAMLError) as exc:
            _log.warning(
                "the committed projection could not be hydrated",
                extra={"root": str(root), "prefix": prefix, "error": str(exc)},
            )
            return Criterion(
                CRITERION_PROJECTION, False, CLAIMS[CRITERION_PROJECTION],
                [f"the projection at HEAD cannot be hydrated, so it cannot be canonical: {exc}"],
            )
    return Criterion(
        CRITERION_PROJECTION, report.ok, CLAIMS[CRITERION_PROJECTION],
        [f"{m.filename} is not the canonical projection of what it hydrates to"
         for m in report.mismatches],
    )


def _projection_criterion(root: Path, projection_dir: Optional[Path]) -> Criterion:
    """The projection round-trips **at HEAD** — the property the blocking gate enforces.

    Read out of git, never off the working tree. The claim this criterion stamps has always
    said "over the projection at HEAD"; it globbed the filesystem instead, so 3/3 could flip
    before a single byte was committed and the gate that exists to prove the cutover happened
    would certify that it had when it had not (#2024).

    An **empty** projection does not pass. A repo with no projection at HEAD has not made the
    projection its shared state; it has made nothing its shared state, and a check that called
    that "canonical" would report M8 complete on a repo that had not started.
    """
    root = Path(root)
    prefix = _committed_prefix(root, projection_dir)
    if prefix is None:
        return Criterion(
            CRITERION_PROJECTION, False, CLAIMS[CRITERION_PROJECTION],
            [f"{projection_dir} is outside {root}, so no commit can contain it — there is "
             "nothing at HEAD to judge"],
        )
    try:
        committed = gitstore.projection_bytes_at(root, "HEAD", prefix)
    except gitstore.GitError as exc:
        _log.warning(
            "the projection at HEAD could not be read",
            extra={"root": str(root), "prefix": prefix, "error": str(exc)},
        )
        return Criterion(
            CRITERION_PROJECTION, False, CLAIMS[CRITERION_PROJECTION],
            [f"the projection at HEAD could not be read: {exc}"],
        )
    if not committed:
        return Criterion(
            CRITERION_PROJECTION, False, CLAIMS[CRITERION_PROJECTION],
            [f"no committed projection at {prefix} in HEAD — the shared state does not exist "
             "yet (files in the working tree do not count; they are not what anyone else gets)"],
        )
    identity = _canonicality_over(committed, root, prefix)
    coverage = _coverage_blockers(root, committed)
    if coverage:
        return Criterion(
            CRITERION_PROJECTION, False, CLAIMS[CRITERION_PROJECTION],
            list(identity.blockers) + coverage,
        )
    return identity


def _coverage_blockers(root: Path, committed: Dict[str, bytes]) -> List[str]:
    """Why the committed projection does not cover the store — ``[]`` when it does (#2042).

    The other half of this criterion's claim, and the half nothing checked. Byte-identity
    compares HEAD against a projection of the same snapshot, so both sides descend from one
    ``build_document`` call; self-canonicality compares the projection to itself. Neither can
    see what is ABSENT. Measured before this existed: a projection with a third of its
    documents deleted passed both and the cutover reported MET.

    The store is the other population, and it is read here rather than re-projected — a check
    that rebuilt the projection from the store would compare the store to itself, which is the
    same defect one layer out.

    **An absent store is a blocker, not a pass.** The claim being stamped is that the committed
    projection is the shared source of truth *for this control root*; with no store, that claim
    is unproven rather than true, and a check that called it proven would be the vacuous pass
    this whole criterion exists to remove. It is the distinction ``MissingProjectionError``
    draws on the other side: "there is nothing here" and "what is here is empty" are different
    facts and must not collapse.

    Note this is operator-side by construction. The store is gitignored under the scoped-truth
    rule, so CI has no population to compare against and does not run this command.
    """
    # Imported here, not at module scope: `cutover` is imported by the CLI on every
    # invocation and most of them never open a store, so the SQLite work is deferred to the
    # one path that needs it — the deferred-import shape this layer already keeps.
    from atdd.state.db import STATE_STORE_RELATIVE, connect
    from atdd.state.store import StateStore

    store_path = Path(root) / STATE_STORE_RELATIVE
    if not store_path.is_file():
        return [
            f"there is no store at {store_path} to compare the committed projection against, "
            "so its coverage of this control root is unproven — not proven empty"
        ]

    uids = [name[: -len(projection.PROJECTION_SUFFIX)] for name in committed]
    try:
        conn = connect(store_path)
        try:
            report = projection.check_coverage(uids, StateStore(conn))
        finally:
            conn.close()
    except Exception as exc:  # a verdict, never a traceback at the gate
        _log.warning(
            "projection coverage could not be established",
            extra={"root": str(root), "error": str(exc)},
        )
        return [f"the store could not be read to check coverage: {exc}"]
    return report.blockers()


def _hot_path_criterion(package: Optional[Path]) -> Criterion:
    offenders = hot_path.offenders(package)
    return Criterion(
        CRITERION_NO_HOT_PATH_READ, not offenders, CLAIMS[CRITERION_NO_HOT_PATH_READ], offenders,
    )


def _manifest_criterion(package: Optional[Path]) -> Criterion:
    offenders = manifest_fallback.offenders(package)
    return Criterion(
        CRITERION_NO_MANIFEST_READ, not offenders, CLAIMS[CRITERION_NO_MANIFEST_READ], offenders,
    )


def check(
    root: Path,
    *,
    package: Optional[Path] = None,
    projection_dir: Optional[Path] = None,
) -> CutoverReport:
    """Evaluate all three M8 exit criteria over ``root`` (K001).

    Every criterion is evaluated, always — the check does not stop at the first failure, because
    an operator planning the rest of the cutover needs the whole remaining list, not the first
    item on it.
    """
    report = CutoverReport(criteria=[
        _projection_criterion(Path(root), projection_dir),
        _hot_path_criterion(package),
        _manifest_criterion(package),
    ])
    if not report.met:
        _log.warning(
            "the M8 cutover is not complete",
            extra={"root": str(root),
                "unmet": [criterion.name for criterion in report.unmet]},
        )
    return report


__all__ = [
    "CLAIMS", "CRITERIA", "CRITERION_NO_HOT_PATH_READ", "CRITERION_NO_MANIFEST_READ",
    "CRITERION_PROJECTION", "Criterion", "CutoverReport", "check",
]

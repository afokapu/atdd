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
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from atdd.state import hot_path, manifest_fallback
from atdd.state.projection import PROJECTION_RELATIVE, check_canonicality

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


def _projection_criterion(root: Path, projection_dir: Optional[Path]) -> Criterion:
    """The projection round-trips — the property the blocking canonicality gate enforces.

    An **empty** projection does not pass. A repo with no projection files has not made the
    projection its shared state; it has made nothing its shared state, and a check that called
    that "canonical" would report M8 complete on a repo that had not started.
    """
    directory = Path(projection_dir) if projection_dir is not None else Path(root) / PROJECTION_RELATIVE
    if not directory.is_dir() or not any(directory.glob("*.yaml")):
        return Criterion(
            CRITERION_PROJECTION, False, CLAIMS[CRITERION_PROJECTION],
            [f"no committed projection at {directory} — the shared state does not exist yet"],
        )
    report = check_canonicality(directory)
    return Criterion(
        CRITERION_PROJECTION, report.ok, CLAIMS[CRITERION_PROJECTION],
        [f"{m.filename} is not the canonical projection of what it hydrates to"
         for m in report.mismatches],
    )


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

"""The trailer/projection cross-check (#1400 enforce-merge-authority).

Trailers make git history an event log; the projection is the state that log claims to
describe. When the two disagree, the log has quietly stopped being an audit trail — and
a wrong audit trail is worse than none, because it is *believed*. This module binds them
(spec §5 rules 1–4, 6–7):

1. a projection object diff must carry an ``ATDD-Object`` trailer;
2. a phase diff must carry an ``ATDD-Transition`` trailer, and it must name the phases
   the diff actually moved between;
3. the ``ATDD-Projection-Digest`` trailer must equal the digest of the object the commit
   actually committed;
4. an ``ATDD-Object`` trailer must name an object the commit actually changed;
5. a squash merge is admitted only when its ``ATDD-Summary`` artifact exists and hashes
   to the ``ATDD-Summary-Digest`` it declares.

Every disagreement is reported with the field and **both sides** — "digest mismatch" is
an accusation, "trailer says X, projection says Y" is a diagnosis.

Dependency discipline: stdlib + ``atdd.state`` only.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from atdd.state.evidence import diff_phases
from atdd.state.projection import DIGEST_PREFIX, object_digest
from atdd.state.trailers import SQUASH_MERGE, TrailerBlock

_log = logging.getLogger(__name__)

#: The three fields a trailer group and a projection diff can disagree about.
FIELD_OBJECT = "object"
FIELD_TRANSITION = "transition"
FIELD_DIGEST = "projection_digest"
FIELD_SUMMARY = "summary"


@dataclass(frozen=True)
class Disagreement:
    """One place the trailers and the projection diff tell different stories."""

    uid: Optional[str]
    what: str
    trailer_side: Optional[str]
    projection_side: Optional[str]
    detail: str

    def render(self) -> str:
        where = f"{self.uid}: " if self.uid else ""
        return (
            f"{where}{self.what} disagreement — trailer={self.trailer_side!r}, "
            f"projection={self.projection_side!r}: {self.detail}"
        )


@dataclass(frozen=True)
class CrossCheckReport:
    """The outcome of binding one commit's trailers to the projection diff it carries."""

    checked: int
    disagreements: List[Disagreement] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.disagreements

    def render(self) -> str:
        if self.ok:
            return f"trailers match the projection diff ({self.checked} object(s))"
        lines = [
            f"trailer/projection mismatch ({len(self.disagreements)} disagreement(s), "
            f"{self.checked} object(s)):"
        ]
        lines.extend(f"  - {d.render()}" for d in self.disagreements)
        return "\n".join(lines)


def changed_objects(
    base: Mapping[str, Mapping[str, Any]],
    head: Mapping[str, Mapping[str, Any]],
) -> List[str]:
    """Every uid whose projection document was added, modified, or removed."""
    return sorted(
        uid for uid in set(base) | set(head)
        if base.get(uid) != head.get(uid)
    )


def _phase_change_by_uid(
    base: Mapping[str, Mapping[str, Any]],
    head: Mapping[str, Mapping[str, Any]],
) -> Dict[str, str]:
    """``uid -> "FROM->TO"`` for every object whose phase (or retirement) moved."""
    changes: Dict[str, str] = {}
    for change in diff_phases(base, head):
        if change.before is None:
            continue  # a mint is `∅ -> INIT`; there is no FROM phase to name in a trailer
        changes[change.uid] = f"{change.before}->{change.after}"
    return changes


def file_digest(path: Path) -> str:
    """The ``sha256:<hex>`` digest of a file's bytes — the form every trailer carries."""
    return DIGEST_PREFIX + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cross_check(
    block: TrailerBlock,
    base: Mapping[str, Mapping[str, Any]],
    head: Mapping[str, Mapping[str, Any]],
    *,
    repo_root: Optional[Path] = None,
) -> CrossCheckReport:
    """Bind one commit's trailer group to the projection diff it accompanies (C002)."""
    disagreements: List[Disagreement] = []
    changed = changed_objects(base, head)
    phase_changes = _phase_change_by_uid(base, head)

    # Rule 1: every changed object must be claimed by a trailer.
    for uid in changed:
        group = block.group_for(uid)
        if group is None:
            disagreements.append(Disagreement(
                uid=uid, what=FIELD_OBJECT, trailer_side=None, projection_side=uid,
                detail="the projection object changed but the commit carries no ATDD-Object trailer "
                       "for it",
            ))
            continue

        # Rule 2: a phase diff must be declared, and declared truthfully.
        expected = phase_changes.get(uid)
        if expected is not None and group.transition is None:
            disagreements.append(Disagreement(
                uid=uid, what=FIELD_TRANSITION, trailer_side=None, projection_side=expected,
                detail="the object's phase moved but the commit carries no ATDD-Transition trailer",
            ))
        elif expected is not None and group.transition != expected:
            disagreements.append(Disagreement(
                uid=uid, what=FIELD_TRANSITION, trailer_side=group.transition,
                projection_side=expected,
                detail="the trailer and the projection diff name different transitions",
            ))
        elif expected is None and group.transition is not None:
            disagreements.append(Disagreement(
                uid=uid, what=FIELD_TRANSITION, trailer_side=group.transition,
                projection_side=None,
                detail="the commit claims a transition the projection diff does not show",
            ))

        # Rule 4: the digest trailer must pin the bytes the commit actually committed.
        document = head.get(uid)
        actual = None if document is None else object_digest(document)
        if group.projection_digest is not None and group.projection_digest != actual:
            disagreements.append(Disagreement(
                uid=uid, what=FIELD_DIGEST, trailer_side=group.projection_digest,
                projection_side=actual,
                detail="the ATDD-Projection-Digest trailer does not match the committed projection",
            ))

    # Rule 1, the other direction: a trailer must not claim an object the commit left alone.
    for group in block.groups:
        if group.object_uid not in changed:
            disagreements.append(Disagreement(
                uid=group.object_uid, what=FIELD_OBJECT, trailer_side=group.object_uid,
                projection_side=None,
                detail="the commit claims an ATDD-Object whose projection did not change",
            ))

    # Rules 6–7: a squash merge carries the event semantics in its summary artifact, so
    # the artifact must exist and hash to what the trailer says it does.
    if block.commit_kind == SQUASH_MERGE:
        disagreements.extend(_check_summary(block, repo_root))

    report = CrossCheckReport(checked=len(changed), disagreements=disagreements)
    if not report.ok:
        _log.warning(
            "trailer/projection cross-check failed",
            extra={"objects": len(changed), "disagreements": len(disagreements)},
        )
    return report


def _check_summary(block: TrailerBlock, repo_root: Optional[Path]) -> List[Disagreement]:
    """The squash-merge summary artifact must exist and match its declared digest."""
    if block.summary is None or block.summary_digest is None:
        return [Disagreement(
            uid=None, what=FIELD_SUMMARY, trailer_side=block.summary,
            projection_side=None,
            detail="a squash merge must carry both ATDD-Summary and ATDD-Summary-Digest",
        )]
    if repo_root is None:
        return []  # nothing to resolve the artifact against; the caller opted out
    path = Path(repo_root) / block.summary
    if not path.is_file():
        return [Disagreement(
            uid=None, what=FIELD_SUMMARY, trailer_side=block.summary, projection_side=None,
            detail="the ATDD-Summary artifact named by the commit does not exist",
        )]
    actual = file_digest(path)
    if actual != block.summary_digest:
        return [Disagreement(
            uid=None, what=FIELD_SUMMARY, trailer_side=block.summary_digest,
            projection_side=actual,
            detail=f"the ATDD-Summary artifact {block.summary} does not hash to its declared digest",
        )]
    return []


# --------------------------------------------------------------------------- #
# Field ownership (spec §7.1) — the writer half of the required-check set
# --------------------------------------------------------------------------- #
#: Who may write each projection field (``commons:projection-field-ownership``). The two
#: rules the merge authority can enforce from the committed diff alone are the two that
#: matter most: a human may not write ``external_refs``, and an extension may not write a
#: lifecycle field. The full policy is the ``govern-projection-fields`` wagon's subject;
#: this is the subset the merge-authority run needs today.
LIFECYCLE_FIELDS = ("uid", "phase", "state", "train", "wmbts", "tombstone")
EXTENSION_FIELDS = ("external_refs",)

#: The bot namespace an extension writes under. A core actor is anything else.
EXTENSION_ACTOR_PREFIX = "bot:"


@dataclass(frozen=True)
class OwnershipReport:
    """The outcome of the field-writer check over a projection diff."""

    checked: int
    violations: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.ok:
            return f"every projection field was written by its owner ({self.checked} object(s))"
        lines = [f"field-ownership violation(s) ({len(self.violations)}):"]
        lines.extend(f"  - {violation}" for violation in self.violations)
        return "\n".join(lines)


def check_field_ownership(
    base: Mapping[str, Mapping[str, Any]],
    head: Mapping[str, Mapping[str, Any]],
    *,
    actor: str = "",
) -> OwnershipReport:
    """Refuse a diff whose fields were written by an actor that does not own them (§7.1).

    An extension bot writing a lifecycle field, or a human writing ``external_refs``, is
    the wrong-writer corruption the ownership table exists to prevent — and it is exactly
    the change that *looks* legal to every other check in the set.
    """
    violations: List[str] = []
    is_extension = actor.startswith(EXTENSION_ACTOR_PREFIX)
    for uid in changed_objects(base, head):
        before, after = base.get(uid) or {}, head.get(uid) or {}
        moved = [
            key for key in sorted(set(before) | set(after))
            if before.get(key) != after.get(key)
        ]
        if uid in base and uid not in head:
            violations.append(
                f"{uid}: the projection file was deleted; retirement is a tombstone record, "
                "never a file deletion (spec §10 rule 3)"
            )
            continue
        if before.get("uid") is not None and after.get("uid") != before.get("uid"):
            violations.append(f"{uid}: uid is immutable and was rewritten to {after.get('uid')!r}")
        for key in moved:
            if is_extension and key in LIFECYCLE_FIELDS:
                violations.append(
                    f"{uid}: the extension actor {actor!r} wrote the lifecycle field {key!r}; "
                    "the GitHub mirror is non-authoritative (I7)"
                )
            if not is_extension and key in EXTENSION_FIELDS and actor:
                violations.append(
                    f"{uid}: the core actor {actor!r} wrote {key!r}; only the extension bot may "
                    "write external_refs (spec §7.1)"
                )
    return OwnershipReport(checked=len(changed_objects(base, head)), violations=violations)

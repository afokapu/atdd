"""The ATDD commit-trailer group — git history as a reliable event log (#1400 enforce-merge-authority).

Git history is only an event log if commit metadata is *structured*; free prose is
insufficient (spec §5). This module is the two halves of that contract:

- the **schema** (D001) that pins the canonical trailer group, the value grammar of
  each trailer, and which trailers a given projection diff class must carry;
- the **parser** (E001) that lifts a raw commit message into the schema-typed group,
  handling grouped trailers for a multi-object commit and the ``ATDD-Summary`` form
  for a squash merge, and *refusing* a block that violates the schema rather than
  silently dropping it.

The document shape is the ``commons:projection-trailer`` contract
(``contracts/commons/projection-trailer.schema.json``). As in
:mod:`atdd.state.projection`, the authored schema is the source of truth and the
constants below are its executable form — ``state/tests/enforce_merge_authority``
fails if the two drift. Nothing is vendored under ``state/``
(``coder.state-store.operational-vs-definition-sot``).

Refusal, not tolerance, is the design: a partially-parsed trailer group is worse than
no group at all, because a cross-check run against half a group would report agreement
it never verified. So :func:`parse_trailers` raises and returns nothing.

Dependency discipline: stdlib + ``atdd.state`` only. No provider, no network.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from atdd.state.identity import UID_RE, is_uid
from atdd.state.projection import PHASES

_log = logging.getLogger(__name__)

#: The canonical trailer group (spec §5). A key outside this table is unknown, and an
#: unknown ``ATDD-*`` trailer is a schema violation rather than a harmless extra: the
#: whole point of pinning the group is that a reader can rely on its closure.
TRAILER_KEYS: Tuple[str, ...] = (
    "ATDD-Object",
    "ATDD-Transition",
    "ATDD-Token-Digest",
    "ATDD-Gate",
    "ATDD-Projection-Digest",
    "ATDD-Summary",
    "ATDD-Summary-Digest",
)

#: Trailers that belong to a *group* — the run of trailers describing one object.
GROUP_KEYS: Tuple[str, ...] = (
    "ATDD-Object",
    "ATDD-Transition",
    "ATDD-Token-Digest",
    "ATDD-Gate",
    "ATDD-Projection-Digest",
)

#: Trailers that belong to the *block* — they describe the commit, not an object.
BLOCK_KEYS: Tuple[str, ...] = ("ATDD-Summary", "ATDD-Summary-Digest")

#: Commit kinds (the contract's ``commit_kind`` enum). The kind selects the
#: cardinality rule the block must satisfy (spec §5 rules 6–7).
SINGLE_OBJECT = "single_object"
MULTI_OBJECT = "multi_object"
SQUASH_MERGE = "squash_merge"
NON_PROJECTION = "non_projection"
COMMIT_KINDS: Tuple[str, ...] = (SINGLE_OBJECT, MULTI_OBJECT, SQUASH_MERGE, NON_PROJECTION)

#: The phase vocabulary a transition trailer may name. Wider than the *projection's*
#: phase enum: a commit may record the derived ``SMOKE->COMPLETE`` and the retirement
#: ``->TOMBSTONED``, neither of which a committed projection document may carry.
TRANSITION_PHASES: Tuple[str, ...] = PHASES + ("COMPLETE", "TOMBSTONED")

#: The one digest form the contract admits anywhere. Rule 5 (I8): a raw token, a
#: bearer token, a credential or a private key is never admissible — only a digest.
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: ``PHASE->PHASE``, byte-for-byte the contract's ``ATDD-Transition`` pattern.
TRANSITION_RE = re.compile(r"^[A-Z]+->[A-Z]+$")

#: A gate id, e.g. ``E019`` — the evidence gate a gated transition passed through.
GATE_RE = re.compile(r"^[A-Z]{1,2}[0-9]{3}$")

#: The squash-merge event artifact, byte-for-byte the ``commons:projection-merge-event``
#: ``summary.path`` pattern.
SUMMARY_RE = re.compile(r"^\.atdd/events/.+\.json$")

#: An RFC-822-style trailer line. Matched over the whole message, not only the last
#: paragraph: a grouped multi-object block is readable with blank lines between its
#: groups, and refusing to read one because of a blank line would be a parser bug
#: masquerading as a schema rule.
_TRAILER_LINE_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9-]*):[ \t]*(?P<value>.*?)[ \t]*$")

#: Only ``ATDD-*`` trailers are ours. ``Refs:``, ``Co-authored-by:`` and friends belong
#: to other conventions and are passed over in silence.
_ATDD_PREFIX = "ATDD-"


class TrailerSchemaError(ValueError):
    """A trailer block does not conform to ``commons:projection-trailer`` (D001)."""


class TrailerParseError(ValueError):
    """A commit message's trailer block is malformed and was refused (E001).

    Carries the offending trailer ``keys`` so the operator is told *which* trailer to
    fix, not merely that the commit was refused.
    """

    def __init__(self, problems: List[str], *, keys: Optional[List[str]] = None) -> None:
        self.problems = list(problems)
        self.keys = list(keys or [])
        super().__init__("malformed ATDD trailer block: " + "; ".join(problems))


@dataclass(frozen=True)
class TrailerGroup:
    """One object's trailers — the run beginning at an ``ATDD-Object``."""

    object_uid: str
    transition: Optional[str] = None
    token_digest: Optional[str] = None
    gate: Optional[str] = None
    projection_digest: Optional[str] = None

    @property
    def phases(self) -> Optional[Tuple[str, str]]:
        """``(from, to)`` for the declared transition, or ``None`` when none is declared."""
        if self.transition is None:
            return None
        before, _, after = self.transition.partition("->")
        return before, after

    def as_mapping(self) -> Dict[str, str]:
        """The group as its canonical ``ATDD-*`` mapping (absent trailers omitted)."""
        pairs = (
            ("ATDD-Object", self.object_uid),
            ("ATDD-Transition", self.transition),
            ("ATDD-Token-Digest", self.token_digest),
            ("ATDD-Gate", self.gate),
            ("ATDD-Projection-Digest", self.projection_digest),
        )
        return {key: value for key, value in pairs if value is not None}


@dataclass(frozen=True)
class TrailerBlock:
    """The typed ATDD trailer group lifted out of one commit message."""

    commit_kind: str
    groups: Tuple[TrailerGroup, ...] = ()
    summary: Optional[str] = None
    summary_digest: Optional[str] = None

    @property
    def objects(self) -> Tuple[str, ...]:
        return tuple(group.object_uid for group in self.groups)

    def group_for(self, uid: str) -> Optional[TrailerGroup]:
        """The group naming ``uid``, or ``None`` when the commit does not mention it."""
        for group in self.groups:
            if group.object_uid == uid:
                return group
        return None

    def as_document(self) -> Dict[str, Any]:
        """The block as a ``commons:projection-trailer`` document.

        Deterministic: the same message always yields the same document, so two parses
        of one commit are byte-identical (E001).
        """
        document: Dict[str, Any] = {"commit_kind": self.commit_kind}
        if self.commit_kind == MULTI_OBJECT:
            document["groups"] = [group.as_mapping() for group in self.groups]
        elif self.groups:
            document.update(self.groups[0].as_mapping())
            if self.commit_kind == SQUASH_MERGE and len(self.groups) > 1:
                document["groups"] = [group.as_mapping() for group in self.groups]
        if self.summary is not None:
            document["ATDD-Summary"] = self.summary
        if self.summary_digest is not None:
            document["ATDD-Summary-Digest"] = self.summary_digest
        return document


# --------------------------------------------------------------------------- #
# Schema (D001) — the value grammar of every trailer
# --------------------------------------------------------------------------- #
def _grammar_problem(key: str, value: str) -> Optional[str]:
    """The grammar fault ``value`` carries under ``key``, or ``None`` if it is clean."""
    if key == "ATDD-Object":
        if not is_uid(value):
            return f"ATDD-Object {value!r} is not a work-item uid (expected {UID_RE.pattern})"
        return None
    if key == "ATDD-Transition":
        if not TRANSITION_RE.match(value):
            return f"ATDD-Transition {value!r} is not PHASE->PHASE"
        before, _, after = value.partition("->")
        outside = [p for p in (before, after) if p not in TRANSITION_PHASES]
        if outside:
            return (
                f"ATDD-Transition {value!r} names phase(s) {outside} outside the "
                f"phase-machine vocabulary {list(TRANSITION_PHASES)}"
            )
        return None
    if key in ("ATDD-Token-Digest", "ATDD-Projection-Digest", "ATDD-Summary-Digest"):
        if not DIGEST_RE.match(value):
            # The value is NOT echoed: an ungrammatical digest trailer is exactly where
            # a raw token turns up, and a validator that prints it has leaked it (I8).
            return f"{key} is not a sha256:<hex> digest"
        return None
    if key == "ATDD-Gate":
        if not GATE_RE.match(value):
            return f"ATDD-Gate {value!r} is not a gate id (expected {GATE_RE.pattern})"
        return None
    if key == "ATDD-Summary":
        if not SUMMARY_RE.match(value):
            return f"ATDD-Summary {value!r} is not an .atdd/events/<name>.json artifact path"
        return None
    return None


def validate_trailer_mapping(mapping: Mapping[str, str]) -> None:
    """Refuse ``mapping`` unless every key is pinned and every value is grammatical (D001).

    Raises :class:`TrailerSchemaError` listing *every* problem — an author fixing a
    commit message wants them all at once, not one per amend.
    """
    problems: List[str] = []
    for key, value in mapping.items():
        if not key.startswith(_ATDD_PREFIX):
            continue
        if key not in TRAILER_KEYS:
            problems.append(f"unknown trailer {key!r} (the canonical group is {list(TRAILER_KEYS)})")
            continue
        problem = _grammar_problem(key, str(value))
        if problem is not None:
            problems.append(problem)
    if problems:
        raise TrailerSchemaError("; ".join(problems))


#: Which trailers a projection diff class must carry (spec §5 rules 1–4).
REQUIRED_BY_DIFF_CLASS: Dict[str, Tuple[str, ...]] = {
    # Rule 1 + rule 4: any projection object diff.
    "projection_object": ("ATDD-Object", "ATDD-Projection-Digest"),
    # Rule 2: the diff moves the object's phase.
    "phase": ("ATDD-Object", "ATDD-Transition", "ATDD-Projection-Digest"),
    # Rule 3: the transition passes a gate, so it needs the operator's token digest.
    "gated_transition": (
        "ATDD-Object", "ATDD-Transition", "ATDD-Token-Digest", "ATDD-Gate",
        "ATDD-Projection-Digest",
    ),
    # Rules 6–7: many objects at once, or a squash merge.
    "squash_merge": ("ATDD-Summary", "ATDD-Summary-Digest"),
}


def required_trailers(diff_class: str) -> Tuple[str, ...]:
    """The trailers a ``diff_class`` of projection change is required to carry."""
    if diff_class not in REQUIRED_BY_DIFF_CLASS:
        raise KeyError(f"unknown projection diff class {diff_class!r}")
    return REQUIRED_BY_DIFF_CLASS[diff_class]


# --------------------------------------------------------------------------- #
# Parser (E001) — raw commit message → typed trailer group
# --------------------------------------------------------------------------- #
def _atdd_lines(message: str) -> List[Tuple[str, str]]:
    """Every ``ATDD-*`` trailer in ``message``, in the order it was written."""
    lines: List[Tuple[str, str]] = []
    for raw in message.splitlines():
        match = _TRAILER_LINE_RE.match(raw)
        if match is None:
            continue
        key = match.group("key")
        if key.upper().startswith(_ATDD_PREFIX.upper()):
            lines.append((key, match.group("value")))
    return lines


def _partition(lines: List[Tuple[str, str]], problems: List[str], keys: List[str]) -> Tuple[
    List[Dict[str, str]], Dict[str, str],
]:
    """Split trailers into per-object groups and the block-level (summary) trailers.

    A group *starts* at each ``ATDD-Object``: that is what makes the grouped
    multi-object form (spec §5 rule 6) readable without inventing a delimiter.
    """
    groups: List[Dict[str, str]] = []
    block: Dict[str, str] = {}
    for key, value in lines:
        if key in BLOCK_KEYS:
            if key in block:
                problems.append(f"duplicate {key} trailer")
                keys.append(key)
            block[key] = value
            continue
        if key == "ATDD-Object":
            groups.append({key: value})
            continue
        if key not in TRAILER_KEYS:
            problems.append(f"unknown trailer {key!r} (the canonical group is {list(TRAILER_KEYS)})")
            keys.append(key)
            continue
        if not groups:
            problems.append(f"{key} appears before any ATDD-Object trailer")
            keys.append(key)
            continue
        if key in groups[-1]:
            problems.append(f"duplicate {key} trailer in the group for {groups[-1]['ATDD-Object']}")
            keys.append(key)
            continue
        groups[-1][key] = value
    return groups, block


def _classify(groups: List[Dict[str, str]], block: Dict[str, str]) -> str:
    if "ATDD-Summary" in block or "ATDD-Summary-Digest" in block:
        return SQUASH_MERGE
    if not groups:
        return NON_PROJECTION
    return SINGLE_OBJECT if len(groups) == 1 else MULTI_OBJECT


def _check_cardinality(
    kind: str, groups: List[Dict[str, str]], block: Dict[str, str],
    problems: List[str], keys: List[str],
) -> None:
    """The rules that depend on the *kind* of commit, not on one trailer's grammar."""
    seen: Dict[str, int] = {}
    for group in groups:
        uid = group["ATDD-Object"]
        seen[uid] = seen.get(uid, 0) + 1
    # One object, one group. A repeated uid is two contradictory claims about the same
    # object in one commit — there is no reading of it that makes the event log honest.
    for uid, count in sorted(seen.items()):
        if count > 1:
            problems.append(f"duplicate ATDD-Object trailer: {uid} is claimed by {count} groups")
            keys.append("ATDD-Object")
    if kind == MULTI_OBJECT:
        # Rule 6: grouped trailers must be *complete* groups, or an ATDD-Summary must
        # carry the event instead. A half-filled group is neither.
        for group in groups:
            if "ATDD-Projection-Digest" not in group:
                problems.append(
                    f"grouped commit: the group for {group['ATDD-Object']} carries no "
                    "ATDD-Projection-Digest"
                )
                keys.append("ATDD-Projection-Digest")
    if kind == SQUASH_MERGE:
        for key in ("ATDD-Summary", "ATDD-Summary-Digest"):
            if key not in block:
                problems.append(f"squash merge: no {key} trailer")
                keys.append(key)


def parse_trailers(message: str) -> TrailerBlock:
    """Lift ``message``'s ATDD trailer block into the schema-typed group (E001).

    Deterministic: the same message always yields the same block. Refuses rather than
    degrades — a malformed block raises :class:`TrailerParseError` naming the offending
    trailer key(s) and is never returned half-parsed.
    """
    problems: List[str] = []
    keys: List[str] = []
    lines = _atdd_lines(message)
    groups, block = _partition(lines, problems, keys)
    kind = _classify(groups, block)
    _check_cardinality(kind, groups, block, problems, keys)

    for mapping in (*groups, block):
        try:
            validate_trailer_mapping(mapping)
        except TrailerSchemaError as exc:
            problems.append(str(exc))
            keys.extend(key for key in mapping if key in TRAILER_KEYS and _grammar_problem(
                key, str(mapping[key])) is not None)

    if problems:
        _log.warning(
            "commit trailer block refused",
            extra={"problems": len(problems), "keys": sorted(set(keys))},
        )
        raise TrailerParseError(problems, keys=sorted(set(keys)))

    return TrailerBlock(
        commit_kind=kind,
        groups=tuple(
            TrailerGroup(
                object_uid=group["ATDD-Object"],
                transition=group.get("ATDD-Transition"),
                token_digest=group.get("ATDD-Token-Digest"),
                gate=group.get("ATDD-Gate"),
                projection_digest=group.get("ATDD-Projection-Digest"),
            )
            for group in groups
        ),
        summary=block.get("ATDD-Summary"),
        summary_digest=block.get("ATDD-Summary-Digest"),
    )

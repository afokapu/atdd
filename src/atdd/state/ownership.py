"""Field ownership — the single legal writer of every projection field (#1400 govern-projection-fields).

Same-object corruption has two shapes, and this module is the declaration that tells them
apart (spec §7.1). The first is a *wrong writer*: a human hand-editing ``external_refs``,
or an extension bot moving ``phase``. Both produce a projection that is canonical,
schema-valid, and a lie about who is allowed to say it — every other check in the required
set waves it through. The second is an *unsafe merge*, which
:mod:`atdd.state.merge_driver` handles by reading the same declaration.

The declaration is **data**, not prose (D001):

- ``.atdd/policy/field-ownership.yaml`` is the committed policy — one entry per projection
  field, naming its single legal ``writer`` and its ``rule``, shaped by the authored
  ``commons:projection-field-ownership`` contract.
- :data:`DEFAULT_POLICY` is that file's executable form, so the merge-authority run has a
  table even in a checkout that has not declared one. The two are bound byte-for-byte by
  ``state/tests/govern_projection_fields/test_d001_unit_002_*`` — they cannot drift.

Two vocabularies, deliberately distinct:

**Writers** are *roles* — ``core-lifecycle``, ``extension-bot`` — and they are what the
policy declares. **Actors** are *identities* — the person or bot that made the commit — and
they are what CI resolves from the commit. ``human`` is an actor, never a writer; a policy
that names ``human`` as the writer of ``phase`` is rejected, because "a human wrote it" is
not a statement about which subsystem owns the field (C001).

An unattributed diff (no actor) can carry no wrong-writer claim, so only the writer-
independent rules apply to it: ``uid`` is immutable, and a projection file is never deleted
(retirement is a tombstone record — spec §10 rule 3).

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` only. No provider, and no
lifecycle decision anywhere here reads ``external_refs`` (I7, spec §8.2 rule 5).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

import yaml

from atdd.state.projection import FIELD_TYPES

_log = logging.getLogger(__name__)

#: Where the committed policy lives, relative to the Control Root.
POLICY_RELATIVE = Path(".atdd") / "policy" / "field-ownership.yaml"

# --------------------------------------------------------------------------- #
# The two vocabularies
# --------------------------------------------------------------------------- #
#: The writer roles a field may be owned by. Closed: a policy naming anything else is
#: rejected rather than admitted with an unknown owner nobody can enforce.
WRITER_CORE_CREATE = "core-create"
WRITER_CORE_AUTHORING = "core-authoring"
WRITER_CORE_LIFECYCLE = "core-lifecycle"
WRITER_CORE_TRAIN = "core-train"
WRITER_CORE_TEST = "core-test"
WRITER_EXTENSION_BOT = "extension-bot"

WRITERS: Tuple[str, ...] = (
    WRITER_CORE_CREATE,
    WRITER_CORE_AUTHORING,
    WRITER_CORE_LIFECYCLE,
    WRITER_CORE_TRAIN,
    WRITER_CORE_TEST,
    WRITER_EXTENSION_BOT,
)

#: Every writer but the bot is core. This is the set an attributed core actor may act as.
CORE_WRITERS: FrozenSet[str] = frozenset(WRITERS) - {WRITER_EXTENSION_BOT}

#: The contract's ``writer`` enum spells the roles with underscores; the policy file is
#: written in the contract's spelling so it validates against the authored schema, and the
#: loader normalises to the canonical ids above. One vocabulary in code, one on disk.
WRITER_ALIASES: Dict[str, str] = {
    "core_create": WRITER_CORE_CREATE,
    "core_authoring": WRITER_CORE_AUTHORING,
    "core_lifecycle": WRITER_CORE_LIFECYCLE,
    "core_train_ops": WRITER_CORE_TRAIN,
    "core_test_ops": WRITER_CORE_TEST,
    "extension_bot": WRITER_EXTENSION_BOT,
}

#: The merge rules a field may be governed by (spec §7.1, §7.2). The rule is what the
#: merge driver reads; the writer is what this module reads.
RULE_IMMUTABLE = "immutable"
RULE_MUTABLE = "mutable"
RULE_MONOTONIC_GATED = "monotonic-gated"
RULE_SINGLE_OWNER = "conflict-unless-single-owner"
RULE_SAME_DIGEST = "conflict-unless-same-digest"
RULE_POLICY_MERGE = "policy-merge"
RULE_DERIVED = "derived"
RULE_BOT_ONLY = "bot-only"

MERGE_RULES: Tuple[str, ...] = (
    RULE_IMMUTABLE,
    RULE_MUTABLE,
    RULE_MONOTONIC_GATED,
    RULE_SINGLE_OWNER,
    RULE_SAME_DIGEST,
    RULE_POLICY_MERGE,
    RULE_DERIVED,
    RULE_BOT_ONLY,
)

#: Actor classes. An actor is *who committed*; a writer is *what owns the field*.
ACTOR_CORE = "core"
ACTOR_EXTENSION = "extension-bot"
ACTOR_UNATTRIBUTED = "unattributed"

#: A bot identity, in the three spellings a commit can carry one: the ``bot:`` actor
#: namespace core uses internally, GitHub's ``…[bot]`` author name, and a ``*-bot@`` email.
_BOT_ACTOR_RE = re.compile(r"^bot:|\[bot\]|(?:^|[\s<])[\w.+-]*bot@", re.IGNORECASE)


class OwnershipError(ValueError):
    """A field-ownership policy could not be read or does not conform."""


class PolicyNotFound(OwnershipError):
    """No field-ownership policy is committed (D001).

    Names the path the loader looked at. Deliberately *not* an empty ownership table: a
    table with no entries would admit every writer for every field, which is the exact
    corruption the policy exists to refuse — and it would do it silently.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        super().__init__(
            f"no field-ownership policy at {self.path}: every projection field must resolve "
            "to a declared writer before a diff can be judged (spec §7.1)"
        )


# --------------------------------------------------------------------------- #
# The policy (D001)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FieldOwnership:
    """One field's declared owner and merge rule."""

    field: str
    writer: str
    rule: str
    #: ``False`` for ``external_refs``: lifecycle code may not *read* it (spec §8.2 rule 5).
    lifecycle_readable: bool = True


@dataclass(frozen=True)
class FieldOwnershipPolicy:
    """The whole declaration, indexed by field — what the validator and the driver read."""

    fields: Dict[str, FieldOwnership] = field(default_factory=dict)

    def __contains__(self, name: str) -> bool:
        return name in self.fields

    def owner(self, name: str) -> FieldOwnership:
        """The declaration for ``name``; raises when the field is unowned (C001)."""
        try:
            return self.fields[name]
        except KeyError:
            raise OwnershipError(
                f"projection field {name!r} resolves to no declared writer; the policy covers "
                f"{sorted(self.fields)}"
            ) from None

    def writer_of(self, name: str) -> str:
        return self.owner(name).writer

    def rule_of(self, name: str) -> str:
        return self.owner(name).rule

    def rules(self) -> Tuple[str, ...]:
        """Every merge rule the policy actually declares, in canonical order.

        The *declared* set, not :data:`MERGE_RULES`: the merge-driver matrix must cover the
        rules this policy uses, so declaring a new one is what makes a new matrix row
        required (C002).
        """
        declared = {owner.rule for owner in self.fields.values()}
        return tuple(rule for rule in MERGE_RULES if rule in declared) + tuple(
            sorted(declared - set(MERGE_RULES))
        )

    def fields_owned_by(self, writer: str) -> Tuple[str, ...]:
        return tuple(sorted(name for name, o in self.fields.items() if o.writer == writer))

    def as_document(self) -> Dict[str, Any]:
        """The policy as a ``commons:projection-field-ownership`` document."""
        entries: List[Dict[str, Any]] = []
        for name in sorted(self.fields):
            owner = self.fields[name]
            entry: Dict[str, Any] = {
                "field": owner.field,
                "writer": _spell_for_contract(owner.writer),
                "rule": owner.rule,
            }
            if not owner.lifecycle_readable:
                entry["lifecycle_readable"] = False
            entries.append(entry)
        return {"fields": entries}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "FieldOwnershipPolicy":
        """Parse a policy document, normalising writer spellings to the canonical ids.

        Structural faults are refused here; *semantic* ones — an uncovered field, an unknown
        writer — are the coverage check's job (:func:`check_coverage`), because an operator
        editing the policy wants every one of them at once, not the first.
        """
        if not isinstance(document, Mapping) or not isinstance(document.get("fields"), list):
            raise OwnershipError(
                "a field-ownership policy is a mapping with a 'fields' list "
                "(commons:projection-field-ownership)"
            )
        fields: Dict[str, FieldOwnership] = {}
        for entry in document["fields"]:
            if not isinstance(entry, Mapping):
                raise OwnershipError(f"policy entry {entry!r} is not a mapping")
            missing = [key for key in ("field", "writer", "rule") if key not in entry]
            if missing:
                raise OwnershipError(f"policy entry {dict(entry)!r} is missing {missing}")
            name = str(entry["field"])
            if name in fields:
                raise OwnershipError(
                    f"projection field {name!r} is declared twice; a field has exactly one writer"
                )
            fields[name] = FieldOwnership(
                field=name,
                writer=WRITER_ALIASES.get(str(entry["writer"]), str(entry["writer"])),
                rule=str(entry["rule"]),
                lifecycle_readable=bool(entry.get("lifecycle_readable", True)),
            )
        return cls(fields=fields)


def _spell_for_contract(writer: str) -> str:
    """The contract's spelling of a canonical writer id (the inverse of the alias table)."""
    for spelling, canonical in WRITER_ALIASES.items():
        if canonical == writer:
            return spelling
    return writer


#: The committed policy, in executable form (spec §7.1). ``.atdd/policy/field-ownership.yaml``
#: is the declaration an operator edits; this is what core carries when it is asked to judge
#: a diff in a checkout that has not committed one. The two are bound by a coherence test.
#:
#: Two entries are worth their justification:
#:
#: - ``extension_digests`` is owned by ``core_lifecycle``, not by the bot. The provider
#:   *supplies* the digest; core *writes* it (spec §7.1) — so a bot commit that touches it
#:   directly is the wrong writer, and that is the reading this table enforces.
#: - ``tombstone`` merges under ``conflict-unless-same-digest``: two sides retiring the same
#:   object for different stated reasons is not something a merge may quietly pick between.
DEFAULT_POLICY: Dict[str, Any] = {
    "fields": [
        {"field": "uid", "writer": "core_create", "rule": RULE_IMMUTABLE},
        {"field": "slug", "writer": "core_authoring", "rule": RULE_MUTABLE},
        {"field": "title", "writer": "core_authoring", "rule": RULE_MUTABLE},
        {"field": "body", "writer": "core_authoring", "rule": RULE_SINGLE_OWNER},
        {"field": "owner_actor", "writer": "core_authoring", "rule": RULE_MUTABLE},
        {"field": "phase", "writer": "core_lifecycle", "rule": RULE_MONOTONIC_GATED},
        {"field": "state", "writer": "core_lifecycle", "rule": RULE_MONOTONIC_GATED},
        {"field": "tombstone", "writer": "core_lifecycle", "rule": RULE_SAME_DIGEST},
        {"field": "last_lifecycle_actor", "writer": "core_lifecycle", "rule": RULE_DERIVED},
        {"field": "extension_digests", "writer": "core_lifecycle", "rule": RULE_DERIVED},
        {"field": "train", "writer": "core_train_ops", "rule": RULE_SAME_DIGEST},
        {"field": "wmbts", "writer": "core_test_ops", "rule": RULE_POLICY_MERGE},
        {
            "field": "external_refs",
            "writer": "extension_bot",
            "rule": RULE_BOT_ONLY,
            "lifecycle_readable": False,
        },
    ],
}


def default_policy() -> FieldOwnershipPolicy:
    """The shipped ownership table (the executable form of the committed policy)."""
    return FieldOwnershipPolicy.from_document(DEFAULT_POLICY)


def policy_path(root: Path) -> Path:
    """Where the policy is expected to live under ``root``."""
    return Path(root) / POLICY_RELATIVE


def load_document(root: Path) -> Dict[str, Any]:
    """The committed policy document under ``root``; raises :class:`PolicyNotFound`."""
    path = policy_path(root)
    if not path.is_file():
        raise PolicyNotFound(path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise OwnershipError(f"{path}: not a YAML mapping")
    return document


def load_policy(root: Path) -> FieldOwnershipPolicy:
    """Load the committed field-ownership policy (D001).

    Raises :class:`PolicyNotFound` when the repo has not declared one — never an empty
    table, which would admit every writer for every field without saying so.
    """
    return FieldOwnershipPolicy.from_document(load_document(root))


# --------------------------------------------------------------------------- #
# Coverage (C001) — a policy that leaves a field unowned is not a policy
# --------------------------------------------------------------------------- #
#: The projection schema's field list — the universe the policy must cover. Taken from the
#: projector itself, so adding a field to the schema *makes the policy incomplete* until it
#: is declared, rather than leaving it quietly unowned.
def schema_fields() -> Tuple[str, ...]:
    return tuple(sorted(FIELD_TYPES))


@dataclass(frozen=True)
class CoverageReport:
    """The outcome of checking a policy against the projection schema (C001)."""

    checked: int
    uncovered: List[str] = field(default_factory=list)
    unknown_writers: List[Tuple[str, str]] = field(default_factory=list)
    unknown_rules: List[Tuple[str, str]] = field(default_factory=list)
    unknown_fields: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.uncovered or self.unknown_writers or self.unknown_rules or self.unknown_fields
        )

    def render(self) -> str:
        if self.ok:
            return (
                f"every projection field resolves to one declared writer and one merge rule "
                f"({self.checked} field(s))"
            )
        lines = ["field-ownership policy rejected:"]
        for name in self.uncovered:
            lines.append(
                f"  - {name}: uncovered — the policy declares no writer for it, so no diff "
                "touching it can be judged"
            )
        for name, writer in self.unknown_writers:
            lines.append(
                f"  - {name}: unknown writer {writer!r} — the declared writer set is "
                f"{list(WRITERS)} (an actor such as 'human' is not a writer)"
            )
        for name, rule in self.unknown_rules:
            lines.append(
                f"  - {name}: unknown merge rule {rule!r} — the declared rule set is "
                f"{list(MERGE_RULES)}"
            )
        for name in self.unknown_fields:
            lines.append(f"  - {name}: declared, but no such field exists in the projection schema")
        return "\n".join(lines)


def check_coverage(
    document: Mapping[str, Any],
    *,
    fields: Optional[Tuple[str, ...]] = None,
) -> CoverageReport:
    """Refuse a policy that leaves a field unowned or names a writer outside the set (C001).

    Both faults are silent by nature: an omitted field is unowned — every writer may write
    it and the merge driver has no rule for it — and an unknown writer can never match a
    resolved actor, so the field it "owns" is effectively unwritable. Neither shows up as an
    error anywhere else, so authoring is where they have to be caught.
    """
    universe = tuple(fields) if fields is not None else schema_fields()
    policy = FieldOwnershipPolicy.from_document(document)
    report = CoverageReport(
        checked=len(universe),
        uncovered=[name for name in universe if name not in policy.fields],
        unknown_writers=[
            (name, owner.writer)
            for name, owner in sorted(policy.fields.items())
            if owner.writer not in WRITERS
        ],
        unknown_rules=[
            (name, owner.rule)
            for name, owner in sorted(policy.fields.items())
            if owner.rule not in MERGE_RULES
        ],
        unknown_fields=[name for name in sorted(policy.fields) if name not in universe],
    )
    if not report.ok:
        _log.warning(
            "field-ownership policy rejected",
            extra={
                "uncovered": report.uncovered,
                "unknown_writers": [w for _, w in report.unknown_writers],
            },
        )
    return report


# --------------------------------------------------------------------------- #
# Actors (D002) — who committed, and what they are therefore allowed to write
# --------------------------------------------------------------------------- #
def actor_class(actor: str) -> str:
    """Classify a committing identity: core, extension bot, or unattributed."""
    if not actor or not actor.strip():
        return ACTOR_UNATTRIBUTED
    return ACTOR_EXTENSION if _BOT_ACTOR_RE.search(actor) else ACTOR_CORE


def allowed_writers(actor: str) -> FrozenSet[str]:
    """The writer roles ``actor`` may act as (spec §7.1, §8.2).

    The two directions the wagon exists to block fall straight out of this table: a core
    actor is not the extension bot, and the extension bot is not core. An *unattributed*
    diff is allowed every writer — not out of leniency, but because a wrong-writer claim
    against an unknown writer would be a guess, and the writer-independent rules (immutable
    uid, no file deletion) still apply to it.
    """
    kind = actor_class(actor)
    if kind == ACTOR_EXTENSION:
        return frozenset({WRITER_EXTENSION_BOT})
    if kind == ACTOR_CORE:
        return CORE_WRITERS
    return frozenset(WRITERS)


# --------------------------------------------------------------------------- #
# The field-writer validator (E001)
# --------------------------------------------------------------------------- #
#: Dict-valued fields whose *leaves* are the interesting unit: a report that says
#: "external_refs changed" when what changed was ``external_refs.github.issue_number`` has
#: made the operator go and diff it by hand.
_LEAF_FIELDS: Tuple[str, ...] = ("external_refs", "extension_digests", "tombstone")


def changed_field_paths(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> List[Tuple[str, str]]:
    """``(field, path)`` for every value that moved between two documents.

    ``field`` is the top-level projection field the policy owns; ``path`` is the dotted
    leaf that actually changed. For a scalar the two are the same.
    """
    changed: List[Tuple[str, str]] = []
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        if name in _LEAF_FIELDS and isinstance(old or {}, Mapping) and isinstance(new or {}, Mapping):
            changed.extend(
                (name, f"{name}.{leaf}") for leaf in _changed_leaves(old or {}, new or {})
            )
            continue
        changed.append((name, name))
    return changed


def _changed_leaves(before: Mapping[str, Any], after: Mapping[str, Any], prefix: str = "") -> List[str]:
    """Every dotted leaf path whose value differs between two nested mappings."""
    leaves: List[str] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        path = f"{prefix}{key}"
        if isinstance(old, Mapping) and isinstance(new, Mapping):
            leaves.extend(_changed_leaves(old, new, prefix=f"{path}."))
        else:
            leaves.append(path)
    return leaves


@dataclass(frozen=True)
class WriterViolation:
    """One field written by an actor that does not own it — named well enough to act on."""

    uid: str
    path: str
    actor: str
    writer: Optional[str]
    rule: Optional[str]
    detail: str

    def render(self) -> str:
        legal = f" the legal writer is {self.writer}" if self.writer else ""
        rule = f" [{self.rule}]" if self.rule else ""
        return f"{self.uid}: {self.path} written by {self.actor or '<unattributed>'};{legal}{rule} — {self.detail}"


@dataclass(frozen=True)
class WriterReport:
    """The outcome of the field-writer validator over a projection diff (E001)."""

    checked: int
    violations: List[WriterViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1

    def render(self) -> str:
        if self.ok:
            return f"every projection field was written by its owner ({self.checked} object(s))"
        lines = [f"wrong-writer field change(s) ({len(self.violations)}):"]
        lines.extend(f"  - {violation.render()}" for violation in self.violations)
        return "\n".join(lines)


def check_diff(
    policy: FieldOwnershipPolicy,
    base: Mapping[str, Mapping[str, Any]],
    head: Mapping[str, Mapping[str, Any]],
    *,
    actor: str = "",
) -> WriterReport:
    """Refuse a projection diff that touches a field its writer does not own (E001).

    Three classes of refusal, in the order an operator reads them:

    1. the file was **deleted** — retirement is a tombstone record, never a deletion;
    2. an **unowned** or **immutable** field moved — ``uid`` is identity and cannot be
       rewritten, and a field no policy entry covers cannot be judged at all;
    3. the **wrong writer** touched a field — a core actor writing ``external_refs``, or the
       extension bot writing a lifecycle field. Both directions, from one table (spec §7.1).

    The ``body`` clause is the one that needs the actor *identity* rather than its class: the
    field is owned under ``conflict-unless-single-owner``, so a body edit is admissible only
    from the object's ``owner_actor`` (D002). Without that field on the object there is
    nothing to compute the rule against — which is precisely why it is on it.
    """
    permitted = allowed_writers(actor)
    attributed = actor_class(actor) != ACTOR_UNATTRIBUTED
    uids = sorted(set(base) | set(head))
    violations: List[WriterViolation] = []
    checked = 0

    for uid in uids:
        before, after = base.get(uid), head.get(uid)
        if before == after:
            continue
        checked += 1

        if before is not None and after is None:
            violations.append(WriterViolation(
                uid=uid, path="<file>", actor=actor, writer=None, rule=None,
                detail="the projection file was deleted; retirement is a tombstone record, "
                       "never a file deletion (spec §10 rule 3)",
            ))
            continue

        for name, path in changed_field_paths(before or {}, after or {}):
            if name not in policy:
                violations.append(WriterViolation(
                    uid=uid, path=path, actor=actor, writer=None, rule=None,
                    detail="the field-ownership policy declares no writer for this field, so no "
                           "writer may touch it",
                ))
                continue
            owner = policy.owner(name)

            if owner.rule == RULE_IMMUTABLE and before is not None:
                violations.append(WriterViolation(
                    uid=uid, path=path, actor=actor, writer=owner.writer, rule=owner.rule,
                    detail=f"{name} is immutable and was rewritten to {(after or {}).get(name)!r}",
                ))
                continue

            if owner.writer not in permitted:
                violations.append(WriterViolation(
                    uid=uid, path=path, actor=actor, writer=owner.writer, rule=owner.rule,
                    detail=_wrong_writer_detail(actor, owner.writer),
                ))
                continue

            if owner.rule == RULE_SINGLE_OWNER and attributed and before is not None:
                owner_actor = str((after or {}).get("owner_actor") or "")
                if owner_actor and owner_actor != actor:
                    violations.append(WriterViolation(
                        uid=uid, path=path, actor=actor, writer=owner.writer, rule=owner.rule,
                        detail=f"{name} is owned by {owner_actor!r} under "
                               f"{RULE_SINGLE_OWNER}; a second writer editing it is the "
                               "divergence the rule exists to refuse",
                    ))

    report = WriterReport(checked=checked, violations=violations)
    if not report.ok:
        _log.warning(
            "wrong-writer field change(s) in the projection diff",
            extra={"actor": actor, "objects": checked, "violations": len(violations)},
        )
    return report


def _wrong_writer_detail(actor: str, writer: str) -> str:
    """Why this actor may not write a field owned by ``writer`` — in both directions."""
    if actor_class(actor) == ACTOR_EXTENSION:
        return (
            f"the extension bot may write only {WRITER_EXTENSION_BOT} fields; the GitHub "
            "mirror is presentation, never lifecycle truth (I7, spec §8.2)"
        )
    return (
        f"only the {writer} may write it; a core actor hand-editing the provider's subtree "
        "would make the mirror a second source of truth (spec §7.1)"
    )

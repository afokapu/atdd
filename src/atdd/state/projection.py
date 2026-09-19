"""The committed projection — shared source of truth (#1400 project-shared-state).

The scoped-truth rule (spec §1): the local SQLite store is the *private authoring
workspace*; the committed, deterministic per-uid projection under
``.atdd/state/projection/<uid>.yaml`` is the *shared* source of truth that peers
and CI read. This module is the projection spine (milestone M1):

- :func:`project`            — store → byte-identical canonical per-uid YAML (I1).
- :func:`hydrate`            — committed projection at HEAD → store, zero providers.
                               Restores objects AND the projected ``external_refs`` slice,
                               merging into what the store already holds (#2025).
- :func:`projection_digest`  — a stable digest over the canonical bytes.
- :func:`check_canonicality` — the honest CI guarantee (spec §4):
  ``project(hydrate(committed projection)) == committed projection``, byte-for-byte.

Determinism (I1) is enforced *before* any byte is written: a document carrying a
wall-clock timestamp or an absolute host path is refused, and every unordered
collection reaching the serializer is emitted in a total, content-derived order.
The three known leaks — timestamps, host paths, iteration order — each have a
guard here; nothing else may reach a projection file.

The document shape is the ``commons:projection-object`` contract
(``contracts/commons/projection-object.schema.json``). The authored schema is the
source of truth for the shape; the constants below are its executable form, and
``state/tests/test_projection_schema_matches_contract.py`` fails if the two drift.
The schema is NOT vendored under ``state/`` — that layer holds operational data
and storage APIs only, never authored definitions (``coder.state-store``
``.operational-vs-definition-sot``).

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` only. In particular it
imports **no** provider and never consults ``external_refs`` for a lifecycle
decision (I7, spec §8.2 rule 5). Reading the ``external_refs`` TABLE to project a
document (#2025) is a read of a local table, not a call to a provider, and the value
is *carried* — no phase, no transition and no lifecycle decision in core reads it.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from atdd.state.identity import UID_RE, is_uid
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import Object, StateStore

_log = logging.getLogger(__name__)

#: Where the committed projection lives, relative to the Control Root.
PROJECTION_RELATIVE = Path(".atdd") / "state" / "projection"

#: One document per object; the uid — and only the uid — names the file.
PROJECTION_SUFFIX = ".yaml"

#: Lifecycle phases a *committed* projection may carry. COMPLETE is deliberately
#: absent: it is DERIVED from merge-to-main (spec §18 decision 1), so a committed
#: projection asserting phase=COMPLETE is invalid, not merely stale.
PHASES: Tuple[str, ...] = (
    "INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "BLOCKED", "OBSOLETE",
    # Success without code (#1967). Projected, unlike COMPLETE: a resolved umbrella
    # is a STORED terminal — nothing downstream re-derives it from a merge, because
    # there is no merge. See the RESOLVED block in phase_machine.convention.yaml.
    "RESOLVED",
)

#: Lifecycle phases a store object may carry that are NOT projected. ``COMPLETE`` is
#: derived from merge-to-main (spec §18 decision 1): it has no legal projection
#: document, so the projector passes over such objects rather than refusing them (see
#: :func:`build_documents`). The store keeps the record; git keeps the completion.
ARCHIVED_PHASES: Tuple[str, ...] = ("COMPLETE",)

#: Retirement is a tombstone record, never a file deletion (spec §10 rule 3).
STATES: Tuple[str, ...] = ("ACTIVE", "TOMBSTONED")

#: The default lifecycle state of a live object.
STATE_ACTIVE = "ACTIVE"
STATE_TOMBSTONED = "TOMBSTONED"

#: Every field the contract admits (``additionalProperties: false``), with the
#: type(s) it may take. Anything outside this table is refused.
FIELD_TYPES: Dict[str, Any] = {
    "uid": str,
    "slug": str,
    "title": str,
    "body": str,
    "phase": str,
    "state": str,
    "owner_actor": str,
    "last_lifecycle_actor": (str, type(None)),
    "train": (str, type(None)),
    # Grown from the data bag by the #1622 dispositions. Both are NULLABLE and must stay
    # so: 22 of 737 live projectable objects carry `type: None`, and typed as plain `str`
    # they refuse the WHOLE projection — assert/validate runs over every document before
    # the first file is written. `wagon` is nullable for the same reason, and carries
    # heterogeneous values (full URNs, bare slugs, one prose value), so it takes no pattern.
    "type": (str, type(None)),
    "wagon": (str, type(None)),
    "wmbts": list,
    "extension_digests": dict,
    "external_refs": dict,
    "tombstone": dict,
}

#: Keys the projector OMITS from the document while the store keeps them (#1622).
#:
#: Strip is not drop. Each of these has a live reader that reads the **live SQLite store**,
#: and carrying them would put machine-local or unreliable values into shared state.
#:
#: The #1622 ruling authorized the strip on the premise that the store is never rebuilt from
#: the projection. #2025 removed that premise — ``hydrate`` is now a real inbound path — so
#: the strip is held up by :func:`hydrate` carrying these keys forward from the object it is
#: writing over, NOT by the projection never being read back. Change one and you must change
#: the other. See the supersession addendum in
#: ``docs/1400-findings/1622-projection-authority-ruling.md``:
#:
#: - ``branch``    the pre-commit registration gate's primary index (#1720). Per-machine:
#:                 written by ``atdd worktree create`` on the host that needs it, so a peer
#:                 was never going to inherit a useful value.
#: - ``feature``   49% of its non-null values are a literal the generator substitutes for an
#:                 omitted ``--feature`` (#2006). Growing it would publish 172 false bindings
#:                 as authoritative shared state.
#: - ``worktree``  51 carriers, exactly 1 non-null.
#: - ``created``   } authoring timestamps and the GitHub id, both re-derivable and neither
#: - ``id``        } read by a decision module.
STRIPPED_AT_PROJECTION: FrozenSet[str] = frozenset({
    "branch", "feature", "worktree", "created", "id",
})

#: The projection field the provider identity rides in. Bot-owned (``field-ownership.yaml``:
#: ``writer: extension_bot``, ``rule: bot-only``, ``lifecycle_readable: false``) and *carried,
#: never consulted* — no phase, no transition and no lifecycle decision in core reads it (I7).
EXTERNAL_REFS_FIELD = "external_refs"

GITHUB_PROVIDER = "github"
ISSUE_REF_KIND = "issue"

#: The ``(provider, ref_kind)`` pairs the PROJECTOR sources from the ``external_refs`` TABLE,
#: each with the reason it is admitted (#2025). This governs what the projector *emits*; it
#: does NOT govern what the contract *admits*, and the two are deliberately different — see
#: :func:`_validate_external_refs`.
#:
#: Everything outside this table is excluded, on three independent grounds:
#:
#: - ``(claude, session)`` — **determinism**. Those 154 rows carry ``data.last_seen_at``, a
#:   wall-clock reading, and :func:`assert_deterministic` refuses the whole corpus on the
#:   first fault. Serializing the table wholesale does not leak session metadata into shared
#:   state; it makes the projection *unwritable*.
#: - the row's ``data`` blob — **the #1622 ruling**. It is determinism-clean, so nothing
#:   mechanical stops it, but 819 of 1,103 GitHub rows carry a ``_recovery`` bag, the key that
#:   ruling ruled DROP. Carrying it would reverse the ruling by the back door.
#: - refs on a non-projected kind — **kind**. 56 ``(github, issue)`` rows sit on ``wmbt``
#:   objects, which have no projection document to ride in.
PROJECTED_REF_KINDS: Dict[Tuple[str, str], str] = {
    (GITHUB_PROVIDER, ISSUE_REF_KIND):
        "the work item's GitHub issue number — the addressing a reconciliation workflow "
        "reading the committed projection needs, and after the #1622 issue_number drop the "
        "only GitHub identity the store holds",
}

#: A projected issue number is a digit STRING. The store column is ``TEXT``, and ``'1975'``
#: and ``1975`` do not serialize to the same bytes — so an unquoted hand-edit would re-project
#: differently and break ``project(hydrate(p)) == p`` with no schema violation to explain it.
#: The contract types this leaf for that reason and constrains nothing else.
ISSUE_VALUE_RE = re.compile(r"^[0-9]+$")

#: Contract ``required``.
REQUIRED_FIELDS: Tuple[str, ...] = ("uid", "phase", "state", "owner_actor")

#: A ``sha256:<hex>`` stamp, the one digest form the contract accepts.
DIGEST_PREFIX = "sha256:"

#: The provenance a **committed** tombstone must carry to be actionable (#1580).
#:
#: Retirement is the only thing a projection can say that ends something, so it is the only
#: claim that must stay auditable after the fact. Without this, ``state: TOMBSTONED`` is a
#: sentence with no author and no cause, and there is no way to tell — a year later, in a
#: merge that tries to reintroduce the uid — whether it was ever true. Each field answers
#: one question a reviewer will actually have:
#:
#: - ``actor``             who retired it
#: - ``reason``            why, in prose, with ``reason_digest`` as the comparable stamp
#: - ``source_generation`` which generation of the shared truth decided it
#: - ``prior_digest``      what the object was immediately before, so the retirement can be
#:                         shown to have been made against the state it claims
#:
#: Enforced on the way *in* (:func:`validate_document`), so an unattributable retirement
#: cannot reach a store even if someone hand-writes one into the projection.
REQUIRED_TOMBSTONE_FIELDS: Tuple[str, ...] = (
    "actor", "reason", "reason_digest", "source_generation", "prior_digest",
)


class ProjectionError(ValueError):
    """Base class for every refusal raised on the projection path."""


class NondeterministicProjectionError(ProjectionError):
    """A document would carry a determinism leak; no file is written (C001).

    Carries the offending ``field`` so the operator is told *what* to remove,
    not merely that the projection was refused.
    """

    def __init__(self, field_path: str, reason: str, *, uid: Optional[str] = None) -> None:
        self.field_path = field_path
        self.reason = reason
        self.uid = uid
        where = f"{uid} " if uid else ""
        super().__init__(
            f"nondeterministic projection content {where}at field {field_path!r}: {reason}"
        )


class ProjectionSchemaError(ProjectionError):
    """A document does not conform to ``commons:projection-object``."""


class DuplicateExternalRefError(ProjectionError):
    """One object carries two refs of the same ``(provider, ref_kind)`` (#2025).

    The refs table is ``UNIQUE (provider, ref_kind, ref_value)`` — *not* per object — so
    binding one uid to two GitHub issues is a state the store can hold, and a scalar leaf
    cannot carry it. Picking one would make the emitted bytes depend on the row order
    ``ExternalRefStore.all()`` happens to yield, which breaks I1 rather than merely losing a
    row. So the whole run is refused, in the same spirit as :func:`build_documents`' refusal
    on a determinism fault.
    """

    def __init__(self, uid: str, provider: str, ref_kind: str, values: Sequence[str]) -> None:
        self.uid = uid
        self.provider = provider
        self.ref_kind = ref_kind
        self.values = tuple(values)
        super().__init__(
            f"{uid} carries {len(self.values)} {provider}/{ref_kind} refs "
            f"({', '.join(self.values)}), and a projected {provider}.{ref_kind} is a single "
            "value. Which one survived would depend on row iteration order, so the projection "
            "is refused rather than made nondeterministic. Retire the stale ref, or bind the "
            "second issue to its own work item"
        )


class ExternalRefConflictError(ProjectionError):
    """An inbound ref claims a provider identity the local store binds elsewhere (#2025).

    ``ExternalRefStore.link`` is ``ON CONFLICT(provider, ref_kind, ref_value) DO UPDATE SET
    object_uid=excluded.object_uid`` — last writer wins, silently. Two peers binding different
    uids to one issue number is the object conflict this train exists to resolve, and resolving
    it by overwrite is not resolving it. Raised before the first write of the hydrate.
    """

    def __init__(self, provider: str, ref_kind: str, ref_value: str, ours: str, theirs: str) -> None:
        self.provider = provider
        self.ref_kind = ref_kind
        self.ref_value = ref_value
        self.ours = ours
        self.theirs = theirs
        super().__init__(
            f"{provider}/{ref_kind} {ref_value} is bound to {ours} here and to {theirs} in the "
            "incoming projection. Nothing was written. An issue identifies one work item, so "
            "this is a conflict for a person to settle, not a value to overwrite"
        )


class MissingProjectionError(ProjectionError):
    """The projection directory a caller required does not exist (#1580).

    "There is no projection here" and "the projection carries no objects" are different
    facts, and :func:`read_projection` used to answer both with ``{}``. That collapse is
    half of what made the 2026-07-20 mass-deletion silent: a control root resolved
    somewhere without a projection produced the same empty mapping as a genuine empty
    one, and the caller deleted the store to match.

    So the distinction is now carried in the type. Callers that mean "read whatever is
    there" keep the permissive default; callers about to *act* on the answer pass
    ``require=True`` and get this instead.
    """

    def __init__(self, projection_dir: Path) -> None:
        self.projection_dir = Path(projection_dir)
        super().__init__(
            f"no projection directory at {self.projection_dir} — this is not an empty "
            "projection, it is the absence of one, and the two must not be confused.\n"
            "  A store is never rebuilt from a projection that is not there. Check that the "
            "Control Root is the one you meant, and that the projection is committed at HEAD."
        )


# --------------------------------------------------------------------------- #
# Determinism guard (C001) — refuse the three known leaks before any write
# --------------------------------------------------------------------------- #
#: Field names that carry a wall-clock reading by convention. Any ``*_at`` key is
#: caught by the suffix rule as well; these are the ones that do not end in ``_at``.
_TIMESTAMP_KEYS = frozenset({"timestamp", "now", "date", "datetime", "mtime", "ctime"})

#: An ISO-8601 wall-clock reading anywhere inside a string value.
_TIMESTAMP_VALUE_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")

#: The per-host filesystem namespaces. A path rooted in one of these differs
#: between developers, between CI runners, and between checkouts of the same repo,
#: so it can never appear in a shared artifact.
_HOST_PATH_RE = re.compile(
    r"(?:/Users/|/home/|/root/|/private/var/|/var/folders/|/var/tmp/|/tmp/|[A-Za-z]:\\)"
)

#: The free-text fields, exempt from the *value* scan.
#:
#: I1 is about content the **projector** generates. A path or a date inside the
#: issue body is not generated — it is *preserved*: the projector copies what a
#: human wrote, byte for byte, and copies the same bytes on every host and every
#: run. Prose that happens to quote ``/Users/alec/…`` or ``2026-07-11`` is
#: therefore deterministic by preservation, and refusing it would refuse a
#: perfectly legal issue body while catching nothing (spec §2.2 I1: "no timestamps,
#: host paths, or unstable ordering" names the three ways *machine-injected*
#: volatility reaches a shared artifact).
#:
#: The scan is narrowed to the generated and structured fields — where a leak means
#: the projector reached for the wall clock or the local filesystem, which is the
#: fault I1 exists to catch. The *key*-name rule (below) still applies to every
#: field, free-text included: a field named ``body_at`` is a timestamp field
#: whatever it holds.
FREE_TEXT_FIELDS: frozenset = frozenset({"body"})


def _scalar_fault(value: str) -> Optional[str]:
    """The determinism fault a string *value* carries, or ``None`` if it is clean."""
    if _TIMESTAMP_VALUE_RE.search(value):
        return "carries a wall-clock timestamp"
    if _HOST_PATH_RE.search(value):
        return "carries an absolute host path"
    return None


def _key_fault(key: str) -> Optional[str]:
    """The determinism fault a mapping *key* carries, or ``None`` if it is clean."""
    lowered = key.lower()
    if lowered.endswith("_at") or lowered in _TIMESTAMP_KEYS:
        return "is a wall-clock timestamp field"
    return None


def _walk_for_faults(node: Any, path: str, faults: List[Tuple[str, str]]) -> None:
    """Collect ``(field_path, reason)`` for every determinism leak under ``node``.

    A top-level free-text field has its *value* skipped (see :data:`FREE_TEXT_FIELDS`);
    its key is still judged, and a field of the same name nested inside a structured
    field — ``external_refs.body``, say — is machine-written and is scanned.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            reason = _key_fault(str(key))
            if reason is not None:
                faults.append((child, reason))
            if child in FREE_TEXT_FIELDS:
                continue
            _walk_for_faults(value, child, faults)
        return
    if isinstance(node, (list, tuple, set, frozenset)):
        for index, value in enumerate(node):
            _walk_for_faults(value, f"{path}[{index}]", faults)
        return
    if isinstance(node, str):
        reason = _scalar_fault(node)
        if reason is not None:
            faults.append((path, reason))


def assert_deterministic(document: Mapping[str, Any], *, uid: Optional[str] = None) -> None:
    """Refuse ``document`` if a *generated* field carries a timestamp or host path (I1, C001).

    Raises :class:`NondeterministicProjectionError` naming the first offending
    field. Callers run this over *every* document before writing *any* file, so a
    single leak leaves the whole projection unwritten rather than half-applied.

    The scan covers the projector-generated and structured fields. The free-text
    body is exempt from the value scan: its content is authored, not generated, so
    it is deterministic by preservation (see :data:`FREE_TEXT_FIELDS`).
    """
    faults: List[Tuple[str, str]] = []
    _walk_for_faults(document, "", faults)
    if not faults:
        return
    field_path, reason = faults[0]
    _log.warning(
        "projection refused: nondeterministic content",
        extra={"uid": uid, "field": field_path, "reason": reason, "faults": len(faults)},
    )
    raise NondeterministicProjectionError(field_path, reason, uid=uid)


# --------------------------------------------------------------------------- #
# Canonical bytes (I1) — total, content-derived order; no iteration-order leak
# --------------------------------------------------------------------------- #
def _order_key(value: Any) -> str:
    """A total, *content-derived* sort key — never insertion order, never hash order."""
    return json.dumps(value, sort_keys=True, default=str)


def canonicalize(value: Any) -> Any:
    """Rewrite ``value`` into its canonical form: sets and sequences sorted by content.

    Sets and dicts have no inherent order, and CPython's iteration order for a set
    of strings varies with ``PYTHONHASHSEED``. Sorting by the JSON rendering of each
    element makes the emitted order a function of the *content* alone, so the same
    logical store yields the same bytes on every host and every run.
    """
    if isinstance(value, Mapping):
        return {str(k): canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (set, frozenset, list, tuple)):
        return sorted((canonicalize(v) for v in value), key=_order_key)
    return value


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """The canonical UTF-8 bytes of ``document`` — the unit the digest and CI compare.

    Keys are emitted in a fixed (sorted) order, sequences in content-derived order,
    block style throughout, and never line-wrapped (a wrap point would otherwise
    depend on nothing but the dumper's default width).
    """
    text = yaml.safe_dump(
        canonicalize(dict(document)),
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1 << 30,
    )
    return text.encode("utf-8")


# --------------------------------------------------------------------------- #
# Schema (commons:projection-object)
# --------------------------------------------------------------------------- #
def _validate_enum(document: Mapping[str, Any]) -> List[str]:
    problems: List[str] = []
    if not is_uid(document.get("uid")):
        problems.append(f"uid {document.get('uid')!r} does not match {UID_RE.pattern}")
    if document.get("phase") not in PHASES:
        problems.append(
            f"phase {document.get('phase')!r} is not one of {list(PHASES)} "
            "(COMPLETE is derived from merge-to-main, never committed)"
        )
    if document.get("state") not in STATES:
        problems.append(f"state {document.get('state')!r} is not one of {list(STATES)}")
    problems.extend(_validate_tombstone(document))
    return problems


def _validate_tombstone(document: Mapping[str, Any]) -> List[str]:
    """A retirement must be attributable, or it is not a retirement (#1580).

    Only checked when the document actually claims ``TOMBSTONED``: a live object may carry
    no ``tombstone`` key at all, and demanding provenance from it would refuse every normal
    document in the store.
    """
    if document.get("state") != STATE_TOMBSTONED:
        return []
    record = document.get("tombstone") or {}
    missing = [name for name in REQUIRED_TOMBSTONE_FIELDS if not record.get(name)]
    if not missing:
        return []
    return [
        "a TOMBSTONED document must carry auditable provenance; its 'tombstone' record is "
        f"missing {', '.join(missing)} (required: {', '.join(REQUIRED_TOMBSTONE_FIELDS)}). "
        "Deletion has to be attributable — an unattributable retirement is a claim nobody "
        "can check"
    ]


def _validate_external_refs(refs: Any) -> List[str]:
    """Type the ``github.issue`` leaf; constrain nothing else (#2025).

    ``external_refs`` stays OPEN on purpose, and the reason is load-bearing:
    ``provider_seam.validate_update`` — the only sanctioned write-back — constrains the uid,
    the bot namespace, authoritativeness and provider *identity*, and enumerates neither
    provider nor ref kind. ``github/pr``, ``jira/ticket`` and ``linear/issue`` are all legal
    writes, and ``merge_driver._bot_only`` unions disjoint providers by design. A contract
    narrowed to ``github.issue`` would refuse writes the bot is built to make and then reject
    the merge results those writes produce.

    So exactly two things are checked, and both only when present: that ``github`` is a
    mapping (the shape ``apply_updates`` writes and the shape the projector merges into), and
    that ``github.issue`` is a digit string. The second is what keeps the round trip
    byte-stable — see :data:`ISSUE_VALUE_RE`.
    """
    if refs is None:
        return []
    if not isinstance(refs, Mapping):
        return [f"field {EXTERNAL_REFS_FIELD!r} has type {type(refs).__name__}, expected a mapping"]
    provider_subtree = refs.get(GITHUB_PROVIDER)
    if not isinstance(provider_subtree, Mapping):
        # Absent, or the FLAT ``{provider: ref}`` shape ``overlay.EXTERNAL_REF_APPLIED``
        # writes. That shape disagrees with the nested one ``provider_seam.apply_updates``
        # emits — the overlay event carries no ref-kind axis to nest by — and converging the
        # two is a change to the overlay's event payload, not to the projection spine. The
        # open field admits both; :func:`merge_external_refs` is where the disagreement is
        # refused, and only when there is actually something to merge.
        return []
    if ISSUE_REF_KIND not in provider_subtree:
        return []
    issue = provider_subtree[ISSUE_REF_KIND]
    if not isinstance(issue, str):
        return [
            f"{EXTERNAL_REFS_FIELD}.{GITHUB_PROVIDER}.{ISSUE_REF_KIND} has type "
            f"{type(issue).__name__}, expected a digit string. An unquoted integer re-projects "
            "to different bytes and would break project(hydrate(p)) == p"
        ]
    if not ISSUE_VALUE_RE.match(issue):
        return [
            f"{EXTERNAL_REFS_FIELD}.{GITHUB_PROVIDER}.{ISSUE_REF_KIND} is {issue!r}, which is not "
            f"a GitHub issue number (expected {ISSUE_VALUE_RE.pattern})"
        ]
    return []


def validate_document(document: Mapping[str, Any]) -> None:
    """Refuse ``document`` unless it conforms to ``commons:projection-object``.

    Checks the contract's ``required``, its ``additionalProperties: false``, the
    declared types, and the three constrained vocabularies (uid pattern, phase and
    state enums). Raises :class:`ProjectionSchemaError` listing every problem — an
    operator fixing a hand-edited file wants them all at once, not one per run.
    """
    problems: List[str] = [
        f"missing required field {name!r}"
        for name in REQUIRED_FIELDS
        if name not in document
    ]
    for key, value in document.items():
        expected = FIELD_TYPES.get(key)
        if expected is None:
            problems.append(f"unknown field {key!r} (the contract forbids extra properties)")
        elif not isinstance(value, expected):
            problems.append(f"field {key!r} has type {type(value).__name__}, expected {expected}")
    problems.extend(_validate_enum(document))
    problems.extend(_validate_external_refs(document.get(EXTERNAL_REFS_FIELD)))
    if problems:
        raise ProjectionSchemaError(
            f"projection document {document.get('uid', '<no uid>')} is invalid: "
            + "; ".join(problems)
        )


# --------------------------------------------------------------------------- #
# Document ↔ store object
# --------------------------------------------------------------------------- #
def merge_external_refs(
    carried: Any, sourced: Optional[Mapping[str, Mapping[str, str]]],
) -> Dict[str, Dict[str, str]]:
    """Layer ``sourced`` onto ``carried`` at the ``(provider, ref_kind)`` LEAF (#2025).

    Not at the provider. The difference is the whole of C003-UNIT-002: the table sources
    ``github.issue``, and ``provider_seam.apply_updates`` may legally have written
    ``github.pr`` under the same provider key. Replacing ``carried['github']`` with the
    sourced subtree destroys a ref the bot is entitled to write — and a test using only a
    foreign provider passes straight through that, which is how it survived the first
    review.

    So the two are merged key by key: the table wins for the kinds it sources, and every
    other kind, under every provider, is left exactly as it was found.
    """
    merged: Dict[str, Dict[str, str]] = {}
    for provider, kinds in (carried or {}).items():
        merged[provider] = dict(kinds) if isinstance(kinds, Mapping) else kinds
    for provider, kinds in (sourced or {}).items():
        target = merged.get(provider)
        if target is not None and not isinstance(target, Mapping):
            # The flat ``{provider: ref}`` shape, with a ref to merge into it. Overwriting
            # would destroy whatever the flat value said; there is no key to merge under.
            # Refuse rather than pick — this is the fault class the whole issue corrects.
            raise ProjectionSchemaError(
                f"{EXTERNAL_REFS_FIELD}.{provider} is {target!r}, a flat provider value, and "
                f"the refs table sources {sorted(kinds)} for it. The two shapes cannot be "
                "merged and overwriting one would lose it. Rewrite the flat ref as "
                f"{{{provider!r}: {{<ref_kind>: <value>}}}}"
            )
        target = dict(target) if isinstance(target, Mapping) else {}
        target.update(kinds)
        merged[provider] = target
    return merged


def source_external_refs(store: StateStore) -> Dict[str, Dict[str, Dict[str, str]]]:
    """``uid -> {provider: {ref_kind: ref_value}}`` for every :data:`PROJECTED_REF_KINDS` row.

    One query for the whole run — the refs table is read once and grouped, never queried per
    object. Rows outside the projected set are passed over silently: they are excluded by
    design, and each exclusion's reason is recorded on :data:`PROJECTED_REF_KINDS`.

    Raises :class:`DuplicateExternalRefError` if one object carries two values for the same
    ``(provider, ref_kind)`` — a state the table's uniqueness permits and a scalar leaf
    cannot represent.
    """
    sourced: Dict[str, Dict[str, Dict[str, str]]] = {}
    for ref in store.external_refs.all():
        if (ref.provider, ref.ref_kind) not in PROJECTED_REF_KINDS:
            continue
        subtree = sourced.setdefault(ref.object_uid, {}).setdefault(ref.provider, {})
        present = subtree.get(ref.ref_kind)
        if present is not None and present != ref.ref_value:
            raise DuplicateExternalRefError(
                ref.object_uid, ref.provider, ref.ref_kind,
                sorted((present, str(ref.ref_value))),
            )
        subtree[ref.ref_kind] = str(ref.ref_value)
    return sourced


def build_document(
    obj: Object, *, external_refs: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> Dict[str, Any]:
    """The projection document for a stored object — a pure, total mapping.

    The ``objects.state`` column is the lifecycle *phase* (the store's long-standing
    convention); every other projection field lives in the object's ``data`` bag and
    is carried through verbatim. An object that never recorded a retirement is ``ACTIVE``.

    The one exception is :data:`STRIPPED_AT_PROJECTION` (#1622): those keys stay in the
    store and are omitted here. Nothing is silently dropped — the set is enumerated, each
    entry carries its reason, and every live reader of one reads the store rather than the
    projection.

    ``external_refs`` is the provider identity for this object, sourced from the refs TABLE
    by :func:`source_external_refs` and **merged** into whatever the data bag already holds
    (#2025). Callers that have a store should pass it; the default of ``None`` carries the
    data bag's subtree through unchanged, which is what a caller holding only an ``Object``
    can honestly say.
    """
    document: Dict[str, Any] = {
        key: value for key, value in obj.data.items()
        if key not in STRIPPED_AT_PROJECTION
    }
    document["uid"] = obj.uid
    document["phase"] = obj.state
    document.setdefault("state", STATE_ACTIVE)
    refs = merge_external_refs(document.get(EXTERNAL_REFS_FIELD), external_refs)
    if refs:
        document[EXTERNAL_REFS_FIELD] = refs
    else:
        document.pop(EXTERNAL_REFS_FIELD, None)
    return document


def document_to_object(document: Mapping[str, Any]) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """The inverse of :func:`build_document`: ``(uid, phase, data)`` for the store.

    ``external_refs`` rides along inside ``data`` verbatim. It is *carried*, never
    *consulted* — no phase, no transition, and no lifecycle decision anywhere in
    core reads it (I7).
    """
    data = {k: v for k, v in document.items() if k not in ("uid", "phase")}
    return str(document["uid"]), document.get("phase"), data


# --------------------------------------------------------------------------- #
# project(store) → canonical per-uid YAML
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProjectionResult:
    """What a :func:`project` run wrote."""

    out_dir: Path
    #: uid → the file written for it.
    files: Dict[str, Path] = field(default_factory=dict)
    #: The digest over the canonical bytes of the whole projection set.
    digest: str = ""


# --------------------------------------------------------------------------- #
# Coverage (#2042) — does the committed projection cover the store?
#
# Every other check in the chain compares the projection to itself, or to a projection
# of the same snapshot it came from: byte-identity proves the WRITER is deterministic,
# self-canonicality proves the SERIALIZER is stable. A comparison whose two sides share
# a parent cannot detect a defect in that parent, and neither side has any opinion about
# what is ABSENT. Measured: a projection with a third of its documents deleted passes
# byte-identity, passes canonicality, is non-empty, and the cutover reports MET.
#
# So coverage compares two INDEPENDENT populations — the uids committed at HEAD against
# the uids the store obliges — in both directions, because equal counts with different
# members is exactly the corruption a count cannot see.
# --------------------------------------------------------------------------- #
def projectable_objects(store: StateStore) -> List[Object]:
    """Every stored object the projector is obliged to emit a document for.

    THE single definition of "projectable", and the reason it is a function rather than a
    comment: :func:`build_documents` iterates it and :func:`projectable_uids` derives from
    it, so the obligation cannot drift from the behaviour. A separately-written obligation
    is a second implementation of the same rule, and the two diverge the first time someone
    changes a filter — which would leave the coverage check confidently wrong.

    Two rules, both already load-bearing elsewhere: the store holds kinds the projection has
    no document shape for, and ``ARCHIVED_PHASES`` holds back COMPLETE work items because
    completion is derived from merge-to-main (spec §18 decision 1).
    """
    return [
        obj for obj in store.objects.list(kind=WORK_ITEM_KIND)
        if obj.state not in ARCHIVED_PHASES
    ]


def projectable_uids(store: StateStore) -> FrozenSet[str]:
    """The uids :func:`projectable_objects` names — the coverage obligation."""
    return frozenset(obj.uid for obj in projectable_objects(store))


@dataclass(frozen=True)
class CoverageCensus:
    """Every stored object assigned to exactly one bucket, with the residual named.

    The census is what makes the residual *provable* rather than merely explained. A gap
    between the store's population and the projection's is legitimate or it is loss, and
    prose cannot tell them apart — so every object is bucketed by the rule that put it
    there, and anything no rule claims lands in :attr:`residual`.
    """

    #: bucket label → how many objects it holds. Labels name the RULE, not the outcome.
    buckets: Dict[str, int] = field(default_factory=dict)
    #: uids the projector neither emits nor declines by a named rule. Empty is the invariant.
    residual: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.buckets.values())

    def render(self) -> str:
        lines = [f"  {name:<32}{count:>6}" for name, count in sorted(self.buckets.items())]
        lines.append(f"  {'TOTAL':<32}{self.total:>6}")
        if self.residual:
            lines.append(f"  unexplained: {', '.join(self.residual[:_MAX_NAMED])}")
        return "\n".join(lines)


def coverage_census(store: StateStore) -> CoverageCensus:
    """Bucket every stored object by the rule that decides whether it projects."""
    projectable = projectable_uids(store)
    buckets: Dict[str, int] = {}
    residual: List[str] = []
    for obj in store.objects.list():
        if obj.uid in projectable:
            label = "projected"
        elif obj.kind != WORK_ITEM_KIND:
            label = f"excluded: kind={obj.kind}"
        elif obj.state in ARCHIVED_PHASES:
            label = f"excluded: phase={obj.state}"
        else:  # pragma: no cover — the invariant is that this is unreachable
            label = "unexplained"
            residual.append(obj.uid)
        buckets[label] = buckets.get(label, 0) + 1
    return CoverageCensus(buckets=buckets, residual=sorted(residual))


@dataclass(frozen=True)
class CoverageReport:
    """Whether the committed projection covers the store, and how it does not."""

    #: What the store obliges the projection to carry.
    obliged: FrozenSet[str] = frozenset()
    #: What the projection actually carries, read from the committed tree.
    committed: FrozenSet[str] = frozenset()

    @property
    def missing(self) -> List[str]:
        """Obliged and absent — the store holds it, the shared truth has lost it."""
        return sorted(self.obliged - self.committed)

    @property
    def unexpected(self) -> List[str]:
        """Present and unobliged — the shared truth describes an object the store does not hold."""
        return sorted(self.committed - self.obliged)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unexpected

    def blockers(self) -> List[str]:
        """Operator-facing refusals, kept distinct because the remedies differ.

        "Missing" means re-project; "unexpected" means find out who wrote that file.
        Flattening them into "coverage failed" sends the operator to the wrong place.
        """
        out: List[str] = []
        if self.missing:
            out.append(
                f"{len(self.missing)} object(s) the store holds are absent from the committed "
                f"projection: {', '.join(self.missing[:_MAX_NAMED])}"
                + (f" … and {len(self.missing) - _MAX_NAMED} more"
                   if len(self.missing) > _MAX_NAMED else "")
            )
        if self.unexpected:
            out.append(
                f"{len(self.unexpected)} committed document(s) name a uid the store does not "
                f"hold: {', '.join(self.unexpected[:_MAX_NAMED])}"
                + (f" … and {len(self.unexpected) - _MAX_NAMED} more"
                   if len(self.unexpected) > _MAX_NAMED else "")
            )
        return out


#: How many uids a blocker names before it summarises. Never silently truncated.
_MAX_NAMED = 10


def check_coverage(committed_uids: Iterable[str], store: StateStore) -> CoverageReport:
    """Compare the committed uid set against the store's obligation, both directions.

    ``committed_uids`` comes from the committed tree — read out of git by the caller, not
    re-derived here. That independence is the whole point: a coverage check that rebuilt the
    projection from the store would be comparing the store to itself, which is the defect
    #2042 exists to remove, one layer further out.
    """
    return CoverageReport(
        obliged=projectable_uids(store),
        committed=frozenset(str(uid) for uid in committed_uids),
    )


def build_documents(store: StateStore) -> Dict[str, Dict[str, Any]]:
    """Every **projectable** object as a validated document, keyed by uid.

    Refuses the whole set if any document leaks nondeterministic content or breaks
    the contract — so a bad object cannot leave a half-written projection behind.

    A ``COMPLETE`` object is **archived, not refused** (:data:`ARCHIVED_PHASES`).
    ``COMPLETE`` is derived from merge-to-main (spec §18 decision 1), so a completed
    work item has no legal projection document — and every real store holds them.
    Refusing them would mean no real repo could ever be projected; fabricating a
    phase for them ("it was probably SMOKE") would be the lossy write the migration
    guard exists to prevent. So the projector passes over them: their completion
    lives in the merge commit that caused it, and their record lives in the store.
    A *document* still may not claim ``COMPLETE`` — :func:`validate_document`
    refuses that, and should.
    """
    documents: Dict[str, Dict[str, Any]] = {}
    sourced = source_external_refs(store)
    for obj in projectable_objects(store):
        document = build_document(obj, external_refs=sourced.get(obj.uid))
        assert_deterministic(document, uid=obj.uid)
        validate_document(document)
        documents[obj.uid] = document
    return documents


def object_digest(document: Mapping[str, Any]) -> str:
    """The ``sha256:<hex>`` digest over *one* object's canonical bytes.

    This is the stamp an ``ATDD-Projection-Digest`` trailer carries: trailers are
    grouped per object (spec §5 rule 6), so the digest they pin must be per object too.
    """
    return DIGEST_PREFIX + hashlib.sha256(canonical_bytes(document)).hexdigest()


def digest_documents(documents: Mapping[str, Mapping[str, Any]]) -> str:
    """The ``sha256:<hex>`` digest over the canonical bytes of a document set."""
    hasher = hashlib.sha256()
    for uid in sorted(documents):
        hasher.update(uid.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(canonical_bytes(documents[uid]))
        hasher.update(b"\0")
    return DIGEST_PREFIX + hasher.hexdigest()


def project(store: StateStore, out_dir: Path) -> ProjectionResult:
    """Write the canonical per-uid projection for ``store`` into ``out_dir`` (I1).

    Every document is built and *fully* validated before the first byte is written,
    so a determinism leak or a schema break leaves ``out_dir`` untouched. The same
    logical store yields byte-identical files on any host, in any checkout, on any
    run — the filename is the uid and nothing else.
    """
    documents = build_documents(store)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Path] = {}
    for uid in sorted(documents):
        path = out_dir / f"{uid}{PROJECTION_SUFFIX}"
        path.write_bytes(canonical_bytes(documents[uid]))
        files[uid] = path
    _log.info(
        "projection written",
        extra={"out_dir": str(out_dir), "objects": len(files)},
    )
    return ProjectionResult(out_dir=out_dir, files=files, digest=digest_documents(documents))


# --------------------------------------------------------------------------- #
# hydrate(projection) → store
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HydrateResult:
    """What a :func:`hydrate` run rebuilt."""

    hydrated: int
    uids: List[str] = field(default_factory=list)


def read_projection(
    projection_dir: Path, *, require: bool = False
) -> Dict[str, Dict[str, Any]]:
    """Read and validate every ``<uid>.yaml`` under ``projection_dir``, keyed by uid.

    The filename is identity: a document whose ``uid`` disagrees with the file it
    was read from is a corrupted projection, not a rename, and is refused.

    ``require=True`` refuses an *absent* directory with :class:`MissingProjectionError`
    rather than returning ``{}`` (#1580). Every caller that is about to rebuild or delete
    store state passes it: acting on "no projection exists" as though it were "the
    projection is empty" is the exact confusion that emptied the store on 2026-07-20.

    The default stays permissive because two callers legitimately mean "read whatever is
    there": :func:`atdd.state.tombstone.compact_archive` and :func:`check_canonicality`
    both run against directories that may honestly not exist yet, and neither deletes
    anything on the strength of the answer.
    """
    documents: Dict[str, Dict[str, Any]] = {}
    projection_dir = Path(projection_dir)
    if not projection_dir.is_dir():
        if require:
            _log.warning(
                "required projection directory is absent",
                extra={"projection_dir": str(projection_dir)},
            )
            raise MissingProjectionError(projection_dir)
        return documents
    for path in sorted(projection_dir.glob(f"*{PROJECTION_SUFFIX}"), key=lambda p: p.name):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ProjectionSchemaError(f"{path.name}: not a YAML mapping")
        validate_document(document)
        expected = path.name[: -len(PROJECTION_SUFFIX)]
        if document["uid"] != expected:
            raise ProjectionSchemaError(
                f"{path.name}: uid {document['uid']!r} does not name its file "
                "(the uid alone names the projection file)"
            )
        documents[document["uid"]] = document
    return documents


def _incoming_refs(
    documents: Mapping[str, Mapping[str, Any]],
) -> Dict[Tuple[str, str, str], str]:
    """``(provider, ref_kind, ref_value) -> uid`` for every projected ref the set carries.

    Refuses two documents claiming the same provider identity. That is the *intra-set* half
    of the conflict check; :func:`_refuse_ref_collisions` does the half that matters more.
    """
    incoming: Dict[Tuple[str, str, str], str] = {}
    for uid in sorted(documents):
        refs = documents[uid].get(EXTERNAL_REFS_FIELD) or {}
        for provider, ref_kind in PROJECTED_REF_KINDS:
            subtree = refs.get(provider)
            if not isinstance(subtree, Mapping) or ref_kind not in subtree:
                continue
            key = (provider, ref_kind, str(subtree[ref_kind]))
            claimed = incoming.get(key)
            if claimed is not None and claimed != uid:
                raise ExternalRefConflictError(*key, claimed, uid)
            incoming[key] = uid
    return incoming


@dataclass(frozen=True)
class _RefRestore:
    """One projected ref to write back, with the row data it must not destroy."""

    uid: str
    provider: str
    ref_kind: str
    ref_value: str
    #: The blob the local row already carries, or ``None`` where there is no row yet.
    data: Optional[Dict[str, Any]]


def _plan_ref_restore(
    store: StateStore, incoming: Mapping[Tuple[str, str, str], str],
) -> List[_RefRestore]:
    """Read each incoming ref ONCE — refusing a collision, and keeping what must survive.

    The two things this has to get right both depend on the same row, so it is read once and
    both are derived from it rather than resolving twice:

    - **Refuse a collision.** Checking uniqueness only *within* the incoming set is not
      enough, and was the first version's mistake: the collision that actually happens on an
      ingest is against the refs the LOCAL STORE ALREADY HOLDS. ``link`` would resolve it
      last-writer-wins and re-point a live binding in silence.
    - **Keep the row's ``data`` blob.** ``link`` is ``DO UPDATE SET data=excluded.data`` and
      ``_dumps(None)`` is ``'{}'``, so writing back without it would wipe the provenance on
      1,103 live rows — the same wholesale-replace fault the hydrate exists to repair, one
      table over. The projection carries no opinion about that blob, which is exactly why it
      must not overwrite it.

    Called before the first write, so a refused hydrate leaves the store exactly as it was —
    the same refuse-before-any-write discipline :func:`build_documents` keeps. The plan stays
    valid across the object writes that follow: :meth:`ObjectStore.upsert` does not touch the
    refs table.
    """
    plan: List[_RefRestore] = []
    for (provider, ref_kind, ref_value), uid in sorted(incoming.items()):
        held = store.external_refs.resolve(provider, ref_kind, ref_value)
        if held is not None and held.object_uid != uid:
            raise ExternalRefConflictError(
                provider, ref_kind, ref_value, held.object_uid, uid,
            )
        plan.append(_RefRestore(
            uid=uid, provider=provider, ref_kind=ref_kind, ref_value=ref_value,
            data=dict(held.data) if held is not None else None,
        ))
    return plan


def _restore_external_refs(store: StateStore, plan: Sequence[_RefRestore]) -> None:
    """Write back the projected slice of the refs table (#2025).

    Restores, never deletes. A ref the projection does not name is left alone: the projection
    is authoritative for the objects it carries, not for the ones it does not, and 304 of the
    live work-item refs belong to ``COMPLETE`` objects that :data:`ARCHIVED_PHASES` keeps out
    of it. A hydrate that made the table *match* would delete every one of them on first
    ingest.
    """
    for entry in plan:
        store.external_refs.link(  # noqa: N+1 — one link per projected ref, not a query loop
            entry.uid, entry.provider, entry.ref_kind, entry.ref_value, data=entry.data,
        )


def _carry_stripped_keys_forward(data: Dict[str, Any], existing: Optional[Object]) -> None:
    """Preserve the keys the projection deliberately declined to speak about (#2025).

    A document that omits ``branch`` is not claiming the object has no branch — it is
    declining to have an opinion, because :data:`STRIPPED_AT_PROJECTION` stripped it on the
    way out. :meth:`ObjectStore.upsert` is a wholesale replace, so without this the
    projection's SILENCE about a key deletes it: measured, one cycle took both
    identity-resolving gates from 174/174 to 0/174.

    ``existing`` is ``None`` for an object this store has never seen, where there is by
    definition nothing local to preserve. Mutates ``data`` in place.
    """
    if existing is None:
        return
    for key in STRIPPED_AT_PROJECTION:
        if key in existing.data:
            data[key] = existing.data[key]


def hydrate(projection_dir: Path, store: StateStore) -> HydrateResult:
    """Rebuild the public store objects from the committed projection (E002).

    Runs with **zero** sync providers registered and against no committed SQLite
    store: the committed YAML at HEAD is the only input. This is the read half of
    the CI guarantee — CI hydrates what the branch committed, then re-projects it.

    It is also the inbound half of git-as-transport (#2025): a peer's committed
    projection is hydrated here, so this rebuilds ``store.objects`` **and** the projected
    slice of ``external_refs`` — a hydrated store can resolve an issue number to a uid,
    which is what both identity-resolving gates enter through. It remains *not* disaster
    recovery: the projection carries a defined slice of the store, never all of it, so
    restore from the SQLite store rather than from here.

    Three things this must not do, each of them a wholesale replace that the #1622 ruling's
    CI-only premise let pass unexamined (see the supersession addendum in
    ``docs/1400-findings/1622-projection-authority-ruling.md``):

    - **Delete what it does not speak for.** :meth:`ObjectStore.upsert` replaces the whole
      data bag, so every :data:`STRIPPED_AT_PROJECTION` key is carried forward from the
      object already in the store. A document that omits ``branch`` is declining to have an
      opinion, not asserting the object has none.
    - **Overwrite a ref row's provenance.** The restore preserves the existing ``data`` blob
      — see :func:`_restore_external_refs`.
    - **Resolve a conflict by overwriting it.** An inbound ref claiming an identity the local
      store binds elsewhere raises :class:`ExternalRefConflictError` before the first write.
    """
    documents = read_projection(projection_dir)
    incoming = _incoming_refs(documents)
    restore = _plan_ref_restore(store, incoming)

    for uid in sorted(documents):
        obj_uid, phase, data = document_to_object(documents[uid])
        _carry_stripped_keys_forward(data, store.objects.get(obj_uid))
        store.objects.upsert(  # noqa: N+1 — one upsert per projected object, not a query loop
            obj_uid, WORK_ITEM_KIND, state=phase, data=data,
        )

    _restore_external_refs(store, restore)
    _log.info(
        "projection hydrated",
        extra={"projection_dir": str(projection_dir), "objects": len(documents)},
    )
    return HydrateResult(hydrated=len(documents), uids=sorted(documents))


# --------------------------------------------------------------------------- #
# Digest + canonicality (C002) — the honest CI guarantee
# --------------------------------------------------------------------------- #
def projection_digest(projection_dir: Path) -> str:
    """The ``sha256:<hex>`` digest over the *committed* bytes of a projection directory.

    Taken over the bytes on disk (not a re-serialization), so a hand-edit moves the
    digest. Filenames are folded in too: adding or removing an object changes the
    stamp even when no surviving document changed.
    """
    hasher = hashlib.sha256()
    projection_dir = Path(projection_dir)
    paths = sorted(projection_dir.glob(f"*{PROJECTION_SUFFIX}"), key=lambda p: p.name)
    for path in paths:
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return DIGEST_PREFIX + hasher.hexdigest()


@dataclass(frozen=True)
class Mismatch:
    """One committed file whose bytes are not the canonical output of the round-trip."""

    filename: str
    diff: str


@dataclass(frozen=True)
class CanonicalityReport:
    """The outcome of ``project(hydrate(projection)) == projection``."""

    checked: int
    mismatches: List[Mismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def render(self) -> str:
        """An operator-facing report naming each offending file with its diff."""
        if self.ok:
            return f"projection is canonical ({self.checked} object(s))"
        lines = [f"projection is NOT canonical ({len(self.mismatches)}/{self.checked} file(s)):"]
        for mismatch in self.mismatches:
            lines.append(f"  - {mismatch.filename}")
            lines.extend(f"      {line}" for line in mismatch.diff.splitlines())
        return "\n".join(lines)


def _diff(filename: str, committed: bytes, canonical: bytes) -> str:
    return "".join(
        difflib.unified_diff(
            committed.decode("utf-8", "replace").splitlines(keepends=True),
            canonical.decode("utf-8", "replace").splitlines(keepends=True),
            fromfile=f"committed/{filename}",
            tofile=f"canonical/{filename}",
        )
    )


def _read_bytes(projection_dir: Path) -> Dict[str, bytes]:
    """Every ``<uid>.yaml`` under ``projection_dir`` as raw bytes, keyed by filename."""
    return {
        path.name: path.read_bytes()
        for path in sorted(Path(projection_dir).glob(f"*{PROJECTION_SUFFIX}"), key=lambda p: p.name)
    }


def _mismatches(expected: Mapping[str, bytes], actual: Mapping[str, bytes]) -> List[Mismatch]:
    """Every filename whose bytes differ, each with a unified diff naming the file."""
    return [
        Mismatch(filename=name, diff=_diff(name, blob, actual.get(name, b"")))
        for name, blob in sorted(expected.items())
        if actual.get(name) != blob
    ]


def compare_projections(expected_dir: Path, actual_dir: Path) -> List[Mismatch]:
    """Byte-compare two projection directories (the golden-file check, E003).

    A golden fixture pins the canonical bytes; this reports every file that drifted
    from it, with a diff naming the offending file — so an unintended byte change
    fails loudly instead of drifting silently into a commit.
    """
    return _mismatches(_read_bytes(expected_dir), _read_bytes(actual_dir))


def check_canonicality(projection_dir: Path) -> CanonicalityReport:
    """Prove ``project(hydrate(projection)) == projection``, byte-for-byte (C002).

    This is the *only* guarantee CI can honestly make: it cannot read a gitignored
    developer store, so it takes the round-trip over the committed projection alone.
    The store used here is in-memory — no developer SQLite is touched — and no
    provider is registered or consulted, so the check also holds against a bare git
    remote with no GitHub API reachable.
    """
    projection_dir = Path(projection_dir)
    committed = _read_bytes(projection_dir)
    with MemoryStore() as store, tempfile.TemporaryDirectory() as tmp:
        hydrate(projection_dir, store)
        result = project(store, Path(tmp))
        canonical = {path.name: path.read_bytes() for path in result.files.values()}

    mismatches = _mismatches(committed, canonical)
    if mismatches:
        _log.warning(
            "projection canonicality check failed",
            extra={"projection_dir": str(projection_dir),
                "mismatches": [m.filename for m in mismatches]},
        )
    return CanonicalityReport(checked=len(committed), mismatches=mismatches)


class MemoryStore:
    """An ephemeral, migrated State Store held entirely in memory.

    The canonicality check must touch no developer SQLite (spec §4), so it hydrates
    into RAM and throws the connection away. Shadow runs on the same terms and for the
    same reason, so it uses this one rather than keeping a second copy of it.
    """

    def __enter__(self) -> StateStore:
        from atdd.state.db import apply_migrations  # local: keeps the import surface small

        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        apply_migrations(self._conn)
        return StateStore(self._conn)

    def __exit__(self, *_exc: Any) -> None:
        self._conn.close()

# URN: component:govern-registry:bound-realization-proof:backend:domain
# Runtime: python
# Purpose: Resolve, per rule id, whether a COMPLETE bound provider realization
#          proves that rule — the third proof reverse coherence accepts (#1773).
"""Bound-realization proof resolver (#1773, program #1772).

``coach.rule-id.validator-binding-violation`` requires every enforced rule —
strict, suppress-and-clean AND advisory — to name real, bidirectional, executable
enforcement. That requirement is correct and is NOT weakened here. What is
incomplete is the vocabulary of evidence it accepts, which froze before the
provider substrate existed:

* proof 1 — a literal ``bind_rule("<id>")`` callsite in a core Python validator;
* proof 2 — an executing convention variant (``resolved.is_convention``, #1207),
  admitted by RESOLUTION rather than by inventing a schema;
* proof 3 — THIS MODULE: a complete bound provider realization, admitted by the
  same mechanism.

A LOCK ROW IS NEVER PROOF ON ITS OWN (#1772 Decision 2). ``bound`` may still be
skipped, exempt, unrunnable, semantically inert or non-blocking, so the whole
chain must resolve before anything is discharged::

    rule id (enforced disposition, no core validator)
      -> consumer-local .atdd/binding.lock.yaml exists and parses
      -> its substrate_lock_digest still describes the substrate on disk
      -> exactly ONE entry whose convention_id == rule_id, disposition: bound
      -> exactly ONE implementation manifest for that implementation_id
      -> realizes_convention contains the rule id        (ownership)
      -> emits_rule_ids contains the rule id             (emission)
      -> realizes_convention is a SUBSET of emits_rule_ids
      -> a `report:` channel is declared AND present next to the manifest
      -> the workspace provider CLI resolves for the locked contract
      -> Path B executes it as a BLOCKING gate
      => discharge

Any broken link refuses, under its own name (:data:`REFUSAL_BASES`), so the
failure message says which link broke rather than "not proven".

TWO IDENTITIES ARE ASSERTED, NOT ASSUMED (#1772 Decision 9, upheld on this
condition). ``binding-lock.schema.json`` types ``convention_id`` as
``{"type": "string", "minLength": 1}`` with no rule-id pattern — the identity
``convention_id == rule_id`` holds empirically for 34 of the 62 live entries but
is not schema-guaranteed, so selection here is EXACT equality against the
canonical rule id and never an alias, prefix or case-folded match. And
``realizes_convention ⊆ emits_rule_ids`` is enforced only in
``author_manifest._validate_impl_rule_ids``, i.e. at AUTHOR time, so a
hand-edited manifest bypasses it — it is re-asserted here at READ time.

NO PROVIDER CODE IS IMPORTED. This module reads manifests, locks and workflow
YAML as data, and resolves the provider only to a CLI *path*
(:func:`atdd.enforce.resolution.resolve_provider`). Execution stays
subprocess-only, in the runner (#1772 Decision 4).

NO SECOND VERDICT VOCABULARY IS AUTHORED (#1772 Decisions 16-18). The four
meanings this resolver concludes with — observed-and-satisfied,
observed-and-violated, could-not-observe, and nothing-owed — shipped in #1719 as
``atdd.coach.gate.decision.GateVerdict``. Their MEANINGS are reused; the TYPE is
deliberately not imported, because ``GateVerdict`` belongs to the
transition-gate domain and importing it here would make binding/substrate code
import outward. That is precedent, not workaround: ``decision.py``'s own
docstring records ``planner.interlocking.route_space`` reaching the identical
split independently in its ``NOT_APPLICABLE_BASES`` vocabulary — "unimportable
from here by the purity contract above, same shape". Three call sites, one set
of meanings, no shared type. :data:`OUTCOMES` therefore states the meanings as
plain strings, exactly as ``route_space`` does, and is not an enum.

``NOT_APPLICABLE`` GRANTS NO DISCHARGE. A consumer with no local substrate is
owed nothing by this proof — the BRANCH correctly concludes there is no
obligation here, which is why it does not error. The enforced rule still FAILS
reverse coherence unless proof 1 or proof 2 supplies the evidence. Only
:data:`PROVEN` discharges, which is why :attr:`BoundRealizationProof.discharges`
is stated on the record rather than derived by the caller: an outcome added
later cannot default to "discharge" by omission. ``NOT_APPLICABLE`` is likewise
never counted or described as verified enforcement (#1747).

THE TOOLKIT'S OWN LOCK IS NEVER BORROWED. :meth:`BoundRealizationResolver.for_repo`
is consumer-local only; unlike ``enforce.runner.resolve_substrate_home`` it does
NOT fall back to the toolkit install, because borrowing the toolkit's vendored
lock to claim a consumer-local binding is exactly the false green #1772 forbids.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from atdd.enforce.registry import path_b_is_blocking
from atdd.enforce.resolution import ProviderResolutionError, resolve_provider
from atdd.substrate.binding.composer import realized_conventions
from atdd.substrate.binding.lock_loader import IMPLEMENTATION_MANIFEST
from atdd.substrate.binding.plan import substrate_lock_digest

_log = logging.getLogger(__name__)

__all__ = [
    "OUTCOMES",
    "PROVEN",
    "REFUSED",
    "UNOBSERVABLE",
    "NOT_APPLICABLE",
    "PROVEN_BASIS",
    "REFUSAL_BASES",
    "UNOBSERVABLE_BASES",
    "NOT_APPLICABLE_BASES",
    "BASIS_OUTCOME",
    "BoundRealizationProof",
    "BoundRealizationResolver",
    "IMPLEMENTATION_MANIFEST",
    "LOCK_RELPATH",
    "iter_implementation_manifests",
]


# --------------------------------------------------------------------------- #
# Outcome vocabulary — #1719's MEANINGS, restated; see the module docstring for #
# why the type is not imported and why this is not an enum.                    #
# --------------------------------------------------------------------------- #
#: it looked, and the complete chain resolves — this rule is proven.
PROVEN = "pass"
#: it looked, and a link in the chain is broken — this rule is NOT proven.
REFUSED = "fail"
#: it could not perform the observation (evidence unreadable). Acquisition
#: failure stays DATA and never collapses into a clean result (#1716/#1725).
UNOBSERVABLE = "could_not_check"
#: it looked; there is no obligation here — no consumer-local substrate exists.
#: Grants NO discharge and is never counted as verified enforcement (#1747).
NOT_APPLICABLE = "not_applicable"

#: The closed outcome space. Every proof concludes with exactly one of these.
OUTCOMES: Tuple[str, ...] = (PROVEN, REFUSED, UNOBSERVABLE, NOT_APPLICABLE)

#: The single basis on which a proof succeeds.
PROVEN_BASIS = "complete-bound-realization"

#: Closed vocabulary of REFUSALS — one per link of the chain, so a refusal names
#: which link broke. Ordered as the chain is walked.
REFUSAL_BASES: Tuple[str, ...] = (
    "stale-substrate-digest",
    "no-lock-entry",
    "not-bound",
    "ambiguous-lock-selection",
    "no-implementation-manifest",
    "ambiguous-implementation-selection",
    "ambiguous-convention-ownership",
    "realizes-mismatch",
    "emits-mismatch",
    "ownership-not-emitted",
    "no-report-channel",
    "unresolvable-report",
    "provider-unrunnable",
    "path-b-not-blocking",
)

#: Closed vocabulary of ACQUISITION FAILURES — the evidence exists but could not
#: be read. Transitional: a state to be resolved, not lived in (#1747).
UNOBSERVABLE_BASES: Tuple[str, ...] = (
    "unreadable-lock",
    "unreadable-implementation-manifest",
)

#: Closed vocabulary of NOTHING-OWED. Distinct from ``UNOBSERVABLE_BASES``: a
#: genuinely absent obligation is not a temporarily unresolvable one (#1747).
NOT_APPLICABLE_BASES: Tuple[str, ...] = ("no-local-substrate",)

#: Every basis maps to exactly one outcome. Stated once so a basis added later
#: cannot silently acquire an outcome (and so the fault matrix can assert the
#: pairing rather than restate it).
BASIS_OUTCOME: Dict[str, str] = {
    PROVEN_BASIS: PROVEN,
    **{b: REFUSED for b in REFUSAL_BASES},
    **{b: UNOBSERVABLE for b in UNOBSERVABLE_BASES},
    **{b: NOT_APPLICABLE for b in NOT_APPLICABLE_BASES},
}


LOCK_RELPATH = Path(".atdd") / "binding.lock.yaml"

#: Where vendored implementation manifests live under a substrate home. Both
#: trees are searched: a workspace package ships the detectors for its own
#: runtime, and an EXTENSION may ship its own detectors targeting that
#: workspace's provider contract (the train-interlocking extension does).
#: Searching only ``.atdd/workspaces`` is the omission that made every
#: extension-shipped detector invisible in #1359.
_SUBSTRATE_TREES: Tuple[str, ...] = ("workspaces", "extensions")

_BOUND = "bound"
_REPORT_FIELD = "report"


# --------------------------------------------------------------------------- #
# Result record                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BoundRealizationProof:
    """What the bound-realization chain concluded for ONE rule id.

    ``basis`` names the link that decided the outcome — the one that resolved
    the whole chain (:data:`PROVEN_BASIS`) or the one that broke. ``detail`` is
    the operator-facing sentence; a refusal an operator cannot act on is only
    marginally better than the vacuous pass it replaces.
    """

    rule_id: str
    outcome: str
    basis: str
    detail: str
    implementation_id: Optional[str] = None
    workspace_id: Optional[str] = None
    manifest_path: Optional[Path] = None

    def __post_init__(self) -> None:
        expected = BASIS_OUTCOME.get(self.basis)
        if expected is None:
            raise ValueError(
                f"bound-realization proof for {self.rule_id!r} was built with "
                f"basis {self.basis!r}, which is not in the closed vocabulary. "
                f"Add it to REFUSAL_BASES / UNOBSERVABLE_BASES / "
                f"NOT_APPLICABLE_BASES (and therefore to BASIS_OUTCOME) so its "
                f"outcome is stated rather than assumed."
            )
        if expected != self.outcome:
            raise ValueError(
                f"bound-realization proof for {self.rule_id!r} pairs basis "
                f"{self.basis!r} with outcome {self.outcome!r}, but that basis "
                f"means {expected!r}. The two representations of one fact must "
                f"not disagree."
            )

    @property
    def discharges(self) -> bool:
        """Whether this proof discharges reverse coherence for the rule.

        Stated on the record rather than in the caller so an outcome added later
        cannot default to "discharge" by omission — the same reason #1719 states
        ``blocks`` on the verdict. ONLY :data:`PROVEN` discharges:
        :data:`NOT_APPLICABLE` establishes that this branch is owed nothing, which
        is not the same as the rule being proven, and :data:`UNOBSERVABLE` is an
        acquisition failure that must stay visible rather than pass silently.
        """
        return self.outcome == PROVEN

    @property
    def verified(self) -> bool:
        """Whether this proof may be COUNTED as verified enforcement (#1747).

        Congruent with :attr:`discharges` today and separate on purpose: it is
        the predicate a report must consult before writing "proven"/"verified",
        so a ``NOT_APPLICABLE`` branch can never be tallied as enforcement that
        was checked. ``decision.py``'s ``passed_checks`` excludes
        ``NOT_APPLICABLE`` for the same reason; this issue must not reintroduce
        the collapse.
        """
        return self.outcome == PROVEN


# --------------------------------------------------------------------------- #
# Manifest reading (pure data — no implementation module is ever imported)     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Manifest:
    implementation_id: str
    realizes: Tuple[str, ...]
    emits: Tuple[str, ...]
    report: Optional[str]
    path: Path
    #: Whether ``emits_rule_ids`` is absent from the manifest entirely, as
    #: distinct from declared-and-empty. Both refuse — a rule id is in neither —
    #: but they are different authoring mistakes and the refusal says which.
    #: The absent case is the v1.0 exit-code shape, which
    #: ``author_manifest._validate_impl_rule_ids`` still accepts at author time
    #: (``emits_rule_ids`` OR ``realizes_convention``, at least one). Proof needs
    #: the v1.1 emission claim, so such a manifest is not proof — see the
    #: ``emits-mismatch`` message.
    emits_declared: bool = True


class _UnreadableManifest(Exception):
    """A manifest exists on disk but could not be parsed (acquisition failure)."""

    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__(f"{path}: {cause}")
        self.path = path


def _as_str_list(value: object) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return ()


def iter_implementation_manifests(substrate_home: Path) -> List[_Manifest]:
    """Every vendored ``atdd.implementation.yaml`` under a substrate home.

    Reads YAML only — the implementation module behind ``entrypoint`` is never
    imported, so core stays free of provider code (#1772 Decision 4). Raises
    :class:`_UnreadableManifest` rather than skipping a malformed manifest: a
    manifest that cannot be read is an acquisition failure to report, not an
    absent one to silently treat as clean (#1716/#1725).
    """
    out: List[_Manifest] = []
    for tree in _SUBSTRATE_TREES:
        root = Path(substrate_home) / ".atdd" / tree
        if not root.is_dir():
            continue
        for mp in sorted(root.rglob(IMPLEMENTATION_MANIFEST)):
            try:
                data = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                raise _UnreadableManifest(mp, exc) from exc
            if not isinstance(data, dict) or data.get("kind") != "implementation":
                continue
            impl_id = data.get("implementation_id")
            if not impl_id:
                continue
            report = data.get(_REPORT_FIELD)
            out.append(
                _Manifest(
                    implementation_id=str(impl_id),
                    realizes=tuple(realized_conventions(data)),
                    emits=_as_str_list(data.get("emits_rule_ids")),
                    report=str(report) if report else None,
                    path=mp,
                    emits_declared="emits_rule_ids" in data,
                )
            )
    return out


# --------------------------------------------------------------------------- #
# The resolver                                                                #
# --------------------------------------------------------------------------- #
class BoundRealizationResolver:
    """Per-rule bound-realization proof over ONE consumer-local substrate.

    Construct once per validation pass: the lock and the manifest set are read
    lazily and then cached, so a registry-wide sweep costs one lock read and one
    manifest walk rather than one per rule.

    The resolver is a PURE READ. It never writes, never spawns a provider, and
    never imports one.
    """

    def __init__(self, substrate_home: Path, repo_root: Optional[Path] = None) -> None:
        #: Where ``.atdd/binding.lock.yaml`` and the vendored trees live.
        self.substrate_home = Path(substrate_home)
        #: Where the CI workflow lives (the Path-B blocking leg). Defaults to the
        #: substrate home, which is the same directory in a normal checkout.
        self.repo_root = Path(repo_root) if repo_root is not None else self.substrate_home
        self._lock: Optional[dict] = None
        self._lock_error: Optional[str] = None
        self._lock_read = False
        self._manifests: Optional[List[_Manifest]] = None
        self._manifest_error: Optional[str] = None
        self._path_b: Optional[bool] = None
        self._cache: Dict[str, BoundRealizationProof] = {}

    # -- construction ------------------------------------------------------- #
    @classmethod
    def for_repo(cls, repo_root: Path) -> "BoundRealizationResolver":
        """Bind to ``repo_root``'s OWN substrate — never the toolkit's.

        Deliberately unlike :func:`atdd.enforce.runner.resolve_substrate_home`,
        which falls back to the toolkit install so an un-bound consumer still
        gets the toolkit's bound rules enforced over its code. That fallback is
        right for enforcement and wrong for proof: borrowing the toolkit's
        vendored lock to claim a CONSUMER-local binding would manufacture
        discharges for rules the consumer never configured — the false green
        #1772 exists to remove. With no local lock the answer is
        ``NOT_APPLICABLE``, and ``NOT_APPLICABLE`` discharges nothing.
        """
        root = Path(repo_root)
        return cls(substrate_home=root, repo_root=root)

    # -- lazy evidence ------------------------------------------------------ #
    @property
    def lock_path(self) -> Path:
        return self.substrate_home / LOCK_RELPATH

    def _read_lock(self) -> None:
        if self._lock_read:
            return
        self._lock_read = True
        path = self.lock_path
        if not path.is_file():
            return  # no local substrate — NOT_APPLICABLE, decided by the caller
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            self._lock_error = f"{path} could not be read: {exc}"
            return
        if not isinstance(data, dict):
            self._lock_error = f"{path} is not a mapping"
            return
        self._lock = data

    def _read_manifests(self) -> None:
        if self._manifests is not None or self._manifest_error is not None:
            return
        try:
            self._manifests = iter_implementation_manifests(self.substrate_home)
        except _UnreadableManifest as exc:
            self._manifest_error = str(exc)

    def _path_b_blocking(self) -> bool:
        if self._path_b is None:
            self._path_b = bool(path_b_is_blocking(self.repo_root))
        return self._path_b

    # -- public API --------------------------------------------------------- #
    def proof_for(self, rule_id: str) -> BoundRealizationProof:
        """Resolve the complete chain for ``rule_id``. Cached per rule."""
        cached = self._cache.get(rule_id)
        if cached is None:
            cached = self._resolve(rule_id)
            self._cache[rule_id] = cached
        return cached

    def discharges(self, rule_id: str) -> bool:
        """Whether a complete bound realization proves ``rule_id``.

        The one-line predicate reverse coherence consults. False for every
        non-``PROVEN`` outcome, including ``NOT_APPLICABLE``.
        """
        return self.proof_for(rule_id).discharges

    # -- the chain ---------------------------------------------------------- #
    def _resolve(self, rule_id: str) -> BoundRealizationProof:
        def concluded(basis: str, detail: str, **extra) -> BoundRealizationProof:
            return BoundRealizationProof(
                rule_id=rule_id,
                outcome=BASIS_OUTCOME[basis],
                basis=basis,
                detail=detail,
                **extra,
            )

        # 1. Is there a consumer-local substrate at all?
        self._read_lock()
        if self._lock is None and self._lock_error is None:
            return concluded(
                "no-local-substrate",
                f"no consumer-local {LOCK_RELPATH} under {self.substrate_home} — "
                f"this branch is owed no provider proof. It grants NO discharge: "
                f"the rule still needs a bind_rule binding or a convention variant.",
            )
        if self._lock_error is not None:
            return concluded("unreadable-lock", self._lock_error)

        assert self._lock is not None  # narrowed by the two branches above

        # 2. Does the lock still describe the substrate on disk? A lock that has
        #    drifted from its substrate is not evidence about that substrate.
        recorded = self._lock.get("substrate_lock_digest")
        actual = substrate_lock_digest(self.substrate_home)
        if recorded != actual:
            return concluded(
                "stale-substrate-digest",
                f"{self.lock_path} records substrate_lock_digest {recorded!r} but "
                f"the substrate on disk digests to {actual!r} — the lock no longer "
                f"describes this substrate, so it proves nothing about it (and "
                f"nothing else reads this key, so the drift is otherwise silent). "
                f"Re-run `atdd bind --check`.",
            )

        # 3. EXACT selection on the asserted identity convention_id == rule_id.
        #    The schema types convention_id as a free minLength:1 string, so this
        #    equality is checked, never inferred — and never matched on an alias,
        #    prefix or case-folded form.
        conventions = self._lock.get("conventions")
        conventions = conventions if isinstance(conventions, list) else []
        entries = [
            c
            for c in conventions
            if isinstance(c, dict) and c.get("convention_id") == rule_id
        ]
        if not entries:
            return concluded(
                "no-lock-entry",
                f"no binding-lock entry whose convention_id is exactly {rule_id!r} "
                f"({len(conventions)} entr(y/ies) present) — no implementation is "
                f"selected for this rule.",
            )
        if len(entries) > 1:
            return concluded(
                "ambiguous-lock-selection",
                f"{len(entries)} binding-lock entries claim convention_id "
                f"{rule_id!r}; exactly one implementation must be selected for a "
                f"convention. Resolve the duplicate before this rule can be proven.",
            )
        entry = entries[0]

        # 4. Selected, but is it BOUND? `legacy-fallback` says the opposite.
        disposition = entry.get("disposition")
        if disposition != _BOUND:
            return concluded(
                "not-bound",
                f"binding-lock entry for {rule_id!r} has disposition "
                f"{disposition!r}, not {_BOUND!r} — no provider owns its gating.",
            )
        implementation_id = str(entry.get("implementation_id") or "")
        workspace_id = str(entry.get("workspace_id") or "")
        contract = str(entry.get("contract_version") or "1.0.0")
        located = {
            "implementation_id": implementation_id or None,
            "workspace_id": workspace_id or None,
        }

        # 5. The EXACT implementation manifest for that implementation_id.
        self._read_manifests()
        if self._manifest_error is not None:
            return concluded(
                "unreadable-implementation-manifest", self._manifest_error, **located
            )
        manifests = self._manifests or []
        candidates = [m for m in manifests if m.implementation_id == implementation_id]
        if not candidates:
            return concluded(
                "no-implementation-manifest",
                f"binding-lock selects implementation {implementation_id!r} for "
                f"{rule_id!r}, but no {IMPLEMENTATION_MANIFEST} under "
                f"{self.substrate_home}/.atdd/{{{','.join(_SUBSTRATE_TREES)}}} "
                f"declares that implementation_id.",
                **located,
            )
        if len(candidates) > 1:
            return concluded(
                "ambiguous-implementation-selection",
                f"{len(candidates)} manifests declare implementation_id "
                f"{implementation_id!r} ("
                f"{', '.join(str(m.path) for m in candidates)}) — the selection is "
                f"ambiguous, so no exact realization can be proven.",
                **located,
            )
        manifest = candidates[0]
        located["manifest_path"] = manifest.path

        # 6. Ownership must be unambiguous across the whole substrate: two
        #    implementations realizing one convention is the DuplicateConventionError
        #    the composer raises at compose time, re-asserted here at read time.
        owners = [m for m in manifests if rule_id in m.realizes]
        if len(owners) > 1:
            return concluded(
                "ambiguous-convention-ownership",
                f"{len(owners)} implementations claim to realize {rule_id!r} ("
                f"{', '.join(sorted(m.implementation_id for m in owners))}) — an "
                f"ambiguous binding the operator must resolve; no single "
                f"realization owns this rule.",
                **located,
            )

        # 7. The reverse direction: the manifest must back-reference the rule.
        if rule_id not in manifest.realizes:
            return concluded(
                "realizes-mismatch",
                f"implementation {implementation_id!r} is selected for {rule_id!r} "
                f"but its realizes_convention is {list(manifest.realizes)!r} — it "
                f"does not claim to own this rule, so the lock's selection is "
                f"unreciprocated.",
                **located,
            )

        # 8. Ownership is not emission: a detector may OWN a convention it never
        #    EMITS, and such a realization can never produce a finding for it.
        if rule_id not in manifest.emits:
            if not manifest.emits_declared:
                shape = (
                    "declares no emits_rule_ids at all (the v1.0 exit-code shape, "
                    "which author_manifest still accepts because it requires "
                    "emits_rule_ids OR realizes_convention)"
                )
            else:
                shape = f"declares emits_rule_ids={list(manifest.emits)!r}"
            return concluded(
                "emits-mismatch",
                f"implementation {implementation_id!r} realizes {rule_id!r} but "
                f"{shape} — nothing states it can emit a violation under this exact "
                f"rule id, so it is not proof that this rule is enforced. Ownership "
                f"is not emission.",
                **located,
            )

        # 9. Re-assert the whole author-time invariant at READ time. Today
        #    `realizes_convention ⊆ emits_rule_ids` is checked only in
        #    author_manifest._validate_impl_rule_ids, so a hand-edited manifest
        #    bypasses it entirely (#1772 Decision 6).
        unemitted = [c for c in manifest.realizes if c not in manifest.emits]
        if unemitted:
            return concluded(
                "ownership-not-emitted",
                f"manifest {manifest.path} realizes {unemitted!r} without emitting "
                f"them (emits_rule_ids={list(manifest.emits)!r}). "
                f"realizes_convention must be a subset of emits_rule_ids; this is "
                f"enforced at author time only, so a hand-edited manifest reaches "
                f"here — and a manifest that claims ownership it cannot emit is "
                f"not proof for ANY rule it declares.",
                **located,
            )

        # 10. A structured report channel must be DECLARED and PRESENT — this is
        #     the runnable-detection the vendored cli/scan.py performs.
        if not manifest.report:
            return concluded(
                "no-report-channel",
                f"manifest {manifest.path} declares no {_REPORT_FIELD!r} channel — "
                f"the detector has no v1.1 report emitter, so nothing it observes "
                f"can reach a verdict.",
                **located,
            )
        report_path = manifest.path.parent / manifest.report
        if not report_path.is_file():
            return concluded(
                "unresolvable-report",
                f"manifest {manifest.path} declares report {manifest.report!r}, but "
                f"{report_path} does not exist — the channel is named, not present.",
                **located,
            )

        # 11. Runnability: the workspace provider CLI must resolve for the locked
        #     contract. Resolution yields a PATH; core never imports or runs it here.
        candidate_roots = [
            self.substrate_home / ".atdd" / tree for tree in _SUBSTRATE_TREES
        ] + [self.substrate_home / ".atdd"]
        try:
            resolve_provider(candidate_roots, workspace_id, f"^{contract}")
        except ProviderResolutionError as exc:
            return concluded(
                "provider-unrunnable",
                f"workspace provider {workspace_id!r} (contract ^{contract}) for "
                f"{rule_id!r} does not resolve to a runnable CLI: {exc}",
                **located,
            )

        # 12. Bound, exact, reciprocated and runnable is still not enforcement
        #     unless Path B actually blocks (#1772 Decision 2).
        if not self._path_b_blocking():
            return concluded(
                "path-b-not-blocking",
                f"the realization for {rule_id!r} is complete, but Path B "
                f"(`atdd enforce`) does not run as a BLOCKING CI gate in "
                f"{self.repo_root}/.github/workflows/atdd-validate.yml — a "
                f"realization nothing blocks on cannot be the proof that an "
                f"enforced rule is enforced.",
                **located,
            )

        return concluded(
            PROVEN_BASIS,
            f"{rule_id!r} is realized by implementation {implementation_id!r} "
            f"(workspace {workspace_id!r}, contract {contract}): selected bound in "
            f"the digest-coherent binding lock, back-referenced in "
            f"realizes_convention, emitted in emits_rule_ids, reporting through "
            f"{manifest.report!r}, runnable, and blockingly executed by Path B.",
            **located,
        )

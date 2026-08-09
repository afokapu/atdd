# URN: component:govern-registry:bound-realization-proof:backend:domain
# Runtime: python
# Purpose: Resolve, per rule id, whether a COMPLETE bound provider realization
#          proves that rule — the third proof reverse coherence accepts (#1773).
"""Bound-realization proof resolver (#1773, program #1772).

``coach.rule-id.validator-binding-violation`` requires every enforced rule —
strict, suppress-and-clean AND advisory — to name real, bidirectional, executable
enforcement. That requirement is correct and is NOT weakened here. What was
incomplete is the vocabulary of EVIDENCE it accepts, which froze before the
provider substrate existed:

* proof 1 — a literal ``bind_rule("<id>")`` callsite in a core Python validator;
* proof 2 — an executing convention variant (``resolved.is_convention``, #1207),
  admitted by RESOLUTION rather than by inventing a schema;
* proof 3 — THIS MODULE: a complete bound provider realization, admitted by the
  same mechanism.

A LOCK ROW IS NEVER PROOF ON ITS OWN (#1772 Decision 2). ``bound`` may still be
skipped, exempt, unrunnable, semantically inert or non-blocking, so the whole
twelve-link chain must resolve before anything is discharged. The links live in
:mod:`atdd.coach.validators._bound_realization_chain`, one short function each;
any broken link refuses under its own name, so the failure says WHICH link broke
rather than "not proven".

TWO IDENTITIES ARE ASSERTED, NOT ASSUMED (#1772 Decision 9, upheld on this
condition). ``binding-lock.schema.json`` types ``convention_id`` as
``{"type": "string", "minLength": 1}`` with no rule-id pattern — the identity
``convention_id == rule_id`` holds empirically for 34 of the 62 live entries but
is not schema-guaranteed, so selection is EXACT equality against the canonical
rule id and never an alias, prefix or case-folded match. And
``realizes_convention ⊆ emits_rule_ids`` is enforced only in
``author_manifest._validate_impl_rule_ids``, i.e. at AUTHOR time, so a
hand-edited manifest bypasses it — it is re-asserted here at READ time.

NO PROVIDER CODE IS IMPORTED. Manifests, locks and workflow YAML are read as
data, and the provider is resolved only to a CLI *path*. Execution stays
subprocess-only, in the runner (#1772 Decision 4).

NO SECOND VERDICT VOCABULARY IS AUTHORED (#1772 Decisions 16-18). The four
meanings this resolver concludes with shipped in #1719 as
``atdd.coach.gate.decision.GateVerdict``. Their MEANINGS are reused; the TYPE is
deliberately not imported, because ``GateVerdict`` belongs to the transition-gate
domain and importing it here would make binding/substrate code import outward.
That is precedent, not workaround: ``decision.py``'s own docstring records
``planner.interlocking.route_space`` reaching the identical split independently
in its ``NOT_APPLICABLE_BASES`` vocabulary — "unimportable from here by the purity
contract above, same shape". Three call sites, one set of meanings, no shared
type. :data:`OUTCOMES` therefore states the meanings as plain strings, exactly as
``route_space`` does, and is NOT an enum.

``NOT_APPLICABLE`` GRANTS NO DISCHARGE. A consumer with no local substrate is
owed nothing by this proof — the BRANCH correctly concludes there is no
obligation here, which is why it does not error. The enforced rule still FAILS
reverse coherence unless proof 1 or proof 2 supplies the evidence. Only
:data:`PROVEN` discharges, which is why :attr:`BoundRealizationProof.discharges`
is stated on the record rather than derived by the caller: an outcome added later
cannot default to "discharge" by omission. ``NOT_APPLICABLE`` is likewise never
counted or described as verified enforcement (#1747).

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

from atdd.coach.validators._bound_realization_chain import (
    Manifest,
    UnreadableManifestError,
    iter_implementation_manifests,
    walk,
)
from atdd.enforce.registry import path_b_is_blocking

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
    "Manifest",
    "UnreadableManifestError",
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
#: cannot silently acquire an outcome.
BASIS_OUTCOME: Dict[str, str] = {
    PROVEN_BASIS: PROVEN,
    **{b: REFUSED for b in REFUSAL_BASES},
    **{b: UNOBSERVABLE for b in UNOBSERVABLE_BASES},
    **{b: NOT_APPLICABLE for b in NOT_APPLICABLE_BASES},
}

LOCK_RELPATH = Path(".atdd") / "binding.lock.yaml"


# --------------------------------------------------------------------------- #
# Result record                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BoundRealizationProof:
    """What the bound-realization chain concluded for ONE rule id.

    ``basis`` names the link that decided the outcome — the one that resolved the
    whole chain (:data:`PROVEN_BASIS`) or the one that broke. ``detail`` is the
    operator-facing sentence; a refusal an operator cannot act on is only
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

        Congruent with :attr:`discharges` today and separate on purpose: it is the
        predicate a report must consult before writing "proven"/"verified", so a
        ``NOT_APPLICABLE`` branch can never be tallied as enforcement that was
        checked. ``decision.py``'s ``passed_checks`` excludes ``NOT_APPLICABLE``
        for the same reason; this issue must not reintroduce the collapse.
        """
        return self.outcome == PROVEN


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
        #: substrate home, the same directory in a normal checkout.
        self.repo_root = Path(repo_root) if repo_root is not None else self.substrate_home
        self._lock: Optional[dict] = None
        self._lock_error: Optional[str] = None
        self._lock_read = False
        self._manifests: Optional[List[Manifest]] = None
        self._manifest_error: Optional[str] = None
        self._path_b: Optional[bool] = None
        self._cache: Dict[str, BoundRealizationProof] = {}

    @classmethod
    def for_repo(cls, repo_root: Path) -> "BoundRealizationResolver":
        """Bind to ``repo_root``'s OWN substrate — never the toolkit's.

        Deliberately unlike :func:`atdd.enforce.runner.resolve_substrate_home`,
        which falls back to the toolkit install so an un-bound consumer still gets
        the toolkit's bound rules enforced over its code. That fallback is right
        for enforcement and wrong for proof: borrowing the toolkit's vendored lock
        to claim a CONSUMER-local binding would manufacture discharges for rules
        the consumer never configured — the false green #1772 exists to remove.
        With no local lock the answer is ``NOT_APPLICABLE``, and
        ``NOT_APPLICABLE`` discharges nothing.
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
            return  # no local substrate — NOT_APPLICABLE, decided by the chain
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            # An unreadable lock is an acquisition failure that must stay visible:
            # it becomes a `could_not_check` proof rather than a clean refusal, and
            # it is logged so it stays diagnosable when only the outcome is shown.
            self._lock_error = f"{path} could not be read: {exc}"
            _log.warning(
                "binding lock unreadable — bound-realization proof is unobservable",
                extra={"lock_path": str(path), "error_type": type(exc).__name__},
            )
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
        except UnreadableManifestError as exc:
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
            cached = walk(rule_id, self)
            self._cache[rule_id] = cached
        return cached

    def discharges(self, rule_id: str) -> bool:
        """Whether a complete bound realization proves ``rule_id``.

        The one-line predicate reverse coherence consults. False for every
        non-``PROVEN`` outcome, including ``NOT_APPLICABLE``.
        """
        return self.proof_for(rule_id).discharges

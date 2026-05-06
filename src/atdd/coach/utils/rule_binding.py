# URN: component:govern-lifecycle:enforcement-substrate:rule_binding:backend:domain
# Runtime: python
# Purpose: Bind rule metadata from convention YAML at module-import time so validators stop redeclaring RULE_SEVERITY/RULE_ID constants.

"""Runtime rule-metadata binding (issue #388).

Validators previously hardcoded their rule's severity and description as
module-level constants alongside the convention's authoritative declaration.
That dual declaration drifts: a convention bump to severity 5 leaves the
validator emitting at severity 4 forever.

``bind_rule(rule_id)`` walks every ``*.convention.yaml`` under the toolkit
search roots, locates the matching ``rules:`` entry, and returns a
``RuleMetadata`` view.  Validators call it once at module-import time:

    _RULE = bind_rule("coder.logging.coach-silent-swallow")

If the rule is unregistered or appears in two convention files, the call
raises at import — the failure surfaces immediately rather than later in a
silently mis-routed ``Violation`` emission.

Related substrate:

* ``src/atdd/coach/validators/_violation.py`` — consumes ``fix_hint_ref``.
* ``src/atdd/coach/specs/rule-id.spec.md`` — grammar and lifecycle.
* ``src/atdd/coach/conventions/rule-id.convention.yaml`` — DOMAIN registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

import atdd


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class RuleNotInRegistryError(LookupError):
    """Raised when ``bind_rule`` cannot find the rule_id in any convention."""


class AmbiguousRuleError(LookupError):
    """Raised when a rule_id appears in more than one convention file."""


class AmbiguousAliasError(LookupError):
    """Raised when a legacy alias collides with another rule's canonical id or alias."""


class RepoYamlValidationError(ValueError):
    """Raised when a repo plan/ YAML violates the substrate's structural rules.

    Surfaces (a) ``disposition:`` declared in repo YAML (walker sets it per
    spec v12 §4.4); (b) literal ``id:`` field at the top of an acceptance
    block (rule-id is derived per §3.3 — declaring it is misleading);
    (c) acceptance URN that fails ``URNBuilder.PATTERNS['acc']``;
    (d) derived rule-id that fails the canonical-archetype + grammar check.
    """


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuleMetadata:
    """Read-only view of a single rule's authoritative declaration.

    Attributes:
        rule_id: Canonical namespaced ID (``<archetype>.<convention>.<rule>``).
        severity: Integer 1-5 from the convention (mirrors
            ``Violation.severity``).
        description: One-line human-readable rule statement.
        disposition: Per-rule CI policy (``strict`` / ``suppress-and-clean``
            / ``advisory`` / ``documentation-only``) or ``None`` for
            unmigrated entries.
        validator: Bidirectional back-reference of form
            ``<module_basename>::<function_name>``, or ``None``.
        fix_hint: Canonical remediation guidance for this rule, or ``None``.
        aliases: Legacy rule ids (typically flat-grammar) this canonical
            rule supersedes; empty tuple when none.
        recipe: Bare peer-recipe filename (no ``.recipe.yaml`` suffix), or
            ``None`` if the convention has no ``recipe:`` field.
        introduced_in: Toolkit version string that first published the rule,
            or ``None``.
        source_path: Absolute path to the convention file that declared the
            rule.  Used in ``AmbiguousRuleError`` messages.

    Substrate-added fields (issue #407, spec v12 §4.1) — discriminator /
    graph-resolution pointers and authoring context. All default to ``None``
    so toolkit rules predating the substrate are unaffected; repo-scope rules
    populate them on construction.

        acceptance_urn: Acceptance criterion this rule enforces.
        wmbt_urn: WMBT (What Must Be True) criterion linkage.
        train_urn: Train (release journey) the rule belongs to.
        security_urn: Security control / policy the rule enforces.
        feature_urn: Feature the rule scopes to.
        bound_acceptance_urn: Graph-resolvable URN bound at registry-load
            time. Distinct from ``fix_hint_ref`` (a remediation pointer) and
            from the YAML-source ``acceptance_ref`` opaque pointer string —
            this field is the resolved URN form (per §4.1).
        phase: ATDD lifecycle phase pin (``RED``/``GREEN``/``SMOKE``/
            ``REFACTOR``) when applicable.
        harness_type: Test harness type the rule expects.
        harness_category: Coarse-grained harness category.
        signal_metric: Telemetry metric the rule produces / consumes.
        signal_threshold: Threshold against which ``signal_metric`` is judged.
        given: Authoring-time precondition prose.
        when: Authoring-time stimulus prose.
        then: Authoring-time expectation prose.
        author: Rule author identifier.
        created: ISO date the rule entry was created.
    """

    rule_id: str
    severity: int
    description: str
    recipe: Optional[str]
    introduced_in: Optional[str]
    source_path: Path
    disposition: Optional[str] = None
    validator: Optional[str] = None
    fix_hint: Optional[str] = None
    aliases: Tuple[str, ...] = ()
    acceptance_urn: Optional[str] = None
    wmbt_urn: Optional[str] = None
    train_urn: Optional[str] = None
    security_urn: Optional[str] = None
    feature_urn: Optional[str] = None
    bound_acceptance_urn: Optional[str] = None
    phase: Optional[str] = None
    harness_type: Optional[str] = None
    harness_category: Optional[str] = None
    signal_metric: Optional[str] = None
    signal_threshold: Optional[str] = None
    given: Optional[str] = None
    when: Optional[str] = None
    then: Optional[str] = None
    author: Optional[str] = None
    created: Optional[str] = None

    @property
    def fix_hint_ref(self) -> Optional[str]:
        """Structured pointer for ``Violation.fix_hint_ref``.

        Returns ``"recipe:{recipe}"`` when ``recipe`` is set on the
        convention entry, else ``None``.  The shape matches the format
        documented in ``_violation.py``.
        """
        if self.recipe:
            return f"recipe:{self.recipe}"
        return None


# ---------------------------------------------------------------------------
# Convention search roots
# ---------------------------------------------------------------------------
# `atdd.__file__` points at the package directory under both install shapes:
#   * pip-installed:  <site-packages>/atdd/__init__.py
#   * editable / src-checkout:  <repo>/src/atdd/__init__.py
# So a single root is sufficient — see SPEC-COACH-PKG-LAYOUT-001 (#367).
_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


def _default_roots() -> List[Path]:
    """Search roots for ``*.convention.yaml`` files (deduped at walk time)."""
    return [_ATDD_PKG_DIR]


# ---------------------------------------------------------------------------
# Walker (lifted out of test_rule_id_uniqueness.py so both consumers share one)
# ---------------------------------------------------------------------------
def _is_structured_rule(item) -> bool:
    """A structured rule is a dict with an ``id`` field.

    Distinguishes from legacy prose ``rules:`` arrays whose items are bare
    strings.
    """
    return isinstance(item, dict) and "id" in item


def _walk_rules(
    node, path_parts: Tuple[str, ...]
) -> Iterable[Tuple[Tuple[str, ...], Dict]]:
    """Recursively yield ``(yaml_path, rule_dict)`` for every structured rule."""
    if isinstance(node, dict):
        for key, value in node.items():
            new_path = path_parts + (str(key),)
            if key == "rules" and isinstance(value, list):
                for idx, item in enumerate(value):
                    if _is_structured_rule(item):
                        yield (new_path + (str(idx),), item)
            else:
                yield from _walk_rules(value, new_path)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            yield from _walk_rules(item, path_parts + (str(idx),))


def extract_rules(
    file_path: Path,
) -> List[Tuple[Path, Tuple[str, ...], Dict]]:
    """Return ``(file, yaml_path, rule_dict)`` for every structured rule in *file_path*."""
    try:
        with open(file_path) as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Unreadable / malformed YAML is policed by test_rule_id_uniqueness;
        # bind_rule treats such files as empty so a single broken convention
        # does not break the entire registry walk.
        return []
    if data is None:
        return []
    return [(file_path, p, r) for (p, r) in _walk_rules(data, ())]


def find_convention_files(
    roots: Optional[Iterable[Path]] = None,
) -> List[Path]:
    """Walk *roots* for ``*.convention.yaml`` files (deduped by resolved path).

    When *roots* is ``None``, the default toolkit search roots are used
    (installed package + ``src/atdd`` checkout).  Both the rule-id
    uniqueness validator and ``bind_rule`` consume this function so the
    discovery rules stay in one place.
    """
    seen: Dict[str, Path] = {}
    for root in roots if roots is not None else _default_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*.convention.yaml"):
            if "__pycache__" in path.parts:
                continue
            seen[str(path.resolve())] = path
    return sorted(seen.values())


# ---------------------------------------------------------------------------
# Repo-rule walker (substrate spec v12 §3.3, §4.2, §4.3, §4.4 — issue #408)
# ---------------------------------------------------------------------------
# Pattern matching the WMBT-shaped acceptance body inside an `acc:` URN:
#   <WMBT-id>-<HARNESS>-<NNN>(-<slug>)?
# The HARNESS list mirrors URNBuilder.HARNESS_CODES.
_WMBT_ACC_BODY_RE = re.compile(
    r"^([DLPCEMYRK][0-9]{3})-"
    r"(UNIT|HTTP|EVENT|WS|E2E|A11Y|VIS|METRIC|JOB|DB|SEC|LOAD|SCRIPT|"
    r"WIDGET|GOLDEN|BLOC|INTEGRATION|RLS|EDGE|REALTIME|STORAGE)-"
    r"([0-9]{3})(?:-([a-z0-9-]+))?$"
)

# Canonical rule-id grammar (mirrors
# ``src/atdd/coach/validators/test_rule_id_uniqueness.py::RULE_ID_PATTERN``).
# Repeated here so the walker can validate without circular-importing the
# validator module.
_RULE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)

# Repo-derived rule-id grammar — looser than the toolkit grammar in the
# rule-name segment to permit the WMBT step-letter prefix (e.g. ``D010-``)
# that the spec example preserves verbatim. Still enforces:
#   - archetype == "repo"
#   - <wagon-or-train> is a kebab-case identifier (digit-leading allowed for
#     train ids like 0001-self-compliance-validate)
#   - rule-name body matches one of two derived shapes:
#       (a) WMBT: ``<WMBT-id>-acc-<harness>-<NNN>``  (WMBT-id is uppercase
#           step-letter + 3 digits; harness is lowercase)
#       (b) Train: ``acc-<acceptance-slug>``         (kebab-case slug)
_REPO_RULE_ID_PATTERN = re.compile(
    r"^repo\.[a-z0-9][a-z0-9-]*\.("
    r"[DLPCEMYRK][0-9]{3}-acc-(?:unit|http|event|ws|e2e|a11y|vis|metric|job|db|sec|load|script|widget|golden|bloc|integration|rls|edge|realtime|storage)-[0-9]{3}"
    r"|"
    r"acc-[a-z][a-z0-9-]*"
    r")$"
)


def _yaml_path_str(parts: Tuple[object, ...]) -> str:
    """Render a YAML key path tuple as a dotted string for error messages."""
    return ".".join(str(p) for p in parts) if parts else "<root>"


def _find_disposition_anywhere(
    node, parts: Tuple[object, ...] = ()
) -> Optional[Tuple[object, ...]]:
    """Return the YAML path to the first ``disposition:`` key found, or None.

    Repo YAML (WMBT and train acceptance files) MUST NOT declare
    ``disposition:`` — the walker sets it to ``strict`` per spec v12 §4.4.
    A declared ``disposition:`` is misleading because it suggests the value
    is configurable when it is not.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "disposition":
                return parts + (key,)
            sub = _find_disposition_anywhere(value, parts + (key,))
            if sub is not None:
                return sub
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            sub = _find_disposition_anywhere(item, parts + (idx,))
            if sub is not None:
                return sub
    return None


def derive_repo_rule_id(acc_urn: str) -> str:
    """Derive the substrate repo rule-id from an ``acc:`` URN per spec §3.3.

    Public façade around ``_derive_repo_rule_id`` for runners (issue #411
    harness-mode plugin, #412 metric runner) that need the rule-id without
    walking the YAML. Raises ``RepoYamlValidationError`` on malformed URNs.
    """
    rule_id, _parent = _derive_repo_rule_id(acc_urn)
    return rule_id


def _derive_repo_rule_id(acc_urn: str) -> Tuple[str, str]:
    """Derive ``(rule_id, parent_token)`` from an ``acc:`` URN per spec §3.3.

    Returns a tuple of the canonical repo rule-id and the parent
    wagon-or-train token. Raises ``RepoYamlValidationError`` when the URN
    is malformed (this should already have been caught by URN validation
    upstream — kept as a defensive belt to surface derivation bugs loudly).

    Transformations (issue #408 derivation table):
      - WMBT shape ``acc:<wagon>:<WMBT-id>-<HARNESS>-<seq>(-<slug>)?``
        → ``repo.<wagon>.<WMBT-id>-acc-<harness>-<seq>``
        (HARNESS lowercased; trailing slug dropped — original slug stays
        on ``RuleMetadata.acceptance_urn``).
      - Train shape ``acc:<train-id>:<acceptance-slug>``
        → ``repo.<train-id>.acc-<acceptance-slug>``
    """
    if not isinstance(acc_urn, str) or not acc_urn.startswith("acc:"):
        raise RepoYamlValidationError(
            f"acc URN must start with 'acc:', got {acc_urn!r}"
        )
    parts = acc_urn.split(":", 2)
    if len(parts) != 3:
        raise RepoYamlValidationError(
            f"acc URN must have shape 'acc:<parent>:<body>', got {acc_urn!r}"
        )
    _, parent, body = parts

    wmbt_match = _WMBT_ACC_BODY_RE.match(body)
    if wmbt_match:
        wmbt_id, harness, seq, _slug = wmbt_match.groups()
        rule_id = f"repo.{parent}.{wmbt_id}-acc-{harness.lower()}-{seq}"
    else:
        # Train shape: body is the acceptance slug.
        rule_id = f"repo.{parent}.acc-{body}"
    return rule_id, parent


def _check_walker_invariants(acc: Dict) -> Optional[str]:
    """Return None when the acceptance satisfies measurability + phase invariants.

    Per spec v12 §4.3: each acceptance MUST declare ``identity.phase`` AND
    EITHER ``harness.type`` (with a binding test) OR both
    ``signal.metric`` and ``signal.threshold``. Acceptances failing either
    invariant are silently skipped during walking — the substrate's
    enforcement validators (Track B / Issue #410) surface the same fail
    condition with a different rule-id, keeping the two-class-failure
    model clean (§11).
    """
    identity = acc.get("identity") if isinstance(acc, dict) else None
    if not isinstance(identity, dict) or not identity.get("phase"):
        return "missing identity.phase"
    harness = acc.get("harness") if isinstance(acc, dict) else None
    has_harness = isinstance(harness, dict) and isinstance(harness.get("type"), str) and harness.get("type")
    signal = acc.get("signal") if isinstance(acc, dict) else None
    has_signal = (
        isinstance(signal, dict)
        and isinstance(signal.get("metric"), str)
        and signal.get("metric")
        and signal.get("threshold") is not None
    )
    if not has_harness and not has_signal:
        return "missing harness.type and signal.metric+signal.threshold (one is required)"
    return None


def _compose_fix_hint(then_block) -> Optional[str]:
    """Compose ``fix_hint`` from ``then.abstract`` items joined with ``; ``."""
    if not isinstance(then_block, dict):
        return None
    abstract = then_block.get("abstract")
    if isinstance(abstract, list):
        items = [str(x).strip() for x in abstract if isinstance(x, (str, int, float)) and str(x).strip()]
        if not items:
            return None
        return "; ".join(items)
    if isinstance(abstract, str) and abstract.strip():
        return abstract.strip()
    return None


def _passthrough_str(block, key) -> Optional[str]:
    """Return ``block[key]`` when it is a non-empty string, else None."""
    if not isinstance(block, dict):
        return None
    val = block.get(key)
    if isinstance(val, (str, int, float)):
        s = str(val).strip()
        return s or None
    if isinstance(val, list):
        # Some authors pass given/when/then.abstract as list — render to string.
        items = [str(x).strip() for x in val if isinstance(x, (str, int, float))]
        return "; ".join(items) if items else None
    return None


def _passthrough_threshold(signal):
    """Return ``signal.threshold`` as a string (preserves int/float/str)."""
    if not isinstance(signal, dict):
        return None
    val = signal.get("threshold")
    if val is None:
        return None
    return str(val)


def _build_repo_rule_metadata(
    acc: Dict,
    file_path: Path,
    parent_urn: Optional[str],
    parent_kind: str,
) -> "RuleMetadata":
    """Construct RuleMetadata from a single repo acceptance block per §4.2.

    Caller is responsible for invariant + structural validation. This helper
    only does field population.
    """
    identity = acc.get("identity", {}) or {}
    acc_urn = identity.get("urn", "")
    rule_id, _parent_token = _derive_repo_rule_id(acc_urn)

    description = ""
    purpose = identity.get("purpose")
    if isinstance(purpose, (str, int, float)):
        description = str(purpose).strip()

    harness = acc.get("harness") if isinstance(acc, dict) else None
    signal = acc.get("signal") if isinstance(acc, dict) else None
    has_signal = (
        isinstance(signal, dict)
        and isinstance(signal.get("metric"), str)
        and signal.get("threshold") is not None
    )

    # Validator: signal mode → toolkit-shipped metric runner; harness-only →
    # None (the anchored test function can't be derived statically from YAML
    # alone — surfaced when the substrate runner machinery lands).
    validator: Optional[str] = None
    if has_signal:
        validator = "test_metric_runner::test_metric_threshold_satisfied"

    metadata_block = acc.get("metadata") if isinstance(acc, dict) else None

    return RuleMetadata(
        rule_id=rule_id,
        severity=4,  # walker-set constant per §4.2
        description=description,
        recipe=None,  # acceptance rules have no recipe pointer (§4.2 close)
        introduced_in=None,
        source_path=file_path.resolve(),
        disposition="strict",  # walker-set constant per §4.4
        validator=validator,
        fix_hint=_compose_fix_hint(acc.get("then")),
        aliases=(),
        acceptance_urn=acc_urn,
        wmbt_urn=parent_urn if parent_kind == "wmbt" else None,
        train_urn=parent_urn if parent_kind == "train" else None,
        phase=identity.get("phase") if isinstance(identity.get("phase"), str) else None,
        harness_type=_passthrough_str(harness, "type"),
        harness_category=_passthrough_str(harness, "category"),
        signal_metric=_passthrough_str(signal, "metric"),
        signal_threshold=_passthrough_threshold(signal),
        given=_passthrough_str(acc.get("given"), "abstract"),
        when=_passthrough_str(acc.get("when"), "abstract"),
        then=_passthrough_str(acc.get("then"), "abstract"),
        author=_passthrough_str(metadata_block, "author"),
        created=_passthrough_str(metadata_block, "created"),
    )


def _train_urn_from_file(data: Dict, train_file: Path) -> str:
    """Derive ``train:<id>`` URN from a parent train YAML.

    Train files declare ``train_id:`` rather than ``urn:``. Falls back to
    the file stem so a missing field still produces a usable parent URN
    (consistent with TrainResolver.find_declarations).
    """
    train_id = data.get("train_id") if isinstance(data, dict) else None
    if not isinstance(train_id, str) or not train_id:
        train_id = train_file.stem
    return f"train:{train_id}"


def _walk_repo_acceptance_file(
    file_path: Path, parent_kind: str
) -> Iterable["RuleMetadata"]:
    """Read one repo YAML and yield RuleMetadata for each valid acceptance.

    Raises ``RepoYamlValidationError`` for structural violations
    (disposition declared, top-level ``id:`` in acceptance, malformed URN,
    derivation produces a non-conforming rule-id). Silently skips
    acceptances that fail the §4.3 walker invariants — those are surfaced
    by Track B substrate validators.
    """
    # Defer URNBuilder import to walk-time so the module loads even when
    # the graph package is not yet importable (avoids import cycles in
    # validators that import rule_binding at module-import time).
    from atdd.coach.utils.graph.urn import URNBuilder

    try:
        with open(file_path) as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        raise RepoYamlValidationError(
            f"unreadable repo YAML at {file_path}: {exc}"
        )
    if not isinstance(data, dict):
        return

    # (1) Reject disposition: anywhere in the file (§4.4).
    bad = _find_disposition_anywhere(data)
    if bad is not None:
        raise RepoYamlValidationError(
            f"{file_path}: declared 'disposition:' at YAML path "
            f"'{_yaml_path_str(bad)}' — repo YAML must not declare disposition; "
            f"the walker sets it to 'strict' per spec v12 §4.4."
        )

    acceptances = data.get("acceptances")
    if not isinstance(acceptances, list):
        return

    parent_urn: Optional[str]
    if parent_kind == "wmbt":
        urn_field = data.get("urn")
        parent_urn = urn_field if isinstance(urn_field, str) else None
    elif parent_kind == "train":
        parent_urn = _train_urn_from_file(data, file_path)
    else:
        parent_urn = None

    for idx, acc in enumerate(acceptances):
        if not isinstance(acc, dict):
            continue

        # (2) Reject top-level id: field on the acceptance block (§3.3 —
        # rule-id derives from identity.urn; declaring id: is misleading).
        if "id" in acc:
            raise RepoYamlValidationError(
                f"{file_path}: acceptance at acceptances[{idx}] declares a "
                f"top-level 'id:' field — rule-id is derived from identity.urn "
                f"per spec v12 §3.3. Remove the top-level 'id:' (identity.id "
                f"is the human-facing label and is allowed)."
            )

        identity = acc.get("identity") or {}
        if not isinstance(identity, dict):
            continue
        acc_urn = identity.get("urn")
        if not isinstance(acc_urn, str) or not acc_urn:
            # No URN: nothing to derive. Substrate enforcement (Track B)
            # surfaces this separately.
            continue

        # (3) Acceptance URN must match URNBuilder.PATTERNS['acc']. Per the
        # spec, "failure of (a) is a parent-graph problem caught by
        # `atdd repo validate`" — so the walker SKIPS malformed-URN
        # acceptances rather than failing loud on the whole registry build.
        # The substrate enforcement validator (Track B / Issue #410)
        # surfaces the URN violation separately.
        if not URNBuilder.validate_urn(acc_urn, "acc"):
            continue

        # (4) Walker invariant: phase + (harness OR signal+threshold).
        invariant_err = _check_walker_invariants(acc)
        if invariant_err is not None:
            # Silent skip — substrate enforcement surfaces this separately.
            continue

        meta = _build_repo_rule_metadata(acc, file_path, parent_urn, parent_kind)

        # (5) Derived rule-id must satisfy the canonical-archetype check
        # AND match the repo-rule grammar. Failure here means a derivation
        # bug — fail loudly with the offending URN and derivation output.
        archetype = meta.rule_id.split(".", 1)[0]
        canonical_archetypes = {"coder", "coach", "tester", "planner", "repo"}
        if archetype not in canonical_archetypes:
            raise RepoYamlValidationError(
                f"{file_path}: derivation produced rule-id {meta.rule_id!r} "
                f"with archetype {archetype!r} not in {sorted(canonical_archetypes)}."
            )
        if not _REPO_RULE_ID_PATTERN.match(meta.rule_id):
            raise RepoYamlValidationError(
                f"{file_path}: derivation produced rule-id {meta.rule_id!r} "
                f"that does not match the repo-rule grammar "
                f"(expected 'repo.<wagon|train>.(<WMBT-id>-acc-<harness>-<NNN>|"
                f"acc-<slug>)'). Source URN: {acc_urn!r}."
            )

        yield meta


def find_repo_rules(
    repo_root: Optional[Path] = None,
) -> List[Tuple[Path, "RuleMetadata"]]:
    """Walk ``<repo>/plan/`` and derive RuleMetadata from every acceptance.

    Substrate spec v12 §4.2/§4.3/§4.4 — peer to ``find_convention_files``.
    The two walkers share a registry index but discover from disjoint
    sources: ``find_convention_files`` finds ``*.convention.yaml`` (toolkit
    rules), this function finds ``plan/<wagon>/[DLPCEMYRK]NNN.yaml`` (WMBT
    acceptances) and ``plan/_trains/<train-id>.yaml`` (train acceptances).

    Each acceptance contributes one ``RuleMetadata`` with:
      - ``rule_id`` derived from ``identity.urn`` per §3.3.
      - ``severity = 4`` (walker-set constant).
      - ``disposition = "strict"`` (walker-set constant per §4.4).
      - All other fields populated per §4.2.

    Acceptances failing the walker invariants (missing ``identity.phase``
    or missing both harness.type AND signal.metric+threshold) are silently
    skipped — Track B substrate validators surface them separately.

    Raises ``RepoYamlValidationError`` for structural violations:
      - ``disposition:`` declared anywhere in repo YAML (§4.4).
      - Literal top-level ``id:`` field on an acceptance block (§3.3).
      - Acceptance URN failing ``URNBuilder.PATTERNS['acc']``.
      - Derivation producing a rule-id that fails repo grammar.

    Returns a list of ``(source_path, metadata)`` tuples. Order is
    deterministic by file path.
    """
    from atdd.coach.utils.repo import find_repo_root as _find_repo_root

    root = Path(repo_root).resolve() if repo_root is not None else _find_repo_root()
    plan_dir = root / "plan"
    if not plan_dir.is_dir():
        return []

    results: List[Tuple[Path, RuleMetadata]] = []

    # WMBT acceptances: plan/<wagon>/[DLPCEMYRK]NNN.yaml
    wmbt_pattern = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")
    for wagon_dir in sorted(plan_dir.iterdir()):
        if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
            continue
        for wmbt_file in sorted(wagon_dir.glob("*.yaml")):
            if not wmbt_pattern.match(wmbt_file.name):
                continue
            for meta in _walk_repo_acceptance_file(wmbt_file, parent_kind="wmbt"):
                results.append((wmbt_file, meta))

    # Train acceptances: plan/_trains/<train-id>.yaml
    trains_dir = plan_dir / "_trains"
    if trains_dir.is_dir():
        for train_file in sorted(trains_dir.glob("*.yaml")):
            for meta in _walk_repo_acceptance_file(train_file, parent_kind="train"):
                results.append((train_file, meta))

    return results


# ---------------------------------------------------------------------------
# Registry cache
# ---------------------------------------------------------------------------
# rule_id -> [RuleMetadata, ...] (length > 1 means ambiguous)
_REGISTRY_CACHE: Optional[Dict[str, List[RuleMetadata]]] = None
_OVERRIDE_ROOTS: Optional[List[Path]] = None
_OVERRIDE_REPO_ROOT: Optional[Path] = None


def clear_cache(
    *,
    override_roots: Optional[Iterable[Path]] = None,
    override_repo_root: Optional[Path] = None,
) -> None:
    """Drop the cached registry.

    Test-only hook.  Pass ``override_roots=[...]`` to seed the next
    ``bind_rule`` call against fixture conventions instead of the live
    toolkit tree.  Pass ``override_repo_root=Path(...)`` to point the
    repo-rule walker (issue #408) at a fixture ``plan/`` tree instead of
    the live consumer repo. Pass nothing (or ``=None``) to reset to the
    default search roots.
    """
    global _REGISTRY_CACHE, _OVERRIDE_ROOTS, _OVERRIDE_REPO_ROOT
    _REGISTRY_CACHE = None
    if override_roots is None:
        _OVERRIDE_ROOTS = None
    else:
        _OVERRIDE_ROOTS = [Path(p) for p in override_roots]
    _OVERRIDE_REPO_ROOT = Path(override_repo_root) if override_repo_root is not None else None


def _load_registry() -> Dict[str, List[RuleMetadata]]:
    """Walk every convention file and index rules by canonical id and alias.

    Each rule's ``id:`` is registered as a primary key. Every entry in
    ``aliases:`` is ALSO registered, pointing at the same ``RuleMetadata``,
    so legacy flat-grammar callsites continue to resolve through bind_rule
    and the suppression scanner. (Issue #399.)

    Collisions surface here: two canonical rules with the same id raise
    ``AmbiguousRuleError`` at bind time; an alias colliding with another
    rule's canonical id (or another rule's alias) raises
    ``AmbiguousAliasError`` at registry-build time.
    """
    roots = _OVERRIDE_ROOTS if _OVERRIDE_ROOTS is not None else _default_roots()
    registry: Dict[str, List[RuleMetadata]] = {}
    canonical_ids: set = set()
    alias_to_canonical: Dict[str, str] = {}

    for file_path in find_convention_files(roots):
        for _, _, rule in extract_rules(file_path):
            rid = rule.get("id")
            if not isinstance(rid, str) or not rid:
                continue
            severity = rule.get("severity")
            if not isinstance(severity, int) or isinstance(severity, bool):
                continue  # malformed rules are policed by test_rule_id_uniqueness
            description = rule.get("description") or ""
            recipe = rule.get("recipe")
            introduced_in = rule.get("introduced_in")
            disposition = rule.get("disposition")
            validator = rule.get("validator")
            fix_hint = rule.get("fix_hint")
            aliases_raw = rule.get("aliases")
            aliases: Tuple[str, ...]
            if isinstance(aliases_raw, list):
                aliases = tuple(a for a in aliases_raw if isinstance(a, str) and a)
            else:
                aliases = ()
            meta = RuleMetadata(
                rule_id=rid,
                severity=severity,
                description=description,
                recipe=recipe if isinstance(recipe, str) and recipe else None,
                introduced_in=(
                    introduced_in
                    if isinstance(introduced_in, str) and introduced_in
                    else None
                ),
                source_path=file_path.resolve(),
                disposition=(
                    disposition if isinstance(disposition, str) else None
                ),
                validator=validator if isinstance(validator, str) and validator else None,
                fix_hint=fix_hint if isinstance(fix_hint, str) and fix_hint else None,
                aliases=aliases,
            )
            registry.setdefault(rid, []).append(meta)
            canonical_ids.add(rid)

            for alias in aliases:
                # Alias collides with another canonical id?
                if alias in canonical_ids and alias != rid:
                    raise AmbiguousAliasError(
                        f"alias {alias!r} on rule {rid!r} collides with another "
                        f"rule's canonical id (declared in "
                        f"{registry[alias][0].source_path}). "
                        f"Aliases must be unique across the registry."
                    )
                # Alias collides with another rule's alias?
                if alias in alias_to_canonical and alias_to_canonical[alias] != rid:
                    raise AmbiguousAliasError(
                        f"alias {alias!r} is claimed by both {rid!r} and "
                        f"{alias_to_canonical[alias]!r}. Aliases must point at "
                        f"a single canonical rule."
                    )
                alias_to_canonical[alias] = rid
                # Register alias entry pointing at the same RuleMetadata so
                # bind_rule(alias) resolves to the canonical rule.
                if alias != rid:
                    registry.setdefault(alias, []).append(meta)

    # Repo-rule walker (substrate spec v12 §4.2 — issue #408). Merges into
    # the same registry index so bind_rule resolves both toolkit-convention
    # and repo-derived rules through one path. Cross-source collisions
    # raise AmbiguousRuleError at lookup time (existing behavior).
    repo_root = _OVERRIDE_REPO_ROOT
    if repo_root is None and _OVERRIDE_ROOTS is None:
        # Live mode: walk the consumer repo's plan/ tree.
        from atdd.coach.utils.repo import find_repo_root

        repo_root = find_repo_root()
    # When override_roots is set (test mode pointing at fixture conventions)
    # we DO NOT also walk a live plan/ — tests must explicitly opt in by
    # passing override_repo_root. This keeps fixture-based convention tests
    # hermetic from the consumer repo's plan/ contents.
    if repo_root is not None:
        for _src_path, repo_meta in find_repo_rules(repo_root):
            registry.setdefault(repo_meta.rule_id, []).append(repo_meta)

    return registry


def _get_registry() -> Dict[str, List[RuleMetadata]]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        _REGISTRY_CACHE = _load_registry()
    return _REGISTRY_CACHE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def bind_rule(rule_id: str) -> RuleMetadata:
    """Return the convention's metadata for *rule_id*.

    Called at validator module-import time so the failure modes are loud:

    * ``RuleNotInRegistryError`` — the ID is not declared in any
      ``*.convention.yaml`` under the toolkit search roots.
    * ``AmbiguousRuleError`` — the ID is declared in two or more files; the
      message lists every ``source_path``.

    The registry is cached at module level; tests reset it via
    ``clear_cache()``.
    """
    registry = _get_registry()
    matches = registry.get(rule_id, [])
    if not matches:
        raise RuleNotInRegistryError(
            f"rule_id {rule_id!r} is not declared in any convention. "
            f"Add it to a *.convention.yaml under src/atdd/, or fix the "
            f"caller's rule_id."
        )
    if len(matches) > 1:
        paths = "\n  - ".join(str(m.source_path) for m in matches)
        raise AmbiguousRuleError(
            f"rule_id {rule_id!r} is declared in {len(matches)} convention files:\n"
            f"  - {paths}\n"
            f"Rule IDs are stable forever — use superseded_by instead of "
            f"redeclaring."
        )
    return matches[0]


def get_canonical_id(rule_id: str) -> str:
    """Resolve *rule_id* (canonical or alias) to its canonical form.

    Useful when a callsite holds a legacy flat-grammar id and needs to
    normalize it (e.g. for stable ordering, reporting, or storage).
    Raises ``RuleNotInRegistryError`` when the id is unknown; raises
    ``AmbiguousRuleError`` when the id is declared canonically in two
    convention files.
    """
    return bind_rule(rule_id).rule_id


def iter_rules() -> Iterable[RuleMetadata]:
    """Yield every canonically-registered rule in the merged registry.

    Walks the same registry that ``bind_rule`` resolves against — so the
    iterator surfaces both toolkit-convention rules (via
    ``find_convention_files``) and repo-derived rules (via
    ``find_repo_rules``). Aliases are skipped; only the canonical id of
    each rule is yielded once.

    The iterator is the public peer of the underscored ``_get_registry``
    helper. ``atdd rules`` and ``atdd urn rules`` consume it (issue #409).

    Order: ascending by ``rule_id``. Stable across calls within a process
    (the registry is cached) but not across processes (file discovery
    order can shift if conventions are added or moved).

    Yields:
        ``RuleMetadata`` for each canonical rule. Ambiguous rules
        (declared in two convention files) are silently elided here —
        ``bind_rule`` is the place those failures surface.
    """
    registry = _get_registry()
    seen: set = set()
    for rule_id in sorted(registry.keys()):
        matches = registry.get(rule_id, [])
        if not matches:
            continue
        # ``registry`` includes alias entries pointing at the canonical
        # ``RuleMetadata``. Yield each canonical metadata exactly once by
        # gating on its own ``rule_id`` (the canonical id, not the lookup
        # key — which may be an alias).
        canonical_meta = matches[0]
        if canonical_meta.rule_id in seen:
            continue
        if rule_id != canonical_meta.rule_id:
            # This entry is the alias-row; skip — the canonical row will
            # appear separately in the sorted walk.
            continue
        seen.add(canonical_meta.rule_id)
        yield canonical_meta


__all__ = [
    "AmbiguousAliasError",
    "AmbiguousRuleError",
    "RepoYamlValidationError",
    "RuleMetadata",
    "RuleNotInRegistryError",
    "bind_rule",
    "clear_cache",
    "derive_repo_rule_id",
    "extract_rules",
    "find_convention_files",
    "find_repo_rules",
    "get_canonical_id",
    "iter_rules",
]

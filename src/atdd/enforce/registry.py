# URN: component:govern-registry:rule-registry-scope:backend:domain
# Runtime: python
# Purpose: Settle the Path-A-is-core-only scope with evidence, keep the extension
#          mirror set coherent with the live core registry, fail loudly on a
#          cross-registry rule_id collision, and refuse a core-node deletion whose
#          extension twin is not independently (bound + blockingly) enforced in CI.
"""Rule-registry scope + succession governance (#1427 govern-registry).

``atdd validate`` (Path A) builds its rule registry from
:func:`atdd.coach.utils.rule_binding.find_convention_files`, whose default roots
are the core ``src/atdd`` tree ALONE — zero of its files live under
``.atdd/extensions``. Every extension convention node is a *high-fidelity mirror*
of a live core rule (each carries ``source.legacy_path`` + ``source.legacy_rule_id``),
so the extension rule_ids are a subset of the core rule_ids. Admitting the
extension tree into the registry would therefore add NO new rule and only
duplicate ids. The registry stays core-only BY DESIGN; this module records that
decision as executable evidence and guards the boundary:

* **D001 registry-scope** — :func:`core_rule_ids` / :func:`extension_rule_ids`
  plus :func:`new_rules_from_extensions` / :func:`duplicate_rule_ids`, the pure
  helpers proving the merge adds nothing. The prose decision lives in
  ``docs/registry-scope-decision.md``.
* **E001 mirror-coherence** — :func:`find_mirror_incoherences` /
  :func:`assert_mirrors_coherent`: every extension node's ``legacy_rule_id`` must
  still resolve to a live core rule, else the mirror has drifted (its core twin
  was renamed/deleted) and it silently reflects no live obligation.
* **E002 duplicate-precedence** — :func:`assert_core_precedes_extension` raises
  :class:`~atdd.coach.utils.rule_binding.DuplicateRuleError` on any rule_id
  present in both registries, stating CORE precedes extension;
  :func:`merge_with_precedence` resolves a unified view core-wins.
* **E003 core-succession** — :func:`path_b_is_blocking` +
  :func:`guard_core_deletion`: no CI job runs Path B (``atdd enforce``) as a
  BLOCKING gate today (the enforce-extensions verdict is advisory), so all
  extension rules are enforced solely by their blocking core twin under Path A.
  Deleting a core node whose extension twin is not both bound AND blockingly
  enforced silently strips the only enforcement — the guard refuses it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Optional, Sequence

import yaml

# The cross-registry collision error lives with its sibling registry errors
# (RuleNotInRegistryError, AmbiguousRuleError) in the rule-binding module, its
# designated home. Re-exported here so enforce callers import it from one place.
from atdd.coach.utils.rule_binding import (  # noqa: F401 (re-exported)
    DuplicateRuleError,
    extract_rules,
    find_convention_files,
)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class MirrorDriftError(Exception):
    """An extension node's ``source.legacy_rule_id`` names no live core rule."""


class CoreSuccessionError(Exception):
    """Deleting a core convention node would silently strip the only enforcement
    of a rule an extension still mirrors (its twin is not independently enforced)."""


# ---------------------------------------------------------------------------
# Core registry (Path A — src/atdd only)
# ---------------------------------------------------------------------------
def core_convention_files(roots: Optional[Iterable[Path]] = None) -> list[Path]:
    """The ``*.convention.yaml`` files admitted into the core rule registry.

    Thin pass-through to :func:`find_convention_files`; its default roots are the
    core ``src/atdd`` tree, so no file under ``.atdd/extensions`` is ever admitted.
    """
    return find_convention_files(roots)


def core_rule_ids(roots: Optional[Iterable[Path]] = None) -> set[str]:
    """Every rule_id declared in the core registry (Path A search roots).

    Uses the SAME walker (:func:`extract_rules`) the rule-id uniqueness validator
    and ``bind_rule`` use, so the set matches what ``atdd validate`` actually reads.
    """
    ids: set[str] = set()
    for f in core_convention_files(roots):
        for _path, _keypath, rule in extract_rules(f):
            rid = rule.get("id") or rule.get("rule_id")
            if rid:
                ids.add(str(rid))
    return ids


# ---------------------------------------------------------------------------
# Extension mirror set (.atdd/extensions convention nodes)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ExtensionNode:
    rule_id: str
    legacy_rule_id: Optional[str]
    legacy_path: Optional[str]
    node_path: Path


def iter_extension_nodes(substrate_home: str | Path) -> Iterator[ExtensionNode]:
    """Yield one :class:`ExtensionNode` per ``*.convention.yaml`` under extensions.

    Nodes that fail to parse, or that declare no ``rule_id``/``convention_id``, are
    skipped — their structural faults are policed by the substrate/authoring
    validators, not the registry-scope guards here.
    """
    ext_root = Path(substrate_home) / ".atdd" / "extensions"
    if not ext_root.is_dir():
        return
    for node in sorted(ext_root.rglob("*.convention.yaml")):
        if "__pycache__" in node.parts:
            continue
        try:
            data = yaml.safe_load(node.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            _log.warning(
                "unreadable extension convention node — skipped",
                extra={"node": str(node), "error": str(exc)},
            )
            continue
        if not isinstance(data, dict):
            continue
        rid = data.get("rule_id") or data.get("convention_id")
        if not rid:
            continue
        source = data.get("source") if isinstance(data.get("source"), dict) else {}
        yield ExtensionNode(
            rule_id=str(rid),
            legacy_rule_id=(str(source.get("legacy_rule_id")) if source.get("legacy_rule_id") else None),
            legacy_path=(str(source.get("legacy_path")) if source.get("legacy_path") else None),
            node_path=node,
        )


def extension_rule_ids(substrate_home: str | Path) -> set[str]:
    """The rule_id of every extension convention node under ``.atdd/extensions``."""
    return {node.rule_id for node in iter_extension_nodes(substrate_home)}


# ---------------------------------------------------------------------------
# D001 — registry-scope evidence (admitting extensions adds nothing)
# ---------------------------------------------------------------------------
def new_rules_from_extensions(
    core_ids: Iterable[str], extension_ids: Iterable[str]
) -> set[str]:
    """Rule_ids the extensions would ADD to the registry — extension ids not in core.

    Empty when every extension id mirrors a core id (the designed state): admitting
    the extension tree contributes no new rule.
    """
    return set(extension_ids) - set(core_ids)


def duplicate_rule_ids(
    core_ids: Iterable[str], extension_ids: Iterable[str]
) -> set[str]:
    """Rule_ids declared in BOTH registries — the collisions a merge would create."""
    return set(core_ids) & set(extension_ids)


# ---------------------------------------------------------------------------
# E001 — mirror coherence (every extension mirror names a live core rule)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MirrorIncoherence:
    extension_rule_id: str
    legacy_rule_id: Optional[str]
    node_path: Path


def find_mirror_incoherences(
    substrate_home: str | Path,
    core_ids: Optional[Iterable[str]] = None,
) -> list[MirrorIncoherence]:
    """Every extension node whose ``legacy_rule_id`` names no live core rule.

    ``core_ids`` is injectable so unit tests stay hermetic; when omitted the live
    core registry (:func:`core_rule_ids`) is read. A node with no ``legacy_rule_id``
    at all is a drifted mirror too — it claims to mirror nothing.
    """
    known = set(core_ids) if core_ids is not None else core_rule_ids()
    out: list[MirrorIncoherence] = []
    for node in iter_extension_nodes(substrate_home):
        if node.legacy_rule_id not in known:
            out.append(
                MirrorIncoherence(
                    extension_rule_id=node.rule_id,
                    legacy_rule_id=node.legacy_rule_id,
                    node_path=node.node_path,
                )
            )
    return sorted(out, key=lambda m: m.extension_rule_id)


def render_mirror_report(incoherences: Sequence[MirrorIncoherence]) -> str:
    """A loud report naming each drifted mirror (or a clean line)."""
    if not incoherences:
        return "mirror-coherence: clean — every extension node mirrors a live core rule."
    lines = [
        f"mirror-coherence: {len(incoherences)} extension node(s) mirror a core rule "
        f"that no longer exists (drifted mirror):",
    ]
    for m in incoherences:
        lines.append(
            f"  [drift] {m.extension_rule_id} -> legacy_rule_id "
            f"{m.legacy_rule_id!r} not in the core registry ({m.node_path})"
        )
    return "\n".join(lines)


def assert_mirrors_coherent(
    substrate_home: str | Path,
    core_ids: Optional[Iterable[str]] = None,
) -> list[MirrorIncoherence]:
    """Raise :class:`MirrorDriftError` naming every drifted mirror; else return ``[]``."""
    incoherences = find_mirror_incoherences(substrate_home, core_ids)
    if incoherences:
        raise MirrorDriftError(render_mirror_report(incoherences))
    return incoherences


# ---------------------------------------------------------------------------
# E002 — duplicate-rule precedence (core precedes extension)
# ---------------------------------------------------------------------------
def assert_core_precedes_extension(
    core_ids: Iterable[str], extension_ids: Iterable[str]
) -> None:
    """Raise :class:`DuplicateRuleError` on any rule_id in BOTH registries.

    The message names the colliding ids and states the resolution — CORE precedes
    extension — so the two registries stay separate on purpose. Disjoint registries
    return ``None`` (no collision).
    """
    dups = sorted(duplicate_rule_ids(core_ids, extension_ids))
    if dups:
        raise DuplicateRuleError(
            f"{len(dups)} rule_id(s) declared in BOTH the core registry and the "
            f"extension mirror set: {dups}. Precedence: CORE precedes extension — "
            f"the core declaration is authoritative; do NOT admit the extension "
            f"mirrors into the core rule registry (Path A stays core-only)."
        )


def merge_with_precedence(
    core_registry: Mapping[str, object],
    extension_registry: Mapping[str, object],
) -> dict[str, object]:
    """Merge two registries under the stated precedence: the CORE entry wins.

    Used only when a unified view is unavoidable — the guard's default is to keep
    the registries separate. Applying core last means a colliding rule_id resolves
    to its core body, never the extension mirror.
    """
    merged: dict[str, object] = dict(extension_registry)
    merged.update(core_registry)  # core overwrites extension → core precedes extension
    return merged


# ---------------------------------------------------------------------------
# E003 — core-succession guard (deleting a core node must not strip enforcement)
# ---------------------------------------------------------------------------
_ENFORCE_JOB = "enforce-extensions"


def path_b_is_blocking(repo_root: str | Path) -> bool:
    """Whether Path B (``atdd enforce``) runs as a BLOCKING CI gate.

    Reads ``.github/workflows/atdd-validate.yml`` and inspects the
    ``enforce-extensions`` job's convention-verdict step (the one that runs
    ``atdd enforce`` WITHOUT ``--verify-substrate``). That step is blocking only
    when it is neither marked ``continue-on-error`` nor ends its command with
    ``|| true``. Today it is advisory, so this returns ``False`` — the fact the
    succession guard depends on.

    Returns ``False`` when the workflow, job, or verdict step is absent (fail
    closed: an absent blocking gate is not a blocking gate).
    """
    wf = Path(repo_root) / ".github" / "workflows" / "atdd-validate.yml"
    if not wf.is_file():
        return False
    try:
        data = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        _log.warning("unreadable CI workflow — Path B treated as non-blocking",
                     extra={"workflow": str(wf), "error": str(exc)})
        return False
    jobs = data.get("jobs") if isinstance(data, dict) else None
    job = jobs.get(_ENFORCE_JOB) if isinstance(jobs, dict) else None
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        run = str(step.get("run") or "")
        # The convention-verdict step runs `atdd enforce` to produce PASS/FAIL,
        # distinct from the `--verify-substrate` digest check (always blocking).
        if "enforce" in run and "--verify-substrate" not in run:
            if step.get("continue-on-error") is True:
                return False
            if "|| true" in run:
                return False
            return True
    return False


def _bound_convention_ids(substrate_home: str | Path) -> set[str]:
    """The convention_id of every ``disposition: bound`` entry in the binding lock."""
    lock_path = Path(substrate_home) / ".atdd" / "binding.lock.yaml"
    if not lock_path.is_file():
        return set()
    try:
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        _log.warning("unreadable binding.lock.yaml — no bound ids",
                     extra={"lock_path": str(lock_path), "error": str(exc)})
        return set()
    conventions = lock.get("conventions") if isinstance(lock, dict) else None
    conventions = conventions if isinstance(conventions, list) else []
    return {
        str(c.get("convention_id"))
        for c in conventions
        if isinstance(c, dict) and c.get("disposition") == "bound" and c.get("convention_id")
    }


def _twins_by_core_rule(substrate_home: str | Path) -> dict[str, list[ExtensionNode]]:
    """Map each core rule_id to the extension nodes that mirror it (by legacy_rule_id)."""
    twins: dict[str, list[ExtensionNode]] = {}
    for node in iter_extension_nodes(substrate_home):
        if node.legacy_rule_id:
            twins.setdefault(node.legacy_rule_id, []).append(node)
    return twins


@dataclass(frozen=True)
class SuccessionRefusal:
    core_rule_id: str
    reason: str


def evaluate_core_deletion(
    deleted_core_rule_ids: Iterable[str],
    substrate_home: str | Path,
    *,
    path_b_blocking: bool,
) -> list[SuccessionRefusal]:
    """Refusals for deleting core rules whose enforcement would silently vanish.

    A core rule is SAFE to delete only when either
      * no extension node mirrors it (nothing else claims the obligation), or
      * its extension twin is *independently* enforced — bound in the lock AND
        Path B runs as a blocking gate.
    Any other twinned rule is refused: deleting it strips the only blocking
    enforcement (the twin, if any, is advisory-only or unbound).
    """
    bound = _bound_convention_ids(substrate_home)
    twins = _twins_by_core_rule(substrate_home)
    refusals: list[SuccessionRefusal] = []
    for rid in deleted_core_rule_ids:
        node_twins = twins.get(rid) or []
        if not node_twins:
            continue  # no mirror → no twin enforcement to lose
        twin_bound = any(t.rule_id in bound for t in node_twins)
        if twin_bound and path_b_blocking:
            continue  # succession is safe — the twin independently enforces the rule
        if not twin_bound:
            reason = (
                f"its extension twin ({', '.join(sorted(t.rule_id for t in node_twins))}) "
                f"is not bound in binding.lock — no independent enforcement exists"
            )
        else:
            reason = (
                "its extension twin is bound but Path B (atdd enforce) is advisory, "
                "not a blocking CI gate — deletion strips the sole blocking enforcement"
            )
        refusals.append(SuccessionRefusal(core_rule_id=rid, reason=reason))
    return sorted(refusals, key=lambda r: r.core_rule_id)


def render_succession_report(refusals: Sequence[SuccessionRefusal]) -> str:
    lines = [
        f"core-succession: refusing to delete {len(refusals)} core convention "
        f"node(s) whose enforcement would silently vanish:",
    ]
    for r in refusals:
        lines.append(f"  [refused] {r.core_rule_id} — {r.reason}")
    return "\n".join(lines)


def guard_core_deletion(
    deleted_core_rule_ids: Iterable[str],
    substrate_home: str | Path,
    *,
    path_b_blocking: bool,
) -> None:
    """Raise :class:`CoreSuccessionError` naming every unsafe core-node deletion.

    The loud guard over :func:`evaluate_core_deletion`: a core node may only be
    deleted when its enforcement genuinely survives the deletion.
    """
    refusals = evaluate_core_deletion(
        deleted_core_rule_ids, substrate_home, path_b_blocking=path_b_blocking
    )
    if refusals:
        raise CoreSuccessionError(render_succession_report(refusals))

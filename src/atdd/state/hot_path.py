"""No GitHub on the lifecycle hot path (#1400 migrate-projection-authority, CORE-033, Y001).

Spec §12 non-goal 2 and invariant I7: **the GitHub mirror is non-authoritative.** A lifecycle
decision that reads GitHub is a decision that GitHub can be wrong about, that an outage can
block, and that a rate limit can make non-deterministic. So:

> No core lifecycle **decision**, **validator**, or **gate** calls the GitHub API. Every
> remaining provider access sits behind the SyncProvider seam and the ``external_refs``
> quarantine.

:mod:`atdd.state.import_boundary` (§8.1) already proves the *state* closure imports no provider
at all. This guard is the wider one CORE-033 asks for: it walks the whole **decision surface** —
the store-backed readers, the gates, the validators, the evidence materializer — which lives
across ``atdd.state``, ``atdd.coach`` and ``atdd.tester``, and asks a narrower question of it.

Narrower, because the two rules differ *on purpose*:

============================  ==========================================================
``import_boundary`` (§8.1)    the state closure may not even reach the provider **registry**
``hot_path`` (this, §12/I7)   a decision module may reach the **seam**; it may not reach
                              **GitHub**
============================  ==========================================================

The seam is the sanctioned path — that is the whole point of having built one. What is refused
is a decision module going *around* it: importing the GitHub API, importing a provider
implementation, shelling out to ``gh``, or reading a GitHub concept (``issue_labels``,
``issue_number``) as code. A store read that a provider happened to seed through
:mod:`atdd.state.sync_engine` is a store read; a ``gh issue view`` in the middle of a gate is not.

Two things it deliberately does **not** claim:

- It says nothing about *mirroring*. ``atdd coach transition`` moving a GitHub label after the
  store write is presentation, not a decision, and it is not in the decision surface.
- It says nothing about *authoring* convenience. Creating a worktree may ask a provider what
  issue #N is called. That is an ingest through the seam, not a gate consulting a label.

The surface is therefore **declared, not discovered** (:data:`DECISION_MODULES`) — a guard that
guessed which modules decide would be a guard nobody could argue with, and the argument is the
useful part. Adding a module to the list is how a reviewer widens the claim.

Static, like §8.1's: source is parsed with :mod:`ast` and nothing is imported. A guard that ran
``try: import github`` would pass on any runner where the provider merely isn't installed —
which is every runner core has — and would therefore have proved nothing.

Dependency discipline: stdlib + :mod:`atdd.state.import_boundary` (itself stdlib-only).
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from atdd.state.import_boundary import (
    GH_COMMAND,
    ImportBoundaryError,
    Violation,
    _gh_shell_outs,
    _imports_of,
    _module_path,
    _parse,
    package_root,
)

_log = logging.getLogger(__name__)

#: The law, quoted in every failure — the reader is told what they broke, not merely what tripped.
HOT_PATH_LAW = (
    "spec §12 non-goal 2 / I7 — the GitHub mirror is non-authoritative. No core lifecycle "
    "decision, validator, or gate may call the GitHub API. Provider access goes through the "
    "SyncProvider seam and the external_refs quarantine, or it does not happen."
)

#: The decision surface: every module that *answers a lifecycle question*. Declared, because a
#: guard that guessed would be a guard nobody could argue with. Dotted relative to ``atdd``.
#:
#: - the ``atdd.state`` lifecycle closure — phase, evidence, transition legality, merge authority
#: - ``state.work_item_reader``  — the store-backed read facade every command reads through
#: - ``coach.runtime.graph``     — the gate graph
#: - ``coach.commands.issue_graph`` — issue → wagon resolution, which gates read
#: - ``train.persistence``       — evidence materialization: what the gate is handed
#: - ``tester.validators._acceptance_walker`` — the acceptance validator's phase read
DECISION_MODULES: Tuple[str, ...] = (
    "state.projection", "state.identity", "state.overlay", "state.reconcile",
    "state.metadata", "state.authoring", "state.trailers", "state.evidence",
    "state.smoke_evidence",
    "state.crosscheck", "state.secrets", "state.merge_authority", "state.policy",
    "state.ownership", "state.merge_driver", "state.merge_matrix", "state.tombstone",
    "state.import_boundary", "state.manifest_migration", "state.manifest_fallback",
    "state.shadow", "state.cutover", "state.hot_path",
    "state.work_item_reader",
    "coach.runtime.graph",
    "coach.commands.issue_graph",
    "train.persistence",
    "tester.validators._acceptance_walker",
)

#: The GitHub API, in every spelling. Reachable from a decision module ⇒ the law is broken.
GITHUB_PACKAGES: Tuple[str, ...] = ("github", "pygithub", "ghapi")

#: Dotted prefixes that ARE the provider implementation, even though their root is core's own.
#: ``atdd.integrations.github`` is core's in-tree GitHub client: a decision module importing it
#: has a GitHub dependency whatever the seam says.
PROVIDER_PREFIXES: Tuple[str, ...] = ("atdd.integrations",)

#: The seam. Reaching THESE from a decision module is allowed and is the point (contrast
#: :data:`atdd.state.import_boundary.REGISTRY_MODULES`, which the *state* closure may not reach).
#: The walk does not descend into them: what a provider does behind the seam is the provider's
#: business, and core is not entitled to an opinion about it.
SEAM_MODULES: Tuple[str, ...] = (
    "atdd.state.provider_seam", "atdd.state.providers", "atdd.state.sync_engine",
    "atdd.state.sync_cli",
)

#: GitHub's own *lifecycle opinion*, and its client, as code identifiers.
#:
#: This set is deliberately **narrower** than §8.1's
#: :data:`atdd.state.import_boundary.GITHUB_IDENTIFIERS`, and the difference is the whole
#: distinction Y001 draws. ``issue_labels`` is GitHub's answer to "what phase is this in?" — a
#: decision module reading it is letting the mirror overrule the store, which is exactly the
#: RED this wagon closes ("lifecycle readers still consult GitHub labels today").
#:
#: ``issue_number`` is **not** in the set. It is core's *own* vocabulary: the key the store's
#: ``external_refs`` table is indexed by and the handle the operator types (``atdd coach enter
#: 1234``). Core addresses a work item by it; it does not call GitHub to learn it. In the §8.1
#: state closure the name should never appear at all, and there it is still refused. Out here —
#: across ``coach`` and ``train``, whose whole job is to be handed an issue number — refusing it
#: would flag 46 parameter names and catch no read.
HOT_PATH_IDENTIFIERS: frozenset = frozenset({
    "gh", "github", "pygithub", "issue_label", "issue_labels",
})

RULE_GITHUB_API = "github-api-dependency"
RULE_GH_SHELL_OUT = "gh-shell-out"
RULE_GITHUB_IDENTIFIER = "github-identifier"


@dataclass(frozen=True)
class HotPathReport:
    """The guard's verdict over the decision surface."""

    violations: List[Violation] = field(default_factory=list)
    scanned: List[str] = field(default_factory=list)
    roots: List[str] = field(default_factory=list)
    #: Decision modules named in :data:`DECISION_MODULES` that do not exist in this checkout.
    missing: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.ok:
            return (
                f"the lifecycle hot path is GitHub-free: {len(self.scanned)} module(s) reachable "
                f"from {len(self.roots)} decision module(s), no GitHub API, no `gh`, no provider "
                f"implementation.\n{HOT_PATH_LAW}"
            )
        lines = [
            f"the lifecycle hot path reads GitHub in {len(self.violations)} place(s):",
            *(f"  {violation.render()}" for violation in sorted(
                self.violations, key=lambda v: (v.module, v.line, v.target))),
            HOT_PATH_LAW,
        ]
        return "\n".join(lines)


def _is_github(target: str) -> bool:
    """True when ``target`` names the GitHub API or a provider implementation."""
    root = target.split(".")[0]
    return root in GITHUB_PACKAGES or any(
        target == prefix or target.startswith(prefix + ".") for prefix in PROVIDER_PREFIXES
    )


def _is_seam(target: str) -> bool:
    """True when ``target`` is the sanctioned SyncProvider seam."""
    return target in SEAM_MODULES


def _import_targets(tree: ast.AST) -> List[Tuple[str, int]]:
    """Every dotted name a module imports — including the submodules of a ``from`` import.

    :func:`atdd.state.import_boundary._imports_of` records ``from atdd.state import evidence`` as
    an import of ``atdd.state``, which is true and is not enough: the module actually pulled in is
    ``atdd.state.evidence``, and a transitive walk that never queues it walks straight past whatever
    *it* imports. So each ``from X import a, b`` also yields ``X.a`` and ``X.b`` as candidates; the
    ones that are not modules simply do not resolve to a file and are dropped by the walk.

    This matters here and not in §8.1's guard because this walk is the one that has to *reach* the
    provider through a chain of core helpers — which is exactly how a GitHub dependency hides.
    """
    found: List[Tuple[str, int]] = list(_imports_of(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.extend((f"{node.module}.{alias.name}", node.lineno) for alias in node.names)
    return found


def _hot_path_identifiers(tree: "ast.AST") -> List[Tuple[str, int]]:
    """GitHub's client and its lifecycle opinion, used as *code*: a name, attribute, or keyword.

    String literals are excluded on purpose (as in §8.1): ``"issue_labels"`` as a dict key inside
    the provider's own ``external_refs`` subtree is data core carries and does not act on, and
    flagging it would be flagging the mirror for existing.
    """
    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.lower() in HOT_PATH_IDENTIFIERS:
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute) and node.attr.lower() in HOT_PATH_IDENTIFIERS:
            found.append((f".{node.attr}", node.lineno))
        elif isinstance(node, ast.keyword) and node.arg and node.arg.lower() in HOT_PATH_IDENTIFIERS:
            found.append((f"{node.arg}=", node.lineno))
    return found


def decision_roots(root: Path, modules: Sequence[str] = DECISION_MODULES) -> Tuple[List[str], List[str]]:
    """``(present, missing)`` dotted names for the declared decision modules in ``root``.

    ``missing`` is reported rather than swallowed: a decision module that has been renamed away
    silently shrinks the surface this guard covers, and a shrinking guard that still says PASS is
    worse than no guard.
    """
    present: List[str] = []
    missing: List[str] = []
    for name in modules:
        dotted = f"{root.name}.{name}"
        (present if _module_path(root, dotted) is not None else missing).append(dotted)
    return present, missing


def check(
    package: Optional[Path] = None, *, modules: Sequence[str] = DECISION_MODULES,
) -> HotPathReport:
    """Walk the decision surface transitively and judge it against :data:`HOT_PATH_LAW` (Y001).

    Transitive, because a gate that imports a helper that imports ``atdd.integrations.github``
    reads GitHub just as surely as if it had typed it itself. The walk stops at the seam and at
    any non-first-party name: core does not own their contents, and reading site-packages would
    make the verdict depend on what happens to be installed.
    """
    root = package_root(package)
    roots, missing = decision_roots(root, modules)
    violations: List[Violation] = []
    scanned: Set[str] = set()
    queue: List[str] = list(roots)

    while queue:
        dotted = queue.pop(0)
        if dotted in scanned:
            continue
        scanned.add(dotted)
        path = _module_path(root, dotted)
        if path is None:
            continue
        tree = _parse(path)

        for target, line in _import_targets(tree):
            if _is_github(target):
                violations.append(Violation(RULE_GITHUB_API, dotted, line, target))
            elif _is_seam(target):
                continue  # the sanctioned path: reach it, do not walk through it
            elif target.startswith(root.name + "."):
                queue.append(target)

        for target, line in _gh_shell_outs(tree):
            violations.append(Violation(RULE_GH_SHELL_OUT, dotted, line, target))

        if dotted in roots:
            for target, line in _hot_path_identifiers(tree):
                violations.append(Violation(RULE_GITHUB_IDENTIFIER, dotted, line, target))

    if violations:
        _log.warning(
            "the lifecycle hot path reads GitHub",
            extra={"violations": [v.render() for v in violations], "law": HOT_PATH_LAW},
        )
    if missing:
        _log.warning(
            "a declared decision module is absent — the hot-path guard now covers less",
            extra={"missing": missing},
        )
    return HotPathReport(
        violations=violations, scanned=sorted(scanned), roots=sorted(roots), missing=sorted(missing),
    )


def offenders(package: Optional[Path] = None) -> List[str]:
    """Every violation, rendered — ``[]`` is the invariant (used by the cutover check)."""
    return [violation.render() for violation in sorted(
        check(package).violations, key=lambda v: (v.module, v.line, v.target))]


__all__ = [
    "DECISION_MODULES", "GH_COMMAND", "GITHUB_PACKAGES", "HOT_PATH_IDENTIFIERS", "HOT_PATH_LAW",
    "HotPathReport", "ImportBoundaryError", "PROVIDER_PREFIXES", "RULE_GH_SHELL_OUT",
    "RULE_GITHUB_API", "RULE_GITHUB_IDENTIFIER", "SEAM_MODULES", "Violation", "check",
    "decision_roots", "offenders",
]

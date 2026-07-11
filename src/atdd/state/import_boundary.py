"""The import-boundary guard — core never imports provider code (#1400 §8.1, C001).

> **Boundary law (spec §8.1).** Provider code imports core. Core never imports provider code.
> If a module needs the GitHub API, ``gh``, issue labels, or issue numbers to make a lifecycle
> decision, it is not core.

This walks the core import graph **statically**, with :mod:`ast`, and never imports a single
module it inspects. That is not an optimisation — it is the property the check lives or dies by.
A guard implemented as ``try: import github / except ImportError: pass`` passes on any machine
where the provider merely isn't installed, which is every CI runner core has, which means it
would have proved nothing at all. Source is read; nothing is executed. A module that raises on
import, or imports a package that does not exist anywhere, is scanned exactly the same.

Three rules, and they are three because they fail three different ways:

``provider-dependency``
    No module **transitively reachable** from a lifecycle module imports a provider, an HTTP
    client, or the GitHub API. Transitive, because a lifecycle module that imports a core helper
    that imports ``github`` has a GitHub dependency just as surely as if it typed it itself.

``registry-consultation``
    No module reachable from a lifecycle module imports the **provider registry**
    (:mod:`atdd.state.provider_seam`, :mod:`atdd.state.providers`). A lifecycle decision that
    *can* consult the registry can depend on a provider, whatever it does today (E001). Note the
    registry modules are named here as **strings**: importing them to check for them would be the
    very violation this rule exists to refuse.

``github-identifier``
    No **lifecycle** module reads a GitHub concept — ``issue_number``, ``issue_labels``, ``gh`` —
    as a code identifier. Restricted to identifiers (``ast.Name`` / ``ast.Attribute`` / keyword
    arguments): a *string* ``"issue_number"`` is a key inside the provider's own ``external_refs``
    subtree, which is data core carries and does not act on, and flagging it would be flagging the
    mirror for existing.

Plus ``gh`` shell-outs: a ``subprocess`` call whose argv begins with the literal ``"gh"`` is a
GitHub dependency that happens to be spelled without an import, and it is caught the same way.

Dependency discipline: stdlib only. This module is itself on the lifecycle hot path (the
merge-authority run's ``core-no-provider`` check calls it), so it may import nothing but stdlib.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

_log = logging.getLogger(__name__)

#: The law, quoted in every failure. A report that only says "forbidden import" tells the reader
#: what tripped; this tells them what they broke.
BOUNDARY_LAW = (
    "spec §8.1 — provider code imports core; core never imports provider code. Core must run a "
    "complete workflow with zero providers registered."
)

#: The modules that make lifecycle decisions. The roots of the walk.
LIFECYCLE_MODULES: Tuple[str, ...] = (
    "projection", "identity", "overlay", "reconcile", "metadata", "authoring",
    "trailers", "evidence", "crosscheck", "secrets", "merge_authority", "policy",
    "ownership", "merge_driver", "merge_matrix", "tombstone", "import_boundary",
)

#: Top-level packages that ARE the provider world. Reachable from lifecycle ⇒ the law is broken.
FORBIDDEN_PACKAGES: Tuple[str, ...] = (
    "github", "pygithub", "ghapi", "requests", "httpx", "urllib3",
)

#: Dotted prefixes that are forbidden even though their root package is core's own.
FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    "urllib.request", "http.client", "atdd.integrations",
)

#: The provider registry, as **strings**. Reaching it from lifecycle means a lifecycle decision
#: could consult a provider — so the check may not reach it either, and names it rather than
#: imports it.
REGISTRY_MODULES: Tuple[str, ...] = (
    "atdd.state.provider_seam", "atdd.state.providers", "atdd.state.sync_cli",
)

#: GitHub concepts, as code identifiers. See the ``github-identifier`` rule above for why string
#: literals are deliberately excluded.
GITHUB_IDENTIFIERS: frozenset = frozenset({
    "gh", "github", "pygithub", "issue_number", "issue_numbers",
    "issue_label", "issue_labels", "issue_url",
})

#: The command a ``gh`` shell-out starts with.
GH_COMMAND = "gh"

RULE_PROVIDER_DEPENDENCY = "provider-dependency"
RULE_REGISTRY_CONSULTATION = "registry-consultation"
RULE_GITHUB_IDENTIFIER = "github-identifier"
RULE_GH_SHELL_OUT = "gh-shell-out"


class ImportBoundaryError(RuntimeError):
    """The guard could not run (a package root that is not one, or unparseable source)."""


@dataclass(frozen=True)
class Violation:
    """One breach of the boundary law, named where it is and by what it imported."""

    rule: str
    module: str
    line: int
    target: str

    def render(self) -> str:
        return f"{self.module}:{self.line} [{self.rule}] {self.target}"


@dataclass(frozen=True)
class BoundaryReport:
    """The guard's verdict over one package."""

    violations: List[Violation] = field(default_factory=list)
    scanned: List[str] = field(default_factory=list)
    roots: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.ok:
            return (
                f"core's import graph is provider-free: {len(self.scanned)} module(s) reachable "
                f"from {len(self.roots)} lifecycle module(s), no provider / gh / GitHub-API "
                f"dependency.\n{BOUNDARY_LAW}"
            )
        lines = [
            f"the core/provider boundary is broken by {len(self.violations)} import(s):",
            *(f"  {violation.render()}" for violation in sorted(
                self.violations, key=lambda v: (v.module, v.line, v.target))),
            BOUNDARY_LAW,
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Resolving the graph — source files only; nothing is ever imported
# --------------------------------------------------------------------------- #
def _module_path(package_root: Path, dotted: str) -> Optional[Path]:
    """The source file a dotted ``atdd.*`` name resolves to inside this checkout, or ``None``.

    ``None`` means "not a first-party module" — a third-party or stdlib name, which the rules
    judge by name rather than by walking into it (core does not own its contents, and reading
    site-packages would make the check depend on what happens to be installed).
    """
    parts = dotted.split(".")
    if not parts or parts[0] != package_root.name:
        return None
    candidate = package_root.joinpath(*parts[1:])
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    if (candidate / "__init__.py").is_file():
        return candidate / "__init__.py"
    return None


def _imports_of(tree: ast.AST) -> List[Tuple[str, int]]:
    """Every dotted name a module imports, with its line. Relative imports are resolved by caller."""
    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.append((node.module, node.lineno))
    return found


def _is_forbidden(target: str) -> bool:
    root = target.split(".")[0]
    return root in FORBIDDEN_PACKAGES or any(
        target == prefix or target.startswith(prefix + ".") for prefix in FORBIDDEN_PREFIXES
    )


def _gh_shell_outs(tree: ast.AST) -> List[Tuple[str, int]]:
    """Every ``subprocess`` call whose argv starts with the literal ``gh``.

    A GitHub dependency spelled as a shell-out is still a GitHub dependency — and it is the one
    an import-only check would sail straight past.
    """
    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        argv = node.args[0]
        first: Optional[str] = None
        if isinstance(argv, (ast.List, ast.Tuple)) and argv.elts:
            head = argv.elts[0]
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                first = head.value
        elif isinstance(argv, ast.Constant) and isinstance(argv.value, str):
            first = argv.value.split()[0] if argv.value.split() else None
        if first is not None and Path(first).name == GH_COMMAND:
            found.append((f"shells out to `{GH_COMMAND}`", node.lineno))
    return found


def _github_identifiers(tree: ast.AST) -> List[Tuple[str, int]]:
    """GitHub concepts used as *code*: a name, an attribute, or a keyword argument."""
    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.lower() in GITHUB_IDENTIFIERS:
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute) and node.attr.lower() in GITHUB_IDENTIFIERS:
            found.append((f".{node.attr}", node.lineno))
        elif isinstance(node, ast.keyword) and node.arg and node.arg.lower() in GITHUB_IDENTIFIERS:
            found.append((f"{node.arg}=", node.lineno))
    return found


def _parse(path: Path) -> ast.AST:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ImportBoundaryError(f"{path} could not be parsed: {exc}") from exc


# --------------------------------------------------------------------------- #
# The walk (C001)
# --------------------------------------------------------------------------- #
def package_root(package: Optional[Path] = None) -> Path:
    """The ``atdd`` package directory this guard runs over (default: the one it lives in)."""
    if package is not None:
        root = Path(package).resolve()
        if not root.is_dir():
            raise ImportBoundaryError(f"{root} is not a package directory")
        return root
    return Path(__file__).resolve().parents[1]


def lifecycle_roots(root: Path, modules: Sequence[str] = LIFECYCLE_MODULES) -> List[str]:
    """The dotted names of the lifecycle modules present in ``root``."""
    return [
        f"{root.name}.state.{name}" for name in modules
        if (root / "state" / f"{name}.py").is_file()
    ]


def check(
    package: Optional[Path] = None, *, modules: Sequence[str] = LIFECYCLE_MODULES,
) -> BoundaryReport:
    """Walk the transitive import graph of every lifecycle module and judge it (C001).

    Deterministic and offline: it reads source files in sorted order and imports nothing, so it
    returns the same verdict on a machine with every provider installed and on one with none.
    """
    root = package_root(package)
    roots = lifecycle_roots(root, modules)
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
        is_root = dotted in roots

        for target, line in _imports_of(tree):
            if _is_forbidden(target):
                violations.append(Violation(RULE_PROVIDER_DEPENDENCY, dotted, line, target))
            elif target in REGISTRY_MODULES:
                violations.append(Violation(RULE_REGISTRY_CONSULTATION, dotted, line, target))
            elif target.startswith(root.name + "."):
                queue.append(target)

        for target, line in _gh_shell_outs(tree):
            violations.append(Violation(RULE_GH_SHELL_OUT, dotted, line, target))

        if is_root:
            for target, line in _github_identifiers(tree):
                violations.append(Violation(RULE_GITHUB_IDENTIFIER, dotted, line, target))

    if violations:
        _log.warning(
            "the core/provider import boundary is broken",
            extra={"violations": [v.render() for v in violations], "law": BOUNDARY_LAW},
        )
    return BoundaryReport(
        violations=violations, scanned=sorted(scanned), roots=sorted(roots),
    )


def offenders(package: Optional[Path] = None) -> List[str]:
    """Every violation, rendered — ``[]`` is the invariant (used by the merge-authority run)."""
    return [violation.render() for violation in sorted(
        check(package).violations, key=lambda v: (v.module, v.line, v.target))]

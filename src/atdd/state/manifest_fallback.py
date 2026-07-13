"""The manifest read-fallback is gone (#1400 migrate-projection-authority, CORE-034, Y002).

> **Y002.** Once projection is in blocking mode, no core reader consults ``.atdd/manifest.yaml``
> for shared lifecycle state. The manifest readers are **removed**, not deprecated in place.

A fallback is not a safety net; it is a second source of truth that only speaks up when the first
one is quiet. While `.atdd/manifest.yaml` still answers "what phase is #1234 in?", two developers
can hold two different answers and both be reading a file the tool told them to trust — and the
projection's whole claim, that peers share one committed state, is a claim about the code path
nobody takes. Deprecating the readers in place does not close that: a deprecated reader still
reads. So they go.

This module is the tripwire that keeps them gone. It scans core's source with :mod:`ast` and
refuses a manifest **read** — which is what Y002 names, in exactly these words: *no core module
**opens, globs, or parses** ``.atdd/manifest.yaml`` for lifecycle state.*

``manifest-read``
    A manifest path reaching a **read sink** (:data:`READ_SINKS`): ``open(…)``, ``.read_text()``,
    ``.glob(…)``, ``yaml.safe_load(…)``. The path may arrive inline
    (``open(root / "manifest.yaml")``) or through a name the module bound it to
    (``self.manifest_file = self.atdd_config_dir / "manifest.yaml"`` … ``open(self.manifest_file)``),
    so the scan does a small local dataflow: it learns which names hold a manifest path, then
    watches where those names are consumed.

Naming the path is **not** the offence; reading it is. A helper that hands the path to
``git commit`` writes the manifest out and never asks it a question — it cannot be a fallback
source of truth, because it does not source anything. Nor is prose: docstrings are ``Constant``
nodes too, and a module that *documents* the retirement is the opposite of a violation. Nor is
help text like "…imports .atdd/manifest.yaml…", which names the file without being a path to it.
Flagging those would have forced this wagon to delete code that was never the problem, and the
guard would have measured tidiness instead of authority.

Two module sets, and they are two because they mean different things:

:data:`SCANNED_PACKAGES`
    The core reader surface — where a manifest read would be a fallback source of truth.

:data:`LEGACY_MODULES`
    The declared, exempt few. :mod:`atdd.state.manifest_import` and
    :mod:`atdd.state.manifest_migration` exist *to read the legacy manifest once* and move it into
    the store and the projection; :mod:`atdd.state.manifest_projection` writes the compatibility
    mirror outward. Migration code reading the thing it migrates is not a fallback — it is the
    exit. They are named here so the exemption is a list a reviewer can shorten, not a hole.

Dependency discipline: stdlib only.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple

_log = logging.getLogger(__name__)

#: The law, quoted in every failure.
FALLBACK_LAW = (
    "spec §14 M8 / Y002 — the projection is the shared source of truth. No core reader may "
    "consult .atdd/manifest.yaml for shared lifecycle state; the readers are removed, not "
    "deprecated in place."
)

#: The manifest, as a filename. A path-forming constant, not a mention in prose.
MANIFEST_FILENAME = "manifest.yaml"

#: The core reader surface, relative to the ``atdd`` package. These are the places a lifecycle
#: read happens — and therefore the places a *fallback* read would.
SCANNED_PACKAGES: Tuple[str, ...] = (
    "state", "coach/commands", "coach/runtime", "coach/utils", "coach/validators",
    "train", "tester/validators", "planner", "coder",
)

#: The declared exemptions: migration code, which reads the legacy manifest **in order to retire
#: it**. Dotted, relative to ``atdd``. Shortening this list is how the retirement finishes.
LEGACY_MODULES: Tuple[str, ...] = (
    "state.manifest_import",      # legacy manifest → store (the one-time import)
    "state.manifest_migration",   # legacy manifest → committed projection (CORE-031)
    "state.manifest_projection",  # store → manifest mirror (an outward write, never a read)
    "state.manifest_fallback",    # this module: it names the file in order to forbid it
)

#: The read sinks — Y002's "opens, globs, or parses", as the calls that spell them.
#:
#: ``exists`` and ``is_file`` are **absent** on purpose: a presence check reads no lifecycle
#: state. Y002-UNIT-001 is the test of that claim — deleting the manifest must change no read
#: *result* — and a guard that skips a no-op when the file is gone changes no result.
READ_SINKS: frozenset = frozenset({
    "open", "read_text", "read_bytes", "safe_load", "full_load", "glob", "rglob", "iterdir",
})

RULE_MANIFEST_READ = "manifest-read"


class ManifestScanError(RuntimeError):
    """The scan could not run (an unparseable source file, or a package root that is not one)."""


@dataclass(frozen=True)
class ManifestRead:
    """One surviving manifest read path, named where it is."""

    rule: str
    module: str
    line: int
    target: str

    def render(self) -> str:
        return f"{self.module}:{self.line} [{self.rule}] {self.target!r}"


@dataclass(frozen=True)
class FallbackReport:
    """The verdict over the core reader surface."""

    reads: List[ManifestRead] = field(default_factory=list)
    scanned: List[str] = field(default_factory=list)
    exempt: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.reads

    def render(self) -> str:
        if self.ok:
            return (
                f"no core reader consults .atdd/{MANIFEST_FILENAME}: {len(self.scanned)} module(s) "
                f"scanned, {len(self.exempt)} declared migration module(s) exempt.\n{FALLBACK_LAW}"
            )
        lines = [
            f"the manifest read-fallback survives in {len(self.reads)} place(s):",
            *(f"  {read.render()}" for read in sorted(
                self.reads, key=lambda r: (r.module, r.line))),
            FALLBACK_LAW,
        ]
        return "\n".join(lines)


def _is_manifest_path(value: object) -> bool:
    """True when ``value`` is a *path-forming* reference to the manifest.

    ``"manifest.yaml"`` and ``".atdd/manifest.yaml"`` are paths. ``"imports .atdd/manifest.yaml
    into the store"`` is a sentence: it names the file without being a path to it, and a module
    that explains the retirement in its help text is not reading the manifest.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped == MANIFEST_FILENAME or stripped.endswith("/" + MANIFEST_FILENAME)


def _docstring_nodes(tree: ast.AST) -> Set[int]:
    """The ``id()`` of every docstring Constant — prose, not code, and never a read path."""
    found: Set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def _render(node: ast.AST) -> Optional[str]:
    """A dotted rendering of a name/attribute node — ``self.manifest_file``, ``manifest_path``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _render(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _holds_manifest_path(node: ast.AST, docstrings: Set[int]) -> bool:
    """True when the expression ``node`` builds a manifest path.

    Deliberately shallow: any manifest path constant *anywhere* inside the expression counts, so
    ``root / ".atdd" / "manifest.yaml"``, ``Path(".atdd/manifest.yaml")`` and a bare
    ``"manifest.yaml"`` are all recognised without modelling ``/`` overloading.
    """
    return any(
        isinstance(child, ast.Constant)
        and id(child) not in docstrings
        and _is_manifest_path(child.value)
        for child in ast.walk(node)
    )


def _manifest_names(tree: ast.AST, docstrings: Set[int]) -> Set[str]:
    """The names this module binds a manifest path to (``self.manifest_file``, ``_MANIFEST_REL``).

    One pass, no fixpoint: a module that launders the path through three intermediate variables
    before reading it is not a case that has ever occurred, and pretending to catch it would buy
    complexity with no defect.
    """
    names: Set[str] = set()
    for node in ast.walk(tree):
        targets: List[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets = [node.target]
        if not targets or node.value is None:
            continue
        if not _holds_manifest_path(node.value, docstrings):
            continue
        for target in targets:
            rendered = _render(target)
            if rendered:
                names.add(rendered)
    return names


def _reads_manifest(call: ast.Call, names: Set[str], docstrings: Set[int]) -> Optional[str]:
    """The manifest path this call *reads*, or ``None`` — Y002's "opens, globs, or parses".

    Two shapes, because a read arrives two ways:

    - ``open(x)`` / ``yaml.safe_load(x)``  — the path is an **argument** to a read function
    - ``x.read_text()`` / ``x.glob(…)``    — the path is the **receiver** of a read method
    """
    func = call.func
    sink = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if sink not in READ_SINKS:
        return None

    # The path as the receiver: `self.manifest_file.read_text()`.
    if isinstance(func, ast.Attribute):
        receiver = _render(func.value)
        if receiver in names:
            return receiver
        if _holds_manifest_path(func.value, docstrings):
            return ast.unparse(func.value)

    # The path as an argument: `open(self.manifest_file)`, `yaml.safe_load(p.read_text())`.
    for arg in call.args:
        rendered = _render(arg)
        if rendered in names:
            return rendered
        if _holds_manifest_path(arg, docstrings):
            return ast.unparse(arg)
    return None


def _manifest_reads(tree: ast.AST, module: str) -> List[ManifestRead]:
    """Every surviving manifest **read** in ``tree`` — a manifest path reaching a read sink."""
    docstrings = _docstring_nodes(tree)
    names = _manifest_names(tree, docstrings)
    return [
        ManifestRead(RULE_MANIFEST_READ, module, node.lineno, target)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for target in [_reads_manifest(node, names, docstrings)]
        if target is not None
    ]


def _parse(path: Path) -> ast.AST:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ManifestScanError(f"{path} could not be parsed: {exc}") from exc


def package_root(package: Optional[Path] = None) -> Path:
    """The ``atdd`` package directory this scan runs over (default: the one it lives in)."""
    if package is not None:
        root = Path(package).resolve()
        if not root.is_dir():
            raise ManifestScanError(f"{root} is not a package directory")
        return root
    return Path(__file__).resolve().parents[1]


def _sources(root: Path, packages: Sequence[str]) -> Iterable[Tuple[str, Path]]:
    """``(dotted, path)`` for every non-test source file under the scanned packages, sorted.

    Test modules are excluded: a test *about* the retired reader legitimately names the file it
    proves is no longer read.
    """
    for package in packages:
        base = root.joinpath(*package.split("/"))
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = path.relative_to(root).with_suffix("").parts
            if any(part in ("tests", "test") or part.startswith("test_") for part in parts):
                continue
            yield f"{root.name}." + ".".join(parts), path


def check(
    package: Optional[Path] = None,
    *,
    packages: Sequence[str] = SCANNED_PACKAGES,
    legacy: Sequence[str] = LEGACY_MODULES,
) -> FallbackReport:
    """Scan the core reader surface for a surviving manifest read path (Y002).

    Static and offline: source is parsed, never imported, so the verdict does not depend on
    whether a manifest happens to exist on the machine running the check.
    """
    root = package_root(package)
    exempt = {f"{root.name}.{name}" for name in legacy}
    reads: List[ManifestRead] = []
    scanned: List[str] = []

    for dotted, path in _sources(root, packages):
        if dotted in exempt:
            continue
        scanned.append(dotted)
        reads.extend(_manifest_reads(_parse(path), dotted))

    if reads:
        _log.warning(
            "the manifest read-fallback survives in core",
            extra={"reads": [r.render() for r in reads], "law": FALLBACK_LAW},
        )
    return FallbackReport(reads=reads, scanned=sorted(scanned), exempt=sorted(exempt))


def offenders(package: Optional[Path] = None) -> List[str]:
    """Every surviving manifest read, rendered — ``[]`` is the invariant."""
    return [read.render() for read in sorted(
        check(package).reads, key=lambda r: (r.module, r.line))]


__all__ = [
    "FALLBACK_LAW", "FallbackReport", "LEGACY_MODULES", "MANIFEST_FILENAME", "ManifestRead",
    "ManifestScanError", "READ_SINKS", "RULE_MANIFEST_READ", "SCANNED_PACKAGES", "check",
    "offenders", "package_root",
]

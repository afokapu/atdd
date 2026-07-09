"""Interlocking runtime-infrastructure detector for the five coder.train.interlocking-* conventions.

Realizes (one implementation, five strict rule_ids) the granular coder obligations that a consumer
interlocking declaring guarded routes ships an ``InterlockingRunner`` route-control layer (core
afokapu/atdd#1251, Part of #1246):

  * coder.train.interlocking-runner-exists            — runner class + resolve_train entry point
  * coder.train.interlocking-resolution-model-exists  — structured resolution metadata, not a bare id
  * coder.train.station-master-interlocking-routing   — Station Master routes through it + delegates
  * coder.train.interlocking-delegates-to-trainrunner — no direct wagon execution / TrainRunner dup
  * coder.train.interlocking-does-not-carry-cargo      — Cargo stays inside TrainRunner; wagons clean

Each detection category maps to exactly one of these rule_ids (CATEGORY_RULE).

PURE detector: the caller supplies the scan root (a consumer tree); this walks the scope's
``python_runtime`` (``python/trains/**/*.py``) + ``station_master`` (``python/app.py``) selectors with
``ast`` and returns RAW violations in the v1.1 violation-output shape
``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1 §3.2). It NEVER decides
disposition; the strict verdict (any violation -> FAIL) is a downstream consumer concern.

Pure stdlib (``ast``, ``pathlib``, ``os``, ``json``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

# The five convention rule_ids this detector realizes (all disposition: strict). One implementation
# emits all five; each detection category maps to exactly one rule_id (CATEGORY_RULE below).
RULE_RUNNER_EXISTS = "coder.train.interlocking-runner-exists"
RULE_RESOLUTION_MODEL = "coder.train.interlocking-resolution-model-exists"
RULE_STATION_ROUTING = "coder.train.station-master-interlocking-routing"
RULE_DELEGATES = "coder.train.interlocking-delegates-to-trainrunner"
RULE_NO_CARGO = "coder.train.interlocking-does-not-carry-cargo"

ALL_RULE_IDS = frozenset(
    {
        RULE_RUNNER_EXISTS,
        RULE_RESOLUTION_MODEL,
        RULE_STATION_ROUTING,
        RULE_DELEGATES,
        RULE_NO_CARGO,
    }
)

# Structured-resolution model contract (core afokapu/atdd#1251 InterlockingResolution).
REQUIRED_RESOLUTION_FIELDS = frozenset(
    {
        "interlocking_id",
        "route_id",
        "train_id",
        "train_path",
        "category",
        "category_digit",
        "guard_id",
        "reason",
    }
)

# Evidence category prefixes — stable tokens so the verdict layer / tests can classify a RAW
# violation without parsing free text. They are part of ``evidence``; the v1.1 shape is unchanged.
CAT_MISSING_RUNNER = "missing-interlocking-runner"
CAT_MISSING_RESOLVE = "missing-resolve-train"
CAT_BARE_RESOLUTION = "bare-train-id-resolution"
CAT_STATION_UNLINKED = "station-master-unlinked"
CAT_STATION_NO_DELEGATE = "station-master-no-trainrunner-delegation"
CAT_DIRECT_WAGON_EXEC = "interlocking-direct-wagon-execution"
CAT_CARGO_MUTATION = "interlocking-cargo-mutation"
CAT_WAGON_IMPORTS_INTERLOCKING = "wagon-imports-interlocking"

# Each detection category belongs to exactly one convention rule_id. The category token stays in the
# evidence string for human triage; the emitted ``rule_id`` is the mapped convention id.
CATEGORY_RULE = {
    CAT_MISSING_RUNNER: RULE_RUNNER_EXISTS,
    CAT_MISSING_RESOLVE: RULE_RUNNER_EXISTS,
    CAT_BARE_RESOLUTION: RULE_RESOLUTION_MODEL,
    CAT_STATION_UNLINKED: RULE_STATION_ROUTING,
    CAT_STATION_NO_DELEGATE: RULE_STATION_ROUTING,
    CAT_DIRECT_WAGON_EXEC: RULE_DELEGATES,
    CAT_CARGO_MUTATION: RULE_NO_CARGO,
    CAT_WAGON_IMPORTS_INTERLOCKING: RULE_NO_CARGO,
}


# ── file discovery ─────────────────────────────────────────────────────────────


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _first_line(path: Path) -> str:
    text = _read(path)
    return text.splitlines()[0] if text else ""


def _line_at(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def _parse(path: Path) -> ast.Module | None:
    text = _read(path)
    if not text:
        return None
    try:
        return ast.parse(text, filename=str(path))
    except SyntaxError:
        # A consumer file that does not parse is not this detector's concern; skip it.
        return None


def _train_files(root: Path) -> list[Path]:
    base = root / "python" / "trains"
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _wagon_files(root: Path) -> list[Path]:
    base = root / "python"
    if not base.is_dir():
        return []
    # Wagons live at python/<wagon>/wagon.py; exclude the trains/ runtime subtree.
    trains = base / "trains"
    out: list[Path] = []
    for p in sorted(base.rglob("wagon.py")):
        if p.is_file() and trains not in p.parents:
            out.append(p)
    return out


def _app_file(root: Path) -> Path | None:
    app = root / "python" / "app.py"
    return app if app.is_file() else None


# ── AST fact extraction ────────────────────────────────────────────────────────


def _identifiers(tree: ast.AST) -> set[str]:
    """Every Name id, Attribute attr, and imported name/module token in a module."""
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.update(node.module.split("."))
            seen.update(a.name.split(".")[0] for a in node.names)
            seen.update(a.asname for a in node.names if a.asname)
        elif isinstance(node, ast.Import):
            for a in node.names:
                seen.update(a.name.split("."))
                if a.asname:
                    seen.add(a.asname)
    return seen


def _find_class(tree: ast.AST, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _class_methods(cls: ast.ClassDef) -> set[str]:
    return {
        n.name
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _resolution_model_fields(tree: ast.AST) -> set[str] | None:
    """Annotated/assigned field names of an ``InterlockingResolution`` class, or None if absent."""
    cls = _find_class(tree, "InterlockingResolution")
    if cls is None:
        return None
    fields: set[str] = set()
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields.add(node.target.id)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    fields.add(t.id)
    return fields


def _imports_wagon(tree: ast.AST) -> list[ast.stmt]:
    """Import statements that pull in a wagon module (module path containing a ``wagon`` segment)."""
    hits: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "wagon" in node.module.split("."):
                hits.append(node)
        elif isinstance(node, ast.Import):
            if any("wagon" in a.name.split(".") for a in node.names):
                hits.append(node)
    return hits


def _imports_interlocking(tree: ast.AST) -> list[ast.stmt]:
    """Import statements that pull in interlocking code (module token or InterlockingRunner name)."""
    hits: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod_tokens = node.module.split(".") if node.module else []
            names = {a.name for a in node.names}
            if any("interlocking" in t for t in mod_tokens) or "InterlockingRunner" in names:
                hits.append(node)
        elif isinstance(node, ast.Import):
            if any("interlocking" in seg for a in node.names for seg in a.name.split(".")):
                hits.append(node)
    return hits


def _run_train_calls(tree: ast.AST) -> list[ast.Call]:
    hits: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "run_train":
                hits.append(node)
            elif isinstance(func, ast.Attribute) and func.attr == "run_train":
                hits.append(node)
    return hits


def _sequence_loops(tree: ast.AST) -> list[ast.stmt]:
    """`for ... in <expr>.sequence:` loops — an interlocking acting as a step executor."""
    hits: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)):
            it = node.iter
            if isinstance(it, ast.Attribute) and it.attr == "sequence":
                hits.append(node)
    return hits


def _docstring_constants(tree: ast.AST) -> set[int]:
    """ids of string Constant nodes that are docstrings / bare string statements (not real uses)."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                skip.add(id(node.value))
    return skip


def _cargo_uses(tree: ast.AST) -> list[tuple[int, int, str]]:
    """References that bleed Cargo into the interlocking layer: Cargo symbol, cargo subscript
    assignment, or an ``artifact_urn`` string literal. Returns (line, col, detail).

    Docstrings / bare string statements are not real Cargo uses and are skipped.
    """
    docstrings = _docstring_constants(tree)
    hits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Cargo":
            hits.append((node.lineno, node.col_offset, "references the Cargo symbol"))
        elif isinstance(node, ast.Attribute) and node.attr == "Cargo":
            hits.append((node.lineno, node.col_offset, "references the Cargo symbol"))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if (
                    isinstance(t, ast.Subscript)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "cargo"
                ):
                    hits.append((t.lineno, t.col_offset, "mutates a cargo mapping"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "artifact_urn" in node.value and id(node) not in docstrings:
                hits.append((node.lineno, node.col_offset, "stores an artifact_urn value"))
    return hits


def _journey_map_routes(tree: ast.AST) -> tuple[bool, list[int], bool]:
    """Inspect the ``JOURNEY_MAP`` assignment. Returns
    (has_interlocking_route, interlocking_route_linenos, has_direct_route)."""
    has_interlocking = False
    has_direct = False
    linenos: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "JOURNEY_MAP" for t in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        for v in value.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                has_direct = True
            elif isinstance(v, ast.Dict):
                keys = {
                    k.value
                    for k in v.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                if "interlocking_id" in keys:
                    has_interlocking = True
                    linenos.append(v.lineno)
    return has_interlocking, linenos, has_direct


# ── violation emission ──────────────────────────────────────────────────────────


def _violation(root: Path, path: Path, line: int, col: int, category: str, detail: str) -> dict:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return {
        "rule_id": CATEGORY_RULE[category],
        "file": str(rel),
        "line": line,
        "col": col,
        "evidence": f"{category}: {detail}",
        "source_line": _line_at(_read(path), line) or _first_line(path),
    }


def scan_root(root: Path) -> list[dict]:
    """Scan a single consumer tree and return RAW violations.

    The rule only bites an *interlocking-enabled* consumer: one whose Station Master declares an
    interlocking route object, or whose runtime defines an ``InterlockingRunner``. A pure direct-train
    consumer carries no obligation and yields no violations.
    """
    root = Path(root)
    violations: list[dict] = []

    train_files = _train_files(root)
    app = _app_file(root)

    # InterlockingRunner-defining modules + a merged view of resolution-model fields across runtime.
    runner_files: list[tuple[Path, ast.Module, ast.ClassDef]] = []
    resolution_fields: set[str] | None = None
    for f in train_files:
        tree = _parse(f)
        if tree is None:
            continue
        fields = _resolution_model_fields(tree)
        if fields is not None:
            resolution_fields = (resolution_fields or set()) | fields
        cls = _find_class(tree, "InterlockingRunner")
        if cls is not None:
            runner_files.append((f, tree, cls))

    # Station Master facts.
    app_tree = _parse(app) if app is not None else None
    has_interlocking_route = False
    interlocking_route_lines: list[int] = []
    app_idents: set[str] = set()
    if app_tree is not None:
        has_interlocking_route, interlocking_route_lines, _ = _journey_map_routes(app_tree)
        app_idents = _identifiers(app_tree)

    enabled = has_interlocking_route or bool(runner_files)
    if not enabled:
        return []

    # 1. InterlockingRunner must exist when interlocking routes are declared.
    if has_interlocking_route and not runner_files and app is not None:
        line = interlocking_route_lines[0] if interlocking_route_lines else 1
        violations.append(
            _violation(
                root, app, line, 0, CAT_MISSING_RUNNER,
                "JOURNEY_MAP declares an interlocking route but no InterlockingRunner class exists "
                "under python/trains/ (core afokapu/atdd#1251)",
            )
        )

    # 2/3. resolve_train + structured resolution model.
    has_resolve_train = False
    for f, _tree, cls in runner_files:
        methods = _class_methods(cls)
        if "resolve_train" in methods:
            has_resolve_train = True
        else:
            violations.append(
                _violation(
                    root, f, cls.lineno, cls.col_offset, CAT_MISSING_RESOLVE,
                    "InterlockingRunner has no resolve_train(...) entry point",
                )
            )

    if has_resolve_train:
        if resolution_fields is None or not REQUIRED_RESOLUTION_FIELDS.issubset(resolution_fields):
            target_file, _t, cls = runner_files[0]
            missing = sorted(REQUIRED_RESOLUTION_FIELDS - (resolution_fields or set()))
            violations.append(
                _violation(
                    root, target_file, cls.lineno, cls.col_offset, CAT_BARE_RESOLUTION,
                    "resolve_train resolves a bare train_id; a structured InterlockingResolution model "
                    f"is missing required field(s): {', '.join(missing)}",
                )
            )

    # 4. Station Master wiring: must reference InterlockingRunner and delegate to TrainRunner.
    if app is not None and has_interlocking_route:
        line = interlocking_route_lines[0] if interlocking_route_lines else 1
        if "InterlockingRunner" not in app_idents:
            violations.append(
                _violation(
                    root, app, line, 0, CAT_STATION_UNLINKED,
                    "Station Master declares an interlocking route but never references "
                    "InterlockingRunner",
                )
            )
        if "TrainRunner" not in app_idents:
            violations.append(
                _violation(
                    root, app, line, 0, CAT_STATION_NO_DELEGATE,
                    "Station Master never references TrainRunner; the selected train must be executed "
                    "by TrainRunner",
                )
            )

    # 5/6. The InterlockingRunner-defining modules must not execute wagons or touch Cargo.
    for f, tree, _cls in runner_files:
        for stmt in _imports_wagon(tree):
            violations.append(
                _violation(
                    root, f, stmt.lineno, stmt.col_offset, CAT_DIRECT_WAGON_EXEC,
                    "interlocking module imports a wagon module directly",
                )
            )
        for call in _run_train_calls(tree):
            violations.append(
                _violation(
                    root, f, call.lineno, call.col_offset, CAT_DIRECT_WAGON_EXEC,
                    "interlocking module calls run_train(...) directly",
                )
            )
        for loop in _sequence_loops(tree):
            violations.append(
                _violation(
                    root, f, loop.lineno, loop.col_offset, CAT_DIRECT_WAGON_EXEC,
                    "interlocking module loops over train.sequence as a step executor",
                )
            )
        for line, col, detail in _cargo_uses(tree):
            violations.append(
                _violation(root, f, line, col, CAT_CARGO_MUTATION, f"interlocking module {detail}")
            )

    # 7. Wagons must not import interlocking code.
    for f in _wagon_files(root):
        tree = _parse(f)
        if tree is None:
            continue
        for stmt in _imports_interlocking(tree):
            violations.append(
                _violation(
                    root, f, stmt.lineno, stmt.col_offset, CAT_WAGON_IMPORTS_INTERLOCKING,
                    "wagon module imports interlocking code (Cargo boundary violation)",
                )
            )

    return violations


def scan_roots(roots: list[Path]) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r)))
    return out


def detect(*args, **kwargs):
    """Back-compat entry point. Accepts a single scan-root (path) or a list of roots."""
    if not args:
        raise ValueError("detect() requires a scan root (path) or a list of roots")
    target = args[0]
    if isinstance(target, (list, tuple, set)):
        return scan_roots([Path(p) for p in target])
    return scan_root(Path(target))


__all__ = ["ALL_RULE_IDS", "CATEGORY_RULE", "scan_root", "scan_roots", "detect"]


if __name__ == "__main__":  # pragma: no cover - manual invocation aid
    import sys

    targets = sys.argv[1:] or ["."]
    print(json.dumps(scan_roots([Path(t) for t in targets]), indent=2))

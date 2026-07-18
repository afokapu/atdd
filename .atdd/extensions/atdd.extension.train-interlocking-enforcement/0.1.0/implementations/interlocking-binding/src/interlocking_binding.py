"""Interlocking bilateral-binding detector (python-pytest realization of #27).

Realizes the single EXTENSION obligation
``coder.train.interlocking-bilateral-binding`` (disposition ``strict``, severity 1),
authored as a convention node in this package's ``conventions/`` directory. This
module is the python-pytest DETECTOR that realizes it; it does not re-author the
obligation.

An interlocking system is SYSTEMIC, not descriptive: it requires CLOSURE across
declaration (the interlocking YAML route space, core afokapu/atdd#1248), runtime
resolution (InterlockingRunner, core afokapu/atdd#1251), Station Master
reachability (the entrypoint JOURNEY_MAP), TrainRunner delegation, and the
execution trace. The detector emits RAW v1.1 violations under the one rule_id for
any of FIVE binding directions that is broken:

  * declaration_to_runtime  — every declared route's train artifact exists, so the
    InterlockingRunner can load and delegate it.
  * runtime_to_declaration  — the InterlockingRunner never resolves a
    route_id/train_id literal absent from the loaded YAML (hidden route).
  * station_to_declaration  — every Station Master ``{interlocking_id, path}``
    mapping points to an existing interlocking YAML.
  * declaration_to_station  — every interlocking with core ``entrypoint.exposed:
    true`` is reachable via a declared ``entrypoint.action`` wired into JOURNEY_MAP
    to that interlocking. CONSUMES core afokapu/atdd#1248's entrypoint field.
  * trace_to_declaration    — every asserted ``trace["route_id"]`` /
    ``trace["interlocking_id"]`` value resolves back to a declared route in the YAML.

It also rejects a PARALLEL reachability field (``entrypoints``,
``runtime_exposure``, ``station_actions``, ``exposed_actions``, ``reachability``)
that forks core #1248's ``entrypoint`` — reported as schema drift under the same
rule_id (direction ``parallel_reachability_field``).

The detector is PURE: the caller supplies the scan root (a consumer tree) and it
returns RAW violations in the v1.1 violation-output shape
``{rule_id, file, line, col, evidence, source_line}``. It NEVER decides
disposition — ``strict`` lives in the convention node; whether a RAW signal blocks
is the gate's job (``gates/interlocking-binding.gate.yaml``).

Provenance (boundary spec §6.2 — NARRATIVE, not graph edges): the route +
entrypoint fields parsed here are core afokapu/atdd#1248; the runner call model +
trace are core afokapu/atdd#1251. No ``atdd.*`` substrate is imported.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml  # provider runtime dependency (cli/scan.py + adapter/discover.py use it)

# The one convention rule_id this detector realizes (disposition: strict). The broken binding
# DIRECTION is named in the evidence (stable token prefix), mirroring the infrastructure detector's
# CATEGORY tokens — so the verdict layer / tests can classify a RAW violation without parsing free text.
RULE_BILATERAL = "coder.train.interlocking-bilateral-binding"
RULE_ID = RULE_BILATERAL  # single-rule alias
ALL_RULE_IDS = (RULE_BILATERAL,)

# Binding direction tokens (the convention's `bidirectional` directions) + the schema-drift signal.
DIR_DECL_RUNTIME = "declaration_to_runtime"
DIR_RUNTIME_DECL = "runtime_to_declaration"
DIR_STATION_DECL = "station_to_declaration"
DIR_DECL_STATION = "declaration_to_station"
DIR_TRACE_DECL = "trace_to_declaration"
DIR_PARALLEL_FIELD = "parallel_reachability_field"

ALL_DIRECTIONS = (
    DIR_DECL_RUNTIME,
    DIR_RUNTIME_DECL,
    DIR_STATION_DECL,
    DIR_DECL_STATION,
    DIR_TRACE_DECL,
    DIR_PARALLEL_FIELD,
)

# Where the authoritative guarded route space + entrypoint live (core #1248).
_INTERLOCKING_GLOBS = (
    "plan/_trains/_interlockings/**/*.yaml",
    "plan/_trains/_interlockings.yaml",
)
_E2E_GLOB = "e2e/**/*.py"
_TRAIN_DIR = "plan/_trains"

# Forbidden parallel reachability fields — anything that forks core #1248's `entrypoint`.
_PARALLEL_FIELDS = (
    "entrypoints",
    "runtime_exposure",
    "station_actions",
    "exposed_actions",
    "reachability",
)

# Resolution-output keyword args the InterlockingRunner runtime sets (core #1251 InterlockingResolution).
_RESOLUTION_ROUTE_KW = "route_id"
_RESOLUTION_TRAIN_KW = frozenset({"train_id", "selected_train_id"})

# trace["route_id"] == "X" / trace["interlocking_id"] == "X" asserted constants in e2e trace tests.
_TRACE_ASSERT = re.compile(
    r"""trace\s*\[\s*["'](?P<field>interlocking_id|route_id)["']\s*\]\s*==\s*["'](?P<value>[^"']+)["']"""
)
_TRACE_OBJECT = re.compile(r"\btrace\b")


# ---------------------------------------------------------------------------
# IO helpers (pure)
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _line_at(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def _line_of(text: str, pattern: re.Pattern, default: int = 1) -> tuple[int, str]:
    for i, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return i, line
    return default, ""


def _violation(rule_id: str, file: str, line: int, col: int, direction: str, detail: str, source_line: str) -> dict:
    return {
        "rule_id": rule_id,
        "file": file,
        "line": line,
        "col": col,
        "evidence": f"{direction}: {detail}",
        "source_line": source_line,
    }


# ---------------------------------------------------------------------------
# Parsing the interlocking artifact (pure) — CONSUMES core #1248 entrypoint field
# ---------------------------------------------------------------------------


def _route_lineno(text: str, route_id: str) -> tuple[int, str]:
    pat = re.compile(
        r"""^\s*-?\s*route_id:\s*["']?""" + re.escape(route_id) + r"""["']?\s*(?:#.*)?$"""
    )
    for i, line in enumerate(text.splitlines(), start=1):
        if pat.match(line):
            return i, line
    return 1, ""


def parse_interlocking(text: str) -> dict | None:
    """Parse one interlocking YAML into ``{interlocking_id, routes, exposed, actions,
    parallel_fields, raw_text}`` or ``None`` when it carries no route space.

    Reads ONLY core afokapu/atdd#1248 fields (interlocking_id, routes[*], entrypoint.exposed,
    entrypoint.actions); ``parallel_fields`` records any forked reachability field found so the
    schema-drift check can report it. Never defines a parallel field of its own.
    """
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(doc, dict):
        return None
    interlocking_id = doc.get("interlocking_id")
    raw_routes = doc.get("routes")
    if not interlocking_id or not isinstance(raw_routes, list):
        return None

    routes: list[dict] = []
    for entry in raw_routes:
        if not isinstance(entry, dict) or "route_id" not in entry:
            continue
        route_id = str(entry["route_id"])
        lineno, source_line = _route_lineno(text, route_id)
        routes.append(
            {
                "route_id": route_id,
                "train_id": (str(entry["train_id"]) if entry.get("train_id") is not None else None),
                "train_path": (str(entry["train_path"]) if entry.get("train_path") is not None else None),
                "line": lineno,
                "source_line": source_line,
            }
        )
    if not routes:
        return None

    entrypoint = doc.get("entrypoint") or {}
    if not isinstance(entrypoint, dict):
        entrypoint = {}
    exposed = bool(entrypoint.get("exposed"))
    raw_actions = entrypoint.get("actions")
    actions = [str(a) for a in raw_actions] if isinstance(raw_actions, list) else []

    # Detect any forked reachability field (top-level OR nested under entrypoint).
    parallel_fields = [f for f in _PARALLEL_FIELDS if f in doc or f in entrypoint]

    return {
        "interlocking_id": str(interlocking_id),
        "routes": routes,
        "exposed": exposed,
        "actions": actions,
        "parallel_fields": parallel_fields,
        "raw_text": text,
    }


# ---------------------------------------------------------------------------
# Parsing the Station Master JOURNEY_MAP (AST, pure)
# ---------------------------------------------------------------------------


def _parse(text: str) -> ast.Module | None:
    if not text:
        return None
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def parse_journey_map(text: str) -> dict[str, dict]:
    """Return ``{action: {kind, interlocking_id?, path?, train_id?, line}}`` from a Station Master
    JOURNEY_MAP assignment, or ``{}`` when absent. ``kind`` is ``"interlocking"`` for an
    ``{interlocking_id, path}`` route object and ``"direct"`` for a bare train_id string."""
    tree = _parse(text)
    if tree is None:
        return {}
    out: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "JOURNEY_MAP" for t in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        for key, val in zip(value.keys, value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            action = key.value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                out[action] = {"kind": "direct", "train_id": val.value, "line": getattr(val, "lineno", 1)}
            elif isinstance(val, ast.Dict):
                fields: dict[str, str] = {}
                for k, v in zip(val.keys, val.values):
                    if (
                        isinstance(k, ast.Constant)
                        and isinstance(k.value, str)
                        and isinstance(v, ast.Constant)
                        and isinstance(v.value, str)
                    ):
                        fields[k.value] = v.value
                if "interlocking_id" in fields or "path" in fields:
                    out[action] = {
                        "kind": "interlocking",
                        "interlocking_id": fields.get("interlocking_id"),
                        "path": fields.get("path"),
                        "line": getattr(val, "lineno", 1),
                    }
    return out


def runtime_resolution_literals(text: str) -> list[tuple[str, str, int, int]]:
    """Keyword args the runtime sets when building a resolution: ``(kind, value, line, col)`` where
    ``kind`` is ``"route"`` (route_id=...) or ``"train"`` (train_id/selected_train_id=...)."""
    tree = _parse(text)
    if tree is None:
        return []
    out: list[tuple[str, str, int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg is None or not isinstance(kw.value, ast.Constant) or not isinstance(kw.value.value, str):
                continue
            if kw.arg == _RESOLUTION_ROUTE_KW:
                out.append(("route", kw.value.value, kw.value.lineno, kw.value.col_offset))
            elif kw.arg in _RESOLUTION_TRAIN_KW:
                out.append(("train", kw.value.value, kw.value.lineno, kw.value.col_offset))
    return out


# ---------------------------------------------------------------------------
# Filesystem scope walk
# ---------------------------------------------------------------------------


def find_interlocking_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for glob in _INTERLOCKING_GLOBS:
        found.extend(p for p in root.glob(glob) if p.is_file())
    return sorted(set(found))


def find_e2e_files(root: Path) -> list[Path]:
    return sorted(p for p in root.glob(_E2E_GLOB) if p.is_file())


def find_runtime_files(root: Path) -> list[Path]:
    base = root / "python" / "trains"
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _app_file(root: Path) -> Path | None:
    app = root / "python" / "app.py"
    return app if app.is_file() else None


def _train_artifact_exists(root: Path, route: dict) -> bool:
    """True if the route's train artifact exists (train_path, else plan/_trains/<train_id>.yaml)."""
    train_path = route.get("train_path")
    if train_path:
        return (root / train_path).is_file()
    train_id = route.get("train_id")
    if train_id:
        return (root / _TRAIN_DIR / f"{train_id}.yaml").is_file()
    return False


# ---------------------------------------------------------------------------
# Direction 1 — declaration_to_runtime
# ---------------------------------------------------------------------------


def _declaration_to_runtime_violations(records: dict[Path, dict], root: Path) -> list[dict]:
    out: list[dict] = []
    for il_file, rec in records.items():
        rel = _rel(il_file, root)
        for route in rec["routes"]:
            if _train_artifact_exists(root, route):
                continue
            target = route.get("train_path") or (
                f"{_TRAIN_DIR}/{route.get('train_id')}.yaml" if route.get("train_id") else "<no train_id>"
            )
            out.append(
                _violation(
                    RULE_BILATERAL, rel, route.get("line", 1), 0, DIR_DECL_RUNTIME,
                    f"declared route {route['route_id']!r} of interlocking {rec['interlocking_id']!r} is "
                    f"not runtime-resolvable: its train artifact {target!r} does not exist, so "
                    f"InterlockingRunner -> TrainRunner cannot resolve it to a declared train_id",
                    route.get("source_line", ""),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Direction 2 — runtime_to_declaration (no hidden routes)
# ---------------------------------------------------------------------------


def _runtime_to_declaration_violations(
    records: dict[Path, dict], runtime_files: list[tuple[Path, str]], root: Path
) -> list[dict]:
    declared_routes = {r["route_id"] for rec in records.values() for r in rec["routes"]}
    declared_trains = {r["train_id"] for rec in records.values() for r in rec["routes"] if r["train_id"]}
    out: list[dict] = []
    for path, text in runtime_files:
        if "InterlockingResolution" not in text and "resolve_train" not in text:
            continue  # only InterlockingRunner runtime modules resolve routes.
        rel = _rel(path, root)
        for kind, value, line, col in runtime_resolution_literals(text):
            declared = declared_routes if kind == "route" else declared_trains
            if value in declared:
                continue
            label = "route_id" if kind == "route" else "train_id"
            out.append(
                _violation(
                    RULE_BILATERAL, rel, line, col, DIR_RUNTIME_DECL,
                    f"InterlockingRunner resolves {label} {value!r} which is declared in no interlocking "
                    f"YAML (hidden route); every resolved route/train must come from the loaded route space",
                    _line_at(text, line),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Direction 3 — station_to_declaration (mappings point to existing YAML)
# ---------------------------------------------------------------------------


def _station_to_declaration_violations(
    journey: dict[str, dict], records: dict[Path, dict], app: Path | None, root: Path
) -> list[dict]:
    if app is None:
        return []
    declared_ids = {rec["interlocking_id"] for rec in records.values()}
    text = _read(app)
    rel = _rel(app, root)
    out: list[dict] = []
    for action, mapping in journey.items():
        if mapping.get("kind") != "interlocking":
            continue
        path = mapping.get("path")
        line = mapping.get("line", 1)
        if path and not (root / path).is_file():
            out.append(
                _violation(
                    RULE_BILATERAL, rel, line, 0, DIR_STATION_DECL,
                    f"Station Master action {action!r} maps to interlocking path {path!r} which does not "
                    f"exist; the mapping must point to a real interlocking YAML",
                    _line_at(text, line),
                )
            )
        il_id = mapping.get("interlocking_id")
        if il_id and il_id not in declared_ids:
            out.append(
                _violation(
                    RULE_BILATERAL, rel, line, 0, DIR_STATION_DECL,
                    f"Station Master action {action!r} maps to interlocking_id {il_id!r} which is declared "
                    f"by no interlocking YAML in the route space",
                    _line_at(text, line),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Direction 4 — declaration_to_station (exposed interlockings are reachable)
# ---------------------------------------------------------------------------


def _interlocking_reachable(rec: dict, il_file: Path, journey: dict[str, dict], root: Path) -> bool:
    """True if some declared entrypoint.action maps in JOURNEY_MAP to THIS interlocking."""
    for action in rec["actions"]:
        mapping = journey.get(action)
        if not mapping or mapping.get("kind") != "interlocking":
            continue
        if mapping.get("interlocking_id") == rec["interlocking_id"]:
            return True
        path = mapping.get("path")
        if path and (root / path).resolve() == il_file.resolve():
            return True
    return False


def _declaration_to_station_violations(
    records: dict[Path, dict], journey: dict[str, dict], root: Path
) -> list[dict]:
    out: list[dict] = []
    for il_file, rec in records.items():
        if not rec["exposed"]:
            continue  # entrypoint.exposed:false carries no reachability obligation (core #1248).
        if _interlocking_reachable(rec, il_file, journey, root):
            continue
        rel = _rel(il_file, root)
        text = rec["raw_text"]
        lineno, src = _line_of(text, re.compile(r"^\s*exposed:\s*true\b"))
        actions = ", ".join(rec["actions"]) or "<none>"
        out.append(
            _violation(
                RULE_BILATERAL, rel, lineno, 0, DIR_DECL_STATION,
                f"interlocking {rec['interlocking_id']!r} has entrypoint.exposed:true but is not "
                f"Station-Master-reachable: none of its entrypoint.actions [{actions}] is wired into "
                f"JOURNEY_MAP to this interlocking (core afokapu/atdd#1248 entrypoint.exposed/actions)",
                src,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Schema drift — parallel reachability field (forks core #1248 entrypoint)
# ---------------------------------------------------------------------------


def _parallel_field_violations(records: dict[Path, dict], root: Path) -> list[dict]:
    out: list[dict] = []
    for il_file, rec in records.items():
        if not rec["parallel_fields"]:
            continue
        rel = _rel(il_file, root)
        text = rec["raw_text"]
        for field in rec["parallel_fields"]:
            lineno, src = _line_of(text, re.compile(r"^\s*" + re.escape(field) + r"\s*:"))
            out.append(
                _violation(
                    RULE_BILATERAL, rel, lineno, 0, DIR_PARALLEL_FIELD,
                    f"interlocking {rec['interlocking_id']!r} declares a parallel reachability field "
                    f"{field!r}; reachability is owned by core afokapu/atdd#1248's `entrypoint` "
                    f"(exposed/actions/reason) — this extension must not fork it (schema drift)",
                    src,
                )
            )
    return out


# ---------------------------------------------------------------------------
# Direction 5 — trace_to_declaration (trace binds back to source YAML)
# ---------------------------------------------------------------------------


def _trace_to_declaration_violations(
    records: dict[Path, dict], e2e_files: list[tuple[Path, str]], root: Path
) -> list[dict]:
    declared_routes = {r["route_id"] for rec in records.values() for r in rec["routes"]}
    declared_ids = {rec["interlocking_id"] for rec in records.values()}
    out: list[dict] = []
    for path, text in e2e_files:
        if not _TRACE_OBJECT.search(text):
            continue  # not a trace-asserting test.
        rel = _rel(path, root)
        for m in _TRACE_ASSERT.finditer(text):
            field, value = m.group("field"), m.group("value")
            declared = declared_ids if field == "interlocking_id" else declared_routes
            if value in declared:
                continue
            lineno = text.count("\n", 0, m.start()) + 1
            out.append(
                _violation(
                    RULE_BILATERAL, rel, lineno, 0, DIR_TRACE_DECL,
                    f"interlocking trace test asserts trace[{field!r}] == {value!r}, which resolves to no "
                    f"declared {('interlocking' if field == 'interlocking_id' else 'route')} in the YAML "
                    f"route space; the trace must bind the executed route back to its declaration",
                    _line_at(text, lineno),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Aggregate scan
# ---------------------------------------------------------------------------


def scan_root(root: Path) -> list[dict]:
    """Scan one consumer ``root`` and return RAW v1.1 violations for all binding directions.

    The rule only bites an interlocking system: a root with a declared interlocking route space OR an
    InterlockingRunner runtime. The detector NEVER applies disposition — ``strict`` is the gate's call.
    """
    root = Path(root)
    if not root.exists():
        return []

    records: dict[Path, dict] = {}
    for il_file in find_interlocking_files(root):
        rec = parse_interlocking(_read(il_file))
        if rec is not None:
            records[il_file] = rec

    runtime_files = [(p, _read(p)) for p in find_runtime_files(root)]
    app = _app_file(root)
    journey = parse_journey_map(_read(app)) if app is not None else {}
    e2e_files = [(p, _read(p)) for p in find_e2e_files(root)]

    enabled = bool(records) or any(
        "InterlockingRunner" in t or "InterlockingResolution" in t for _p, t in runtime_files
    )
    if not enabled:
        return []

    violations: list[dict] = []
    violations += _declaration_to_runtime_violations(records, root)
    violations += _runtime_to_declaration_violations(records, runtime_files, root)
    violations += _station_to_declaration_violations(journey, records, app, root)
    violations += _declaration_to_station_violations(records, journey, root)
    violations += _parallel_field_violations(records, root)
    violations += _trace_to_declaration_violations(records, e2e_files, root)
    return violations


def scan_roots(roots: list[Path]) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r)))
    return out


def detect(roots) -> list[dict]:
    """Public entrypoint: RAW violations across all binding directions. Accepts a path or list."""
    if isinstance(roots, (list, tuple, set)):
        return scan_roots([Path(r) for r in roots])
    return scan_root(Path(roots))


__all__ = [
    "RULE_BILATERAL",
    "ALL_RULE_IDS",
    "ALL_DIRECTIONS",
    "parse_interlocking",
    "parse_journey_map",
    "runtime_resolution_literals",
    "scan_root",
    "scan_roots",
    "detect",
]


if __name__ == "__main__":  # pragma: no cover - manual invocation aid
    import sys

    targets = sys.argv[1:] or ["."]
    print(json.dumps(scan_roots([Path(t) for t in targets]), indent=2))

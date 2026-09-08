"""Interlocking tester detector (python-pytest realization of #26).

Realizes FOUR stack-bound EXTENSION obligations (all disposition ``strict``,
severity 1), authored as convention nodes in this extension package's
``conventions/`` directory; this module is the python-pytest DETECTOR that
realizes them — it does not re-author the obligations:

  * ``tester.interlocking.route-coverage`` — every admissible route declared in an
    interlocking's guarded route space (``routes:`` of
    ``plan/_trains/_interlockings/**/*.yaml``, core afokapu/atdd#1248) has an
    ``e2e/**/*.py`` test exercising it (referenced by ``route_id`` or ``train_id``).
  * ``tester.interlocking.production-runner-used`` — interlocking e2e tests drive
    the production ``InterlockingRunner`` + ``TrainRunner`` (core #1251), never a
    mock / patched / monkeypatched runner or a hand-built route resolver.
  * ``tester.interlocking.smoke-coverage-for-station-master`` — every EXPOSED
    Station Master action (``entrypoint.exposed: true``) has a smoke test that
    reaches the Station Master and drives both runners.
  * ``tester.interlocking.trace-binds-declared-route`` — any test asserting on the
    runtime ``trace`` binds the declared route by asserting every required trace
    field (core #1251 trace contract).

The detector is PURE: the caller supplies the scan roots (a consumer tree carrying
the interlocking YAML + the ``e2e/`` tests) and it returns RAW violations in the
ATDD v1.1 violation-output contract ``{rule_id, file, line, col, evidence,
source_line}``. It NEVER decides disposition — ``strict`` lives in the convention
nodes, and whether a RAW signal blocks is the gate's job, never the detector's.

Scope selectors (scopes/interlocking-targets.scope.yaml): ``interlocking_yaml``
(route space + entrypoint) + ``e2e_tests`` (the covering / smoke / trace tests).

Provenance (boundary spec §6.2 — NARRATIVE, not graph edges): the route +
entrypoint fields parsed here are core afokapu/atdd#1248; the runner call model +
trace are core afokapu/atdd#1251. No ``atdd.coach.*`` substrate is imported.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml  # provider runtime dependency (cli/scan.py + adapter/discover.py use it)

# Rule ids this detector realizes (NOT new nodes; the nodes live in conventions/).
RULE_ROUTE_COVERAGE = "tester.interlocking.route-coverage"            # disposition: strict
RULE_PRODUCTION_RUNNER = "tester.interlocking.production-runner-used"  # disposition: strict
RULE_SMOKE = "tester.interlocking.smoke-coverage-for-station-master"   # disposition: strict
RULE_TRACE = "tester.interlocking.trace-binds-declared-route"          # disposition: strict
RULE_ID = RULE_ROUTE_COVERAGE  # back-compat alias (single-rule callers)

ALL_RULE_IDS = (RULE_ROUTE_COVERAGE, RULE_PRODUCTION_RUNNER, RULE_SMOKE, RULE_TRACE)

# Where the authoritative guarded route space + entrypoint live (core #1248).
_INTERLOCKING_GLOBS = (
    "plan/_trains/_interlockings/**/*.yaml",
    "plan/_trains/_interlockings.yaml",
)
_E2E_GLOB = "e2e/**/*.py"

# Production runner symbols (core #1251 call model).
_PROD_INTERLOCKING = "InterlockingRunner"
_PROD_TRAIN = "TrainRunner"

# Required trace-binding fields, transcribed from core's own
# ``InterlockingResolution.as_trace()`` (src/atdd/runtime/interlocking/runner.py).
#
# ``route_category_digit`` is NOT here: core retired the category digit (#1421 / #1440) and
# its own test pins the trace to the ``category`` FIELD, noting the digit field "no longer
# means anything". Requiring it made this rule reject traces core itself emits.
#
# The ``(?!_)`` on route_category is kept and now does migration work: it stops a legacy
# consumer that emits only ``route_category_digit`` from silently satisfying
# ``route_category``. Such a consumer is missing the field and must still fail.
_REQUIRED_TRACE_FIELDS: list[tuple[str, re.Pattern]] = [
    ("interlocking_id", re.compile(r"\binterlocking_id\b")),
    ("route_id", re.compile(r"\broute_id\b")),
    ("selected_train_id", re.compile(r"\bselected_train_id\b")),
    ("route_category", re.compile(r"\broute_category\b(?!_)")),
    ("guard_id", re.compile(r"\bguard_id\b")),
    ("resolution_strategy", re.compile(r"\bresolution_strategy\b")),
    ("resolution_reason", re.compile(r"\bresolution_reason\b")),
]

# Forbidden runner-substitution patterns (production-runner-used).
_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("MockInterlockingRunner", re.compile(r"\bMockInterlockingRunner\b")),
    ("MockTrainRunner", re.compile(r"\bMockTrainRunner\b")),
    (
        "patch() around runner execution",
        re.compile(
            r"patch\s*\(\s*[^)]*"
            r"(?:InterlockingRunner|TrainRunner|resolve_train|\.execute)"
        ),
    ),
    (
        "monkeypatch replacing runner behavior",
        re.compile(
            r"monkeypatch\.setattr\s*\(\s*[^)]*"
            r"(?:InterlockingRunner|TrainRunner|resolve_train|execute)"
        ),
    ),
    (
        "hand-built route resolver replacing InterlockingRunner",
        re.compile(r"(?m)^\s*(?:async\s+def\s+resolve_train|def\s+resolve_train|class\s+\w*Resolver)\b"),
    ),
]

# A bare `trace` identifier (the captured trace object) — NOT `capture_trace`
# (the `_` before `trace` is a word char, so `\btrace\b` does not match it).
# A test makes a BINDING CLAIM when it reads a trace field that identifies the route.
#
# This was `\btrace\b` alone, which pulled in any test that merely used the word. A
# sequence test asserting `trace["steps"] == declared` makes no claim about WHICH route
# ran, yet was required to assert all eight binding fields — and the natural fix,
# renaming the local variable, would have papered over the detector rather than fixing
# it. Found by running this package against a purpose-built consumer.
#
# Reading ONE binding field still trips the rule, which is the intent: a test that
# asserts route_id and nothing else is exactly the partial binding this rule refuses.
_TRACE_OBJECT = re.compile(
    r"\btrace\b[^\n]*\b(?:interlocking_id|route_id|selected_train_id|route_category"
    r"|guard_id|resolution_strategy|resolution_reason)\b"
    r"|\b(?:interlocking_id|route_id|selected_train_id)\b[^\n]*\btrace\b"
)
# REACHING THE STATION MASTER, detected STRUCTURALLY rather than by naming.
#
# This was `\b(?:StationMaster|station_master)\b` alone, which required a consumer's
# smoke test to contain a symbol literally named StationMaster. Nothing asks for that
# name. `coder.train.station-master-interlocking-routing` defines the Station Master as
# `python/app.py` carrying a `JOURNEY_MAP` — structure, not nomenclature — and the
# coder detector matches it that way. A consumer whose entrypoint is a module-level
# `dispatch()` in app.py therefore PASSED the coder rule and FAILED this one, with no
# documented way to satisfy both. The old pattern matched only because this package's
# own fixture happens to export a class called StationMaster.
#
# Any of these is evidence a test reaches the Station Master: the StationMaster name,
# an import of / reference to the `app` entrypoint module, or JOURNEY_MAP — the
# structure the coder rule says defines it.
_STATION_MASTER = re.compile(
    r"\b(?:StationMaster|station_master|stationMaster)\b"
    r"|\bJOURNEY_MAP\b"
    r"|^\s*(?:import|from)\s+app\b"
    r"|\bapp\.[A-Za-z_]",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Parsing the interlocking artifact (pure)
# ---------------------------------------------------------------------------


def _route_lineno(text: str, route_id: str) -> tuple[int, str]:
    pat = re.compile(
        r"""^\s*-?\s*route_id:\s*["']?""" + re.escape(route_id) + r"""["']?\s*(?:#.*)?$"""
    )
    for i, line in enumerate(text.splitlines(), start=1):
        if pat.match(line):
            return i, line
    return 1, ""


def _line_of(text: str, pattern: re.Pattern, default: int = 1) -> tuple[int, str]:
    for i, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return i, line
    return default, ""


def parse_interlocking(text: str) -> dict | None:
    """Parse one interlocking YAML into a normalized record, or ``None``.

    Returns ``{interlocking_id, routes, exposed, actions, raw_text}`` for a
    document that declares both ``interlocking_id`` and a non-empty ``routes:``
    list. The ``_interlockings.yaml`` index and the generated ``coverage.yaml`` /
    ``sequence.*`` projections carry no route space and yield ``None``.
    """
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        # Malformed YAML is a planner/core concern; surface nothing rather than crash.
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
                "train_id": (
                    str(entry["train_id"]) if entry.get("train_id") is not None else None
                ),
                "category": entry.get("category"),
                "guard_ref": entry.get("guard_ref"),
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
    return {
        "interlocking_id": str(interlocking_id),
        "routes": routes,
        "exposed": exposed,
        "actions": actions,
        "raw_text": text,
    }


def parse_routes(text: str) -> tuple[str | None, list[dict]]:
    """Back-compat shim: ``(interlocking_id, routes)`` (route-coverage callers)."""
    rec = parse_interlocking(text)
    if rec is None:
        return None, []
    return rec["interlocking_id"], rec["routes"]


# ---------------------------------------------------------------------------
# Shared token helpers (pure)
# ---------------------------------------------------------------------------


def _token_covered(token: str | None, text: str) -> bool:
    """True if ``token`` appears in ``text`` not flanked by identifier chars."""
    if not token:
        return False
    return bool(re.search(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", text))


def is_route_covered(route: dict, e2e_texts: list[str]) -> bool:
    """True if any e2e test references the route by ``route_id`` or ``train_id``."""
    for text in e2e_texts:
        if _token_covered(route.get("route_id"), text) or _token_covered(
            route.get("train_id"), text
        ):
            return True
    return False


def _interlocking_token_set(records: list[dict]) -> set[str]:
    """All route/train/interlocking ids across the parsed records (scoping set)."""
    tokens: set[str] = set()
    for rec in records:
        tokens.add(rec["interlocking_id"])
        for r in rec["routes"]:
            if r.get("route_id"):
                tokens.add(r["route_id"])
            if r.get("train_id"):
                tokens.add(r["train_id"])
    return {t for t in tokens if t}


def _is_interlocking_test(text: str, tokens: set[str]) -> bool:
    """True if an e2e file is interlocking-related (references the route space or a runner)."""
    if _PROD_INTERLOCKING in text or _PROD_TRAIN in text or "resolve_train" in text:
        return True
    return any(_token_covered(tok, text) for tok in tokens)


# ---------------------------------------------------------------------------
# Filesystem scope walk (scope supplied explicitly — never auto-discovered)
# ---------------------------------------------------------------------------


def find_interlocking_files(root: Path) -> list[Path]:
    root = Path(root)
    found: list[Path] = []
    for glob in _INTERLOCKING_GLOBS:
        found.extend(p for p in root.glob(glob) if p.is_file())
    return sorted(set(found))


def find_e2e_files(root: Path) -> list[Path]:
    root = Path(root)
    return sorted(p for p in root.glob(_E2E_GLOB) if p.is_file())


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


# ---------------------------------------------------------------------------
# Rule 1 — route coverage
# ---------------------------------------------------------------------------


def _route_coverage_violations(
    records_by_file: dict[Path, dict], e2e_texts: list[str], root: Path
) -> list[dict]:
    out: list[dict] = []
    for il_file, rec in records_by_file.items():
        rel = _rel(il_file, root)
        for route in rec["routes"]:
            if is_route_covered(route, e2e_texts):
                continue
            category, train = route.get("category"), route.get("train_id")
            # The digit that used to appear here is retired (#1421 / #1440); with the key
            # gone from every artifact it could only ever render "(digit None)".
            cat_desc = f"category {category!r}" if category is not None else "uncategorised"
            out.append(
                {
                    "rule_id": RULE_ROUTE_COVERAGE,
                    "file": rel,
                    "line": route.get("line", 1),
                    "col": 0,
                    "evidence": (
                        f"admissible route {route['route_id']!r} of interlocking "
                        f"{rec['interlocking_id']!r} ({cat_desc}, resolves to train "
                        f"{train!r}) has no e2e test exercising it; add an e2e/**/*.py "
                        f"test that references the route_id or train_id and drives it "
                        f"through InterlockingRunner -> TrainRunner"
                    ),
                    "source_line": route.get("source_line", ""),
                }
            )
    return out


# ---------------------------------------------------------------------------
# Rule 2 — production runner used (no mocks)
# ---------------------------------------------------------------------------


def _production_runner_violations(
    e2e_files: list[tuple[Path, str]], tokens: set[str], root: Path
) -> list[dict]:
    out: list[dict] = []
    for path, text in e2e_files:
        if not _is_interlocking_test(text, tokens):
            continue
        rel = _rel(path, root)
        lines = text.splitlines()
        # (a) forbidden substitution patterns.
        for label, pat in _FORBIDDEN_PATTERNS:
            m = pat.search(text)
            if m:
                lineno = text.count("\n", 0, m.start()) + 1
                src = lines[lineno - 1] if 1 <= lineno <= len(lines) else ""
                out.append(
                    {
                        "rule_id": RULE_PRODUCTION_RUNNER,
                        "file": rel,
                        "line": lineno,
                        "col": 0,
                        "evidence": (
                            f"interlocking test {rel!r} substitutes the production "
                            f"runner ({label}); drive InterlockingRunner -> TrainRunner "
                            f"directly instead"
                        ),
                        "source_line": src,
                    }
                )
        # (b) must reference both production runner symbols.
        missing = [
            sym
            for sym in (_PROD_INTERLOCKING, _PROD_TRAIN)
            if not _token_covered(sym, text)
        ]
        if missing:
            out.append(
                {
                    "rule_id": RULE_PRODUCTION_RUNNER,
                    "file": rel,
                    "line": 1,
                    "col": 0,
                    "evidence": (
                        f"interlocking test {rel!r} does not reference the production "
                        f"runner(s) {', '.join(missing)}; it must exercise the real "
                        f"InterlockingRunner -> TrainRunner path (core #1251)"
                    ),
                    "source_line": "",
                }
            )
    return out


# ---------------------------------------------------------------------------
# Rule 3 — smoke coverage for exposed Station Master actions
# ---------------------------------------------------------------------------


def _action_smoke_covered(action: str, e2e_files: list[tuple[Path, str]]) -> bool:
    """True if some e2e file is a smoke test for ``action`` (reaches SM + both runners)."""
    for _path, text in e2e_files:
        if (
            _token_covered(action, text)
            and _STATION_MASTER.search(text)
            and _PROD_INTERLOCKING in text
            and _PROD_TRAIN in text
        ):
            return True
    return False


def _smoke_violations(
    records_by_file: dict[Path, dict], e2e_files: list[tuple[Path, str]], root: Path
) -> list[dict]:
    out: list[dict] = []
    for il_file, rec in records_by_file.items():
        if not rec["exposed"]:
            continue  # internal (exposed:false) interlockings are out of scope (policy).
        rel = _rel(il_file, root)
        text = rec["raw_text"]
        for action in rec["actions"]:
            if _action_smoke_covered(action, e2e_files):
                continue
            lineno, src = _line_of(
                text, re.compile(r"^\s*-\s*" + re.escape(action) + r"\s*$")
            )
            out.append(
                {
                    "rule_id": RULE_SMOKE,
                    "file": rel,
                    "line": lineno,
                    "col": 0,
                    "evidence": (
                        f"exposed Station Master action {action!r} of interlocking "
                        f"{rec['interlocking_id']!r} has no smoke test reaching the "
                        f"Station Master and driving InterlockingRunner -> TrainRunner; "
                        f"add an e2e smoke test (strict: exposed actions are critical "
                        f"user-facing routes)"
                    ),
                    "source_line": src,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Rule 4 — trace binds the declared route
# ---------------------------------------------------------------------------


#: An assert comparing the trace to a whole mapping — `assert trace == expected`.
#: That form asserts every field at once, so the per-field search must not reject it.
#: `assert trace == expected` — the trace compared AS A WHOLE, with nothing between
#: the name and the operator. The first cut allowed anything in between, so
#: `assert trace["route_id"] == "..."` matched and every per-field assertion silently
#: switched the whole check off — a fix that disabled the rule it was fixing. Caught
#: by the package's own dirty fixture, which asserts six of eight fields.
_WHOLE_TRACE_ASSERT = re.compile(r"^\s*assert\s+[\w.]*\btrace\b\s*==(?![=])", re.MULTILINE)


def asserted_text(text: str) -> str:
    """Only the parts of a source that ASSERT something.

    The rule's own statement is that a test "must assert every required trace
    field". The check searched the WHOLE file for each field NAME, so a field
    mentioned anywhere — in a dict literal, a comment, an unrelated list — counted
    as asserted. A smoke test whose only assertion was `assert trace` passed a
    severity-1 strict rule that the gate blocks on, while binding nothing.
    """
    return "\n".join(line for line in text.split("\n") if "assert" in line)


def missing_trace_fields(text: str) -> list[str]:
    """Required trace fields ABSENT from the given text (order-preserving).

    Pure field detection, with no opinion about where it looked. Kept separate from
    the assert-scoping below so each can be tested on its own: conflating them made
    a unit test of field distinction fail for reasons that had nothing to do with
    field distinction.
    """
    return [label for label, pat in _REQUIRED_TRACE_FIELDS if not pat.search(text)]


def unasserted_trace_fields(text: str) -> list[str]:
    """Required trace fields the source never ASSERTS.

    The rule's own statement is that a test "must assert every required trace
    field". The check searched the WHOLE source for each field NAME, so a field
    mentioned anywhere — a dict literal, a comment, an unrelated list — counted as
    asserted.

    A whole-mapping assertion (`assert trace == expected`) covers every field at
    once and is accepted as such; narrowing to per-field asserts without that
    escape would trade a real defect for a false positive against a legitimate test.
    """
    if _WHOLE_TRACE_ASSERT.search(text):
        return []
    return missing_trace_fields(asserted_text(text))


def _trace_violations(
    e2e_files: list[tuple[Path, str]], tokens: set[str], root: Path
) -> list[dict]:
    out: list[dict] = []
    for path, text in e2e_files:
        if not _is_interlocking_test(text, tokens):
            continue
        m = _TRACE_OBJECT.search(text)
        if not m:
            continue  # not a trace-binding test.
        missing = unasserted_trace_fields(text)
        if not missing:
            continue
        rel = _rel(path, root)
        lines = text.splitlines()
        lineno = text.count("\n", 0, m.start()) + 1
        src = lines[lineno - 1] if 1 <= lineno <= len(lines) else ""
        out.append(
            {
                "rule_id": RULE_TRACE,
                "file": rel,
                "line": lineno,
                "col": 0,
                "evidence": (
                    f"interlocking trace test {rel!r} does not bind the declared route: "
                    f"missing required trace field(s) {', '.join(missing)} "
                    f"(core's InterlockingResolution.as_trace records "
                    f"{'/'.join(label for label, _ in _REQUIRED_TRACE_FIELDS)})"
                ),
                "source_line": src,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Aggregate scan
# ---------------------------------------------------------------------------


def scan_root(root: Path) -> list[dict]:
    """Scan one consumer ``root`` and return RAW v1.1 violations for all 4 rules.

    The detector NEVER applies disposition — ``strict`` is the gate's call.
    """
    root = Path(root)
    if not root.exists():
        return []

    e2e_files = [(p, _read(p)) for p in find_e2e_files(root)]
    e2e_texts = [t for _p, t in e2e_files]

    records_by_file: dict[Path, dict] = {}
    for il_file in find_interlocking_files(root):
        rec = parse_interlocking(_read(il_file))
        if rec is not None:
            records_by_file[il_file] = rec
    tokens = _interlocking_token_set(list(records_by_file.values()))

    violations: list[dict] = []
    violations += _route_coverage_violations(records_by_file, e2e_texts, root)
    violations += _production_runner_violations(e2e_files, tokens, root)
    violations += _smoke_violations(records_by_file, e2e_files, root)
    violations += _trace_violations(e2e_files, tokens, root)
    return violations


def scan_roots(roots: list[Path]) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r)))
    return out


def detect(roots: list[Path]) -> list[dict]:
    """Public entrypoint: RAW violations across all 4 interlocking tester rules."""
    return scan_roots([Path(r) for r in roots])


# ---------------------------------------------------------------------------
# STAGED — tester.interlocking.train-sequence-is-exercised
#
# The tester half of coder.train.runtime-executes-the-declaration. That rule makes
# the runtime READ the plan; this one makes the suite prove it OBEYS it. Neither is
# worth much alone: a runtime that reads the plan but is never tested against it
# still drifts silently, and a suite that asserts a sequence against a runtime which
# hardcodes it proves only that the hardcoding is self-consistent.
#
# Staged exactly as its coder sibling is: emitted by `scan_execution`, deliberately
# NOT called from `scan_root`, because no consumer or fixture satisfies it yet and
# wiring an advisory concern into a strict gate would escalate it silently.
# ---------------------------------------------------------------------------

RULE_SEQUENCE = "tester.interlocking.train-sequence-is-exercised"

#: A line that ASSERTS AN ORDER: mentions the executed sequence AND compares it.
#:
#: The first cut was `\b(?:steps|sequence|wagons)\b` alone, which counted a bare
#: `assert trace["steps"]` truthiness check as coverage — the same over-broad trigger
#: that makes `\btrace\b` drag unrelated tests into trace-binding. Merely touching the
#: word is not asserting the order.
_SEQUENCE_ASSERTION = re.compile(
    r"^\s*assert\b[^\n]*\b(?:steps|sequence|wagons)\b[^\n]*==", re.MULTILINE
)


def trains_reachable_from_routes(records: list[dict]) -> set[str]:
    """Train ids a declared route can select. The rule follows the route space."""
    return {
        route["train_id"]
        for rec in records
        for route in rec.get("routes") or []
        if route.get("train_id")
    }


def asserts_a_sequence(text: str) -> bool:
    """True if this test COMPARES an executed order, not merely mentions one."""
    return _SEQUENCE_ASSERTION.search(text) is not None


def train_sequence_covered(train_id: str, e2e_texts: list[str]) -> bool:
    """A test both names the train and asserts on what it ran."""
    return any(_token_covered(train_id, text) and asserts_a_sequence(text) for text in e2e_texts)


def scan_execution(root: Path) -> list[dict]:
    """Declared trains whose executed wagon sequence no test asserts.

    Route coverage proves an admissible route is exercised and trace binding proves
    the run is attributable to its declared route. Both are statements about
    SELECTION. A train whose sequence is wrong is selected correctly and runs the
    wrong thing — demonstrated by replacing a train's whole `sequence:` on a
    data-driven consumer and watching its suite stay green.
    """
    root = Path(root)
    records = [r for r in (parse_interlocking(_read(f)) for f in find_interlocking_files(root)) if r]
    if not records:
        return []
    e2e = [(f, _read(f)) for f in find_e2e_files(root)]
    texts = [text for _f, text in e2e]
    anchor = _rel(e2e[0][0], root) if e2e else "e2e/"

    return [
        {
            "rule_id": RULE_SEQUENCE,
            "file": anchor,
            "line": 1,
            "col": 1,
            "evidence": (
                f"declared train {train_id!r} is selected by a route but no test asserts the "
                f"wagon SEQUENCE it executes; reorder or empty its definition and the suite "
                f"stays green"
            ),
            "source_line": "",
        }
        for train_id in sorted(trains_reachable_from_routes(records))
        if not train_sequence_covered(train_id, texts)
    ]

"""python-pytest detector for tester.acceptance-violation.metric-implementation-must-exist.

REALIZES the agnostic CORE obligation
``tester.acceptance-violation.metric-implementation-must-exist`` (disposition
``strict``, severity 4) for the Python stack. The obligation node is authored in
CORE (``src/atdd/tester/conventions/nodes/
tester.acceptance-violation.metric-implementation-must-exist.convention.yaml``);
this module is the python-pytest DETECTOR that realizes it — it is NOT a new node
and does not re-author the obligation.

When an acceptance declares ``signal.metric: <name>`` (the non-test measurability
path), a backing implementation MUST exist so the metric runner can compute the
value. The Python two-root lookup (substrate spec v12 §4.5, recipe
``metric-implementation``) is, in order, first-hit-wins:

    1. <root>/.atdd/metrics/<name>.py        (consumer-authored; takes precedence)
    2. <root>/src/atdd/runners/metrics/<name>.py   (toolkit-shipped commons)

and the module MUST import cleanly and export a top-level CALLABLE named
``compute``. A declared metric with no such module — a module that fails to
import, or one that does not export a callable ``compute`` — is a measurability
hole that would let an acceptance pass vacuously.

RESOLUTION IS IMPORT-BASED (parity with core, NOT a ``^def compute`` regex).
The legacy oracle (``atdd.runners.metric_runner.discover_metric_module``, used by
``test_metric_implementation.collect_violations``) decides "resolvable" by:
  1. the candidate file existing,
  2. importing cleanly (import-time errors → treated as ABSENT → flagged), and
  3. exporting ``callable(getattr(module, "compute", None))``.
``passes`` is OPTIONAL — the conformance oracle never required it (the metric
runner owns the ``passes`` semantic, and many metrics are upper/lower-bound
checked elsewhere). An earlier extension build regressed this to a pair of
``^def compute`` / ``^def passes`` regexes, which (a) FALSELY flagged a metric
whose ``compute`` is a lambda, an imported name, or any non-``def`` callable,
(b) FALSELY required a ``passes`` symbol core never required, and (c) MISSED
modules that exist but fail to import (a regex sees the text, an import sees the
error). This module restores the import + ``callable`` resolution so it matches
the legacy verdict site-for-site. First RESOLVABLE candidate wins; a candidate
that exists but fails to import / lacks a callable ``compute`` falls through to
the next root, exactly as ``discover_metric_module`` does.

This detector inspects the consumer's acceptance declarations (``*.yaml``) and the
two metric lookup roots, all under the supplied ``ATDD_SCAN_ROOTS``.

PROVENANCE — derived from core
    src/atdd/tester/conventions/metric-implementation.recipe.yaml (the two-root
    lookup) and
    src/atdd/tester/validators/test_metric_implementation.py
        :: test_every_signal_metric_has_compute_function, which delegates
    resolution to ``atdd.runners.metric_runner.discover_metric_module``
    (import + ``callable(compute)``). That resolution is RE-IMPLEMENTED here in
    pure stdlib (``importlib.util``); the ``atdd.coach.*`` substrate couplings
    were REMOVED.

DECOUPLED FROM CORE (the 4 couplings, per task GOTCHAS):
  * ``bind_rule(...)``  ->  module-level ``RULE_METRIC_IMPLEMENTATION_MUST_EXIST``
    constant. Severity 4 / disposition strict live in the CORE convention node.
  * ``Violation``  ->  plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}``.
  * ``find_repo_root`` + repo scan  ->  REMOVED. The metric lookup roots are
    resolved RELATIVE to each supplied ``ATDD_SCAN_ROOTS`` entry; never
    auto-discovered from a repo root.
  * ``assert_disposition_satisfied`` (the disposition gate)  ->  OMITTED. The
    detector emits RAW violations; strict enforcement is the consumer's decision.

Pure stdlib (``re``, ``importlib``, ``pathlib``) — no third-party (no PyYAML) or
core imports. The minimal block/inline ``signal.metric`` scan avoids a YAML
dependency and keeps accurate line numbers for the v1.1 report.
"""
from __future__ import annotations

import fnmatch
import importlib.util
import re
from pathlib import Path
from types import ModuleType

# The CORE convention rule_id this detector realizes (NOT a new node).
RULE_METRIC_IMPLEMENTATION_MUST_EXIST = (
    "tester.acceptance-violation.metric-implementation-must-exist"  # disposition: strict
)

# The two metric lookup roots, in precedence order (relative to a scan root).
METRIC_LOOKUP_ROOTS = (
    Path(".atdd") / "metrics",
    Path("src") / "atdd" / "runners" / "metrics",
)

_SIGNAL_OPEN = re.compile(r"^(\s*)signal:\s*$")
_METRIC_LINE = re.compile(r"""^(\s*)metric:\s*["']?([A-Za-z0-9_.\-]+)["']?\s*$""")
_INLINE_METRIC = re.compile(r"""signal:\s*\{[^}]*?metric:\s*["']?([A-Za-z0-9_.\-]+)""")


# ---------------------------------------------------------------------------
# Detection (pure — unit-tested directly against source strings)
# ---------------------------------------------------------------------------


def find_metric_declarations(source: str) -> list[tuple[int, str, str]]:
    """Return ``(lineno, metric_name, source_line)`` for each ``signal.metric``.

    Pure function over YAML source text. Handles both the block form::

        signal:
          metric: latency_p95

    and the inline form ``signal: {metric: latency_p95, threshold: 200}``. Other
    ``metric:`` keys (not nested under a ``signal:`` block) are ignored.
    """
    lines = source.splitlines()
    found: list[tuple[int, str, str]] = []
    signal_indent: int | None = None
    for i, line in enumerate(lines, start=1):
        inline = _INLINE_METRIC.search(line)
        if inline:
            found.append((i, inline.group(1), line))
            continue

        open_m = _SIGNAL_OPEN.match(line)
        if open_m:
            signal_indent = len(open_m.group(1))
            continue

        if signal_indent is not None:
            stripped = line.strip()
            metric_m = _METRIC_LINE.match(line)
            if metric_m and len(metric_m.group(1)) > signal_indent:
                found.append((i, metric_m.group(2), line))
                continue
            # A non-blank, non-comment line at or below the signal indent closes it.
            if stripped and not stripped.startswith("#"):
                indent = len(line) - len(line.lstrip())
                if indent <= signal_indent:
                    signal_indent = None
    return found


def _load_module_from_path(path: Path) -> ModuleType | None:
    """Import ``path`` as an isolated module by file location, or ``None``.

    Mirrors ``atdd.runners.metric_runner._load_module_from_path``: a unique spec
    name keeps two consumers' same-named modules from shadowing each other via
    ``sys.modules``, and ANY import-time error (ImportError, SyntaxError, a
    raising top-level statement, …) is swallowed to ``None`` so the caller treats
    the module as absent — exactly how the legacy oracle flags a broken metric.
    """
    try:
        unique_name = (
            f"_atdd_metric_{path.parent.name}_{path.stem}_{abs(hash(str(path.resolve())))}"
        )
        spec = importlib.util.spec_from_file_location(unique_name, str(path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        # Import-time failure → the metric is unresolvable → caller flags it.
        return None


def metric_module_ok(scan_root: Path, name: str) -> bool:
    """True if a backing module for ``name`` resolves to a callable ``compute``.

    Walks the two lookup roots (consumer first, toolkit second). For each that
    EXISTS, the module must import cleanly AND export a ``callable`` named
    ``compute``; a candidate that fails either check FALLS THROUGH to the next
    root (it does not shadow a good toolkit module). ``passes`` is NOT required.

    This is the import + ``callable`` resolution the legacy oracle uses
    (``discover_metric_module``), not a ``^def compute`` regex — so a lambda /
    imported / otherwise non-``def`` ``compute`` resolves, a ``passes``-less
    module resolves, and a module that exists but fails to import is flagged.
    """
    for rel in METRIC_LOOKUP_ROOTS:
        candidate = Path(scan_root) / rel / f"{name}.py"
        if not candidate.is_file():
            continue
        module = _load_module_from_path(candidate)
        if module is None:
            continue  # exists but fails to import → treat as absent
        if not callable(getattr(module, "compute", None)):
            continue  # exists/imports but no callable compute → treat as absent
        return True
    return False


# ---------------------------------------------------------------------------
# Scan-root walk (scope supplied via ATDD_SCAN_ROOTS — never auto-discovered)
# ---------------------------------------------------------------------------


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one project ``root`` and return RAW v1.1 violation dicts.

    For every ``signal.metric`` declared in a ``*.yaml`` acceptance under ``root``,
    verify a backing compute()/passes() module exists in one of the two lookup
    roots (resolved relative to ``root``). Each missing implementation is one
    ``{rule_id, file, line, col, evidence, source_line}`` violation. The detector
    NEVER applies the strict disposition — that is the consumer's call.
    """
    root = Path(root)
    exclude_globs = exclude_globs or []
    if not root.exists():
        return []
    violations: list[dict] = []
    for yaml_file in sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")]):
        if "__pycache__" in str(yaml_file):
            continue
        try:
            rel = yaml_file.relative_to(root)
        except ValueError:
            rel = yaml_file
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        try:
            source = yaml_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, name, source_line in find_metric_declarations(source):
            if metric_module_ok(root, name):
                continue
            violations.append(
                {
                    "rule_id": RULE_METRIC_IMPLEMENTATION_MUST_EXIST,
                    "file": str(rel),
                    "line": lineno,
                    "col": 0,
                    "evidence": (
                        f"signal.metric {name!r} has no backing compute()/passes() module "
                        f"in .atdd/metrics/{name}.py or src/atdd/runners/metrics/{name}.py"
                    ),
                    "source_line": source_line,
                }
            )
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out

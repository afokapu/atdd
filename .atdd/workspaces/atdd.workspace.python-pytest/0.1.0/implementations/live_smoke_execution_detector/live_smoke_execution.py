"""python-pytest detector for tester.acceptance-violation.live-smoke-acceptance-must-execute.

REALIZES the agnostic CORE obligation
``tester.acceptance-violation.live-smoke-acceptance-must-execute`` (disposition
``strict``, severity 4) for the Python stack. The obligation node is authored in
CORE (``src/atdd/tester/conventions/nodes/
tester.acceptance-violation.live-smoke-acceptance-must-execute.convention.yaml``);
this module is the python-pytest DETECTOR that realizes it — NOT a new node.

An ``execution_kind: live_smoke`` acceptance's anchored test must run-or-fail
against real infrastructure. A ``pytest.skip()`` (or env-gated
``live_smoke_available()`` self-skip) raises nothing — so the acceptance passes
vacuously and a *skipped* live_smoke test is indistinguishable from a *passing*
one (#1076). The deterministic, static guard: a live_smoke acceptance's anchored
test must NOT be able to self-skip.

This detector inspects the consumer's TEST code: the ``ATDD_SCAN_ROOTS`` are TEST
directories.

PROVENANCE — ported from core
    src/atdd/tester/validators/test_live_smoke_execution.py
        :: detect_self_skip / _SELF_SKIP_PATTERNS / evaluate_live_smoke_execution
    The pure self-skip matcher is copied; the ``atdd.coach.*`` couplings and the
    plan/ walk were REMOVED (see HOW THE live_smoke GATE IS DECIDED below).

DECOUPLED FROM CORE (the 4 couplings, per task §3 / GOTCHAS):
  * ``bind_rule("tester.acceptance-violation.live-smoke-acceptance-must-execute")``
    ->  module-level ``RULE_LIVE_SMOKE_MUST_EXECUTE`` constant. Severity 4 /
    disposition strict live in the CORE convention node, not bound at import.
  * ``Violation``  ->  plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). Core reported file-level (``location=test_path``); this detector reports
    the line:col of the offending self-skip mechanism (finer than core).
  * ``find_repo_root`` + ``iter_repo_acceptances`` (the plan/ walk)  ->  REMOVED.
    Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` (§2); never
    auto-discovered. See below for how the live_smoke gate survives the drop.
  * ``assert_substrate_strict`` (the disposition gate)  ->  OMITTED. ``strict``
    (any self-skip -> FAIL) is the downstream consumer's disposition decision; the
    detector only EMITS the RAW list.

HOW THE live_smoke GATE IS DECIDED (the honest part — read this).
    Core needs TWO inputs to know which test source to scan for self-skip:
      (a) plan/ acceptances with ``execution_kind: live_smoke`` (the AUTHORITY
          that an acceptance is live_smoke — lives in plan YAML, NOT in the test),
      (b) the ``# Acceptance: acc:<urn>`` header join (``scan_test_acceptance_
          headers``) that maps each acceptance URN to its anchored test files.
    In the hermetic scan-mount model there is no plan/ to walk (walking it would
    BE the ``find_repo_root`` global discovery the v1.1 contract forbids, §2). So
    this detector keys the gate off a DECIDABLE in-file signal: a test is treated
    as live_smoke-anchored iff its leading header block carries
    ``# execution_kind: live_smoke`` (the in-file projection of the plan-side
    execution_kind). This makes the detector self-contained over test source AND
    false-positive-safe: a NON-live_smoke test that legitimately skips (a unit
    test with ``@pytest.mark.skipif``) is NOT flagged, because it carries no
    live_smoke header.

    The plan-side authority and the URN graph stay in CORE/the consumer: the
    consumer's plan-resolver is responsible for guaranteeing that every test
    anchored to an ``execution_kind: live_smoke`` acceptance carries this header
    (equivalently, it may pre-filter ATDD_SCAN_ROOTS to the live_smoke tests). The
    detector does only the decidable negative check — catch the self-skip — which
    is exactly core's pure ``evaluate_live_smoke_execution`` minus the plan walk.

Pure stdlib (``re``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# The CORE convention rule_id this detector realizes (NOT a new node).
RULE_LIVE_SMOKE_MUST_EXECUTE = (
    "tester.acceptance-violation.live-smoke-acceptance-must-execute"  # disposition: strict
)

# In-file gate: the hermetic projection of the plan-side execution_kind. A test is
# scanned for self-skip iff its leading header block declares this.
_LIVE_SMOKE_HEADER_RE = re.compile(
    r"^\s*#.*execution_kind\s*:\s*live_smoke\b", re.IGNORECASE
)
_HEADER_SCAN_LINES = 30  # only the leading comment block (core parity, avoids body strings)

# Self-skip mechanisms that let a live_smoke test "pass" by never executing.
# Copied verbatim (in spirit) from core ``_SELF_SKIP_PATTERNS``.
_SELF_SKIP_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bpytest\.skip\s*\("), "pytest.skip(...)"),
    (re.compile(r"\bpytest\.importorskip\s*\("), "pytest.importorskip(...)"),
    (re.compile(r"@\s*(?:pytest\.mark\.)?skipif\b"), "@pytest.mark.skipif"),
    (re.compile(r"@\s*(?:pytest\.mark\.)?skip\b"), "@pytest.mark.skip"),
    (re.compile(r"\bmark\.skipif?\s*\("), "pytest.mark.skip(if)(...)"),
    (re.compile(r"\blive_smoke_available\s*\("), "live_smoke_available() self-skip guard"),
]


def is_live_smoke_test(source: str) -> bool:
    """True iff the leading header block declares ``# execution_kind: live_smoke``."""
    head = source.split("\n", _HEADER_SCAN_LINES)[:_HEADER_SCAN_LINES]
    return any(_LIVE_SMOKE_HEADER_RE.search(line) for line in head)


def detect_self_skip(source: str) -> tuple[int, int, str] | None:
    """Return ``(lineno, col, label)`` for the first self-skip mechanism, else None.

    Mirrors core ``detect_self_skip`` (which returns only a label); this also
    pins the line:col of the first matching site for the v1.1 line-level channel.
    Scans the WHOLE source (a self-skip can appear in a decorator or body).

    KNOWN LIMITATION (core parity): the match is a regex over RAW source — it does
    not strip comments or docstrings. A docstring/comment that literally contains a
    self-skip token (e.g. the prose ``pytest.skip()``) can therefore match before
    the real call and skew the reported line:col. The finding is still a true
    positive (the file does contain a real self-skip), only its *located site* may
    point at the prose. Core never exposed this because it reported file-level
    locations only; the decidable negative check (does this file self-skip at all?)
    is unaffected.
    """
    best: tuple[int, int, str] | None = None
    for pattern, label in _SELF_SKIP_PATTERNS:
        for m in pattern.finditer(source):
            lineno = source.count("\n", 0, m.start()) + 1
            line_start = source.rfind("\n", 0, m.start()) + 1
            col = m.start() - line_start
            if best is None or (lineno, col) < (best[0], best[1]):
                best = (lineno, col, label)
    return best


# ---------------------------------------------------------------------------
# Scan-root walk (scope supplied via ATDD_SCAN_ROOTS — never auto-discovered)
# ---------------------------------------------------------------------------


def is_test_file(path: Path) -> bool:
    """True for ``test_*.py`` / ``*_test.py`` files."""
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py")


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _line_text(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one TEST ``root`` and return RAW v1.1 violation dicts.

    A violation is emitted for each ``execution_kind: live_smoke``-headed test
    file that can self-skip. ``file`` is relative to ``root``; ``source_line`` is
    the RAW offending line. The strict verdict (any self-skip -> FAIL) is the
    consumer's decision.
    """
    root = Path(root)
    exclude_globs = exclude_globs or []
    if not root.exists():
        return []
    violations: list[dict] = []
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        if not is_test_file(py_file):
            continue
        try:
            rel = py_file.relative_to(root)
        except ValueError:
            rel = py_file
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not is_live_smoke_test(source):
            continue  # not a live_smoke-anchored test — out of scope
        hit = detect_self_skip(source)
        if hit is None:
            continue  # cannot self-skip — runs-or-fails, compliant
        lineno, col, label = hit
        lines = source.splitlines()
        violations.append(
            {
                "rule_id": RULE_LIVE_SMOKE_MUST_EXECUTE,
                "file": str(rel),
                "line": lineno,
                "col": col,
                "evidence": (
                    f"live_smoke-anchored test can self-skip ({label}). A skipped "
                    f"live_smoke test passes vacuously — it never executes against "
                    f"real infrastructure. Remove the self-skip so it runs-or-fails "
                    f"(it must run inside the workspace provider)."
                ),
                "source_line": _line_text(lines, lineno),
            }
        )
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out

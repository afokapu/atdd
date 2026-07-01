"""python-pytest detector for tester.filename.urn.

REALIZES the stack-bound EXTENSION obligation ``tester.filename.urn`` (disposition
``documentation-only``, severity 2) for the Python stack. The obligation node is
authored in the tester EXTENSION (``official/atdd.extension.tester/conventions/
tester.filename.urn.convention.yaml``); this module is the python-pytest DETECTOR
that realizes it — it is NOT a new node and it does not re-author the obligation.

A test file's IDENTITY comes from its ``# URN: test:...`` header (a CORE
invariant). The per-stack FILENAME is the rendering of that URN. For python/pytest
the rendering carries the ``test_`` prefix (or ``_test.py`` suffix) so pytest's
default collection finds it. A file that is plainly a test — it carries a
``# URN: test:`` header OR defines a top-level ``def test_*`` — but is NOT named
collectably is a SILENT GREEN GAP: pytest never collects it, so it passes CI by
never running.

This detector inspects the consumer's TEST code: the ``ATDD_SCAN_ROOTS`` are TEST
directories. Every ``*.py`` is examined; only files that look like an intended
test are eligible to be flagged.

PROVENANCE — derived from core
    src/atdd/tester/conventions/filename.convention.yaml
        :: languages.python (pattern ``test_{...}.py``, prefix ``test_``)
           + rules[tester.filename.urn]
    The python naming rendering is copied in spirit; no ``atdd.coach.*`` substrate
    couplings are imported.

DECOUPLED FROM CORE (the 4 couplings, per task GOTCHAS):
  * ``bind_rule("tester.filename.urn")``  ->  module-level ``RULE_FILENAME_URN``
    constant. Severity 2 / disposition documentation-only live in the EXTENSION
    convention node, not bound at import.
  * ``Violation``  ->  plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). ``source_line`` carries the RAW offending line (the URN header or the
    first ``def test_``) so a downstream consumer can act without re-reading files.
  * ``find_repo_root`` + ``rglob`` repo scan  ->  REMOVED. Scan scope is supplied
    explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES``; never
    auto-discovered.
  * ``assert_disposition_satisfied`` (the disposition gate)  ->  OMITTED. The
    detector emits RAW violations; documentation-only is advisory and whether the
    signal blocks is the downstream consumer's decision, never the detector's.

Pure stdlib (``re``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# The EXTENSION convention rule_id this detector realizes (NOT a new node).
RULE_FILENAME_URN = "tester.filename.urn"  # disposition: documentation-only

# A test file carries its identity in a `# URN: test:` header (V3, core parity).
# Anchored to the start of the line (leading whitespace allowed) so the marker is
# a real comment header, NOT prose/docstring text that merely mentions "# URN:".
_URN_TEST_HEADER = re.compile(r"^\s*#\s*URN:\s*test:", re.IGNORECASE)
# ... or it plainly defines a top-level pytest test function.
_TOP_LEVEL_TEST_DEF = re.compile(r"^(async\s+def|def)\s+test_\w*\s*\(", re.MULTILINE)


# ---------------------------------------------------------------------------
# Detection (pure — unit-tested directly against source strings)
# ---------------------------------------------------------------------------


def is_pytest_collectable(name: str) -> bool:
    """True if ``name`` is collected by pytest's default discovery."""
    return name.startswith("test_") or name.endswith("_test.py")


def looks_like_test(source: str) -> tuple[bool, int, str]:
    """Decide whether ``source`` is an intended test, with the deciding evidence.

    Returns ``(is_test, lineno, source_line)``. A file is an intended test if it
    carries a ``# URN: test:`` identity header OR defines a top-level ``def
    test_*`` function. ``lineno`` / ``source_line`` point at whichever marker
    decided it (header preferred), so a mis-named file can be reported at a real
    line. ``(False, 0, "")`` when the file is not a test.
    """
    lines = source.splitlines()
    for i, line in enumerate(lines, start=1):
        if _URN_TEST_HEADER.search(line):
            return True, i, line
    m = _TOP_LEVEL_TEST_DEF.search(source)
    if m:
        lineno = source.count("\n", 0, m.start()) + 1
        return True, lineno, lines[lineno - 1] if 1 <= lineno <= len(lines) else ""
    return False, 0, ""


# ---------------------------------------------------------------------------
# Scan-root walk (scope supplied via ATDD_SCAN_ROOTS — never auto-discovered)
# ---------------------------------------------------------------------------


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one TEST ``root`` and return RAW v1.1 violation dicts.

    A violation is raised for each ``*.py`` that is an intended test (URN header or
    top-level ``def test_*``) yet is NOT named collectably by pytest. Each is
    ``{rule_id, file, line, col, evidence, source_line}``; ``file`` is relative to
    ``root``. The detector NEVER applies disposition — documentation-only is the
    consumer's call.
    """
    root = Path(root)
    exclude_globs = exclude_globs or []
    if not root.exists():
        return []
    violations: list[dict] = []
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        if py_file.name == "conftest.py":
            continue
        try:
            rel = py_file.relative_to(root)
        except ValueError:
            rel = py_file
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        if is_pytest_collectable(py_file.name):
            continue  # already collectable — nothing to flag
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        is_test, lineno, source_line = looks_like_test(source)
        if not is_test:
            continue
        violations.append(
            {
                "rule_id": RULE_FILENAME_URN,
                "file": str(rel),
                "line": lineno,
                "col": 0,
                "evidence": (
                    f"intended test file {py_file.name!r} is not pytest-collectable "
                    f"(name must start with 'test_' or end with '_test.py'); pytest "
                    f"silently skips it"
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

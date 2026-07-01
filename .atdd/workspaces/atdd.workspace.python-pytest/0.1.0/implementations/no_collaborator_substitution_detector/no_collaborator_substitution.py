"""python-pytest detector for tester.smoke.no-collaborator-substitution.

REALIZES the agnostic CORE obligation
``tester.smoke.no-collaborator-substitution`` (disposition
``suppress-and-clean``, severity 4) for the Python stack. The obligation node is
authored in CORE (``src/atdd/tester/conventions/nodes/
tester.smoke.no-collaborator-substitution.convention.yaml``); this module is the
python-pytest DETECTOR that realizes it — it is NOT a new node and it does not
re-author the obligation.

A SMOKE-phase test (a ``test_*.py`` carrying ``# Phase: SMOKE``) must exercise
the real subject. A test that substitutes one of the subject's collaborators —
by ``monkeypatch.setattr`` or by assigning a locally-defined function/lambda over
an object attribute — is a unit test wearing a SMOKE label: it passes CI while
exercising nothing real.

This detector inspects the consumer's TEST code (not product code): the
``ATDD_SCAN_ROOTS`` are TEST directories. Only ``test_*.py`` / ``*_test.py``
files that carry ``# Phase: SMOKE`` are scanned.

PROVENANCE — ported from core
    src/atdd/tester/validators/test_smoke_no_collaborator_substitution.py
        :: detect_substitutions / _iter_smoke_test_files / collect_violations
    The two decidable AST patterns are copied in spirit; the ``atdd.coach.*``
    substrate couplings were REMOVED.

DECOUPLED FROM CORE (the 4 couplings, per task §3 / GOTCHAS):
  * ``bind_rule("tester.smoke.no-collaborator-substitution")``  ->  module-level
    ``RULE_NO_COLLABORATOR_SUBSTITUTION`` constant. Severity 4 / disposition
    suppress-and-clean live in the CORE convention node, not bound at import.
  * ``Violation``  ->  plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). ``source_line`` carries the RAW offending line so the downstream
    consumer can apply suppress-and-clean disposition without re-reading files.
  * ``find_repo_root`` + ``rglob`` repo scan  ->  REMOVED. Scan scope is supplied
    explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2); never
    auto-discovered.
  * ``assert_disposition_satisfied`` (the disposition gate)  ->  OMITTED. The
    detector emits RAW violations INCLUDING handlers/sites that carry a
    ``# atdd:suppress(...)`` marker; whether a marker absorbs a violation is the
    downstream consumer's suppress-and-clean disposition decision (§1), never the
    detector's.

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

# The CORE convention rule_id this detector realizes (NOT a new node).
RULE_NO_COLLABORATOR_SUBSTITUTION = (
    "tester.smoke.no-collaborator-substitution"  # disposition: suppress-and-clean
)

# The header marker that gates a file as a SMOKE-phase test (core parity).
PHASE_SMOKE_MARKER = "# Phase: SMOKE"

# monkeypatch methods that set up the *environment* (legitimate smoke setup)
# rather than substituting a collaborator — NOT flagged (core parity).
_MONKEYPATCH_ENV_METHODS = frozenset({"setenv", "delenv", "chdir", "syspath_prepend"})


# ---------------------------------------------------------------------------
# Detection (pure — unit-tested directly against source strings)
# ---------------------------------------------------------------------------


def detect_substitutions(source: str) -> list[tuple[int, int, str]]:
    """Return ``(lineno, col, evidence)`` for each collaborator-substitution site.

    Pure function over a Python source string. A syntax error yields a single
    synthetic finding so an unparseable smoke test is surfaced, not silently
    skipped (core parity). Two decidable AST patterns:

      1. ``monkeypatch.setattr(...)`` — collaborator stubbing. ``monkeypatch``
         environment methods (setenv / delenv / chdir / syspath_prepend) are
         legitimate smoke setup and are NOT flagged.
      2. ``obj.attr = <local def/lambda>`` — a locally-defined function or lambda
         assigned over an object attribute. Data assignments are not flagged; the
         RHS must resolve to a function/lambda defined in the same test module.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        lineno = getattr(exc, "lineno", 1) or 1
        col = getattr(exc, "offset", 0) or 0
        return [(lineno, max(col - 1, 0), f"unparseable smoke test file: {exc}")]

    # Names bound to a locally-defined function or lambda in this module.
    local_callables: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local_callables.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Lambda):
                    local_callables.add(tgt.id)

    findings: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        # Pattern 1: monkeypatch.<method>(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            fn = node.func
            if isinstance(fn.value, ast.Name) and fn.value.id == "monkeypatch":
                if fn.attr == "setattr":
                    findings.append(
                        (
                            node.lineno,
                            node.col_offset,
                            "monkeypatch.setattr(...) substitutes a collaborator",
                        )
                    )
                # other monkeypatch.* (env methods) are intentionally ignored

        # Pattern 2: obj.attr = <local def/lambda>
        if isinstance(node, ast.Assign):
            value = node.value
            rhs_is_local_fn = isinstance(value, ast.Lambda) or (
                isinstance(value, ast.Name) and value.id in local_callables
            )
            if rhs_is_local_fn:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute):
                        try:
                            target_repr = ast.unparse(tgt)
                        except Exception:  # pragma: no cover - defensive
                            target_repr = f"<attr>.{tgt.attr}"
                        rhs = "<lambda>" if isinstance(value, ast.Lambda) else value.id
                        findings.append(
                            (
                                node.lineno,
                                node.col_offset,
                                f"{target_repr} = {rhs} substitutes a collaborator "
                                f"(local function/lambda assigned over an attribute)",
                            )
                        )

    findings.sort(key=lambda f: (f[0], f[1]))
    return findings


# ---------------------------------------------------------------------------
# Scan-root walk (scope supplied via ATDD_SCAN_ROOTS — never auto-discovered)
# ---------------------------------------------------------------------------


def is_smoke_test_file(path: Path, text: str) -> bool:
    """True for a ``test_*.py`` / ``*_test.py`` file carrying ``# Phase: SMOKE``."""
    name = path.name
    if not (name.startswith("test_") or name.endswith("_test.py")):
        return False
    return PHASE_SMOKE_MARKER in text


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _line_text(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one TEST ``root`` and return RAW v1.1 violation dicts.

    Each violation is ``{rule_id, file, line, col, evidence, source_line}``;
    ``file`` is relative to ``root`` and ``source_line`` is the RAW offending
    line. The detector NEVER inspects ``source_line`` for suppress markers — that
    is the consumer's suppress-and-clean disposition decision.
    """
    root = Path(root)
    exclude_globs = exclude_globs or []
    if not root.exists():
        return []
    violations: list[dict] = []
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file):
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
        if not is_smoke_test_file(py_file, source):
            continue
        lines = source.splitlines()
        for lineno, col, evidence in detect_substitutions(source):
            violations.append(
                {
                    "rule_id": RULE_NO_COLLABORATOR_SUBSTITUTION,
                    "file": str(rel),
                    "line": lineno,
                    "col": col,
                    "evidence": evidence,
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

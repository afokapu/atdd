# URN: component:integration-hardening:meta-validator:_no_polluting_patterns:backend:domain
# Runtime: python
# Purpose: AST-walking scanner for test-pollution patterns (D002 meta-validator).

"""AST-based scanner for test-pollution patterns (Wave 12 contamination class).

Detects patterns that mutate shared git state outside tmp_path scope:

RED flags (PollutionViolation emitted):
  bare-init-bad-cwd:
    subprocess.run(['git','init','--bare',...], cwd=os.getcwd())
    subprocess.run(['git','init','--bare',...], cwd=Path.cwd())
    Any bare-init call with an explicitly bad (non-tmp_path) cwd= arg.

  core-bare-unscoped:
    subprocess.run(['git','config','core.bare','true'])  # no -C, no cwd=
    subprocess.run(['git','config','core.bare','true'], cwd=os.getcwd())  # bad cwd

PASS (no violation):
  subprocess.run(['git','-C',str(tmp_path),'config','core.bare','true'])
  subprocess.run(['git','config','core.bare','true'], cwd=str(tmp_path))
  subprocess.run(['git','config','--worktree','core.bare','true'])
  subprocess.run(['git','init','--bare',str(tmp_path)])  # no bad cwd=

Reference: Wave 12 contamination incident 2026-05-12 (PRs #625/#627).
WMBT: wmbt:integration-hardening:D002
Convention: tester.test-isolation.no-polluting-patterns
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass
class PollutionViolation:
    """A detected static pollution pattern in a test file."""
    pattern: str
    detail: str
    lineno: int
    file: str = field(default="<string>")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TMP_PATH_NAMES = frozenset({
    "tmp_path", "tmpdir", "tmp_dir", "temp_dir", "temp_repo",
    "tmppath", "tmp_path_factory",
})

_SUBPROCESS_ATTRS = frozenset({"run", "call", "check_call", "check_output"})

_OBVIOUSLY_BAD_CWD_ATTRS = frozenset({"getcwd", "cwd"})


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _is_subprocess_run(call: ast.Call) -> bool:
    """Return True if call is subprocess.run / subprocess.call / etc."""
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr in _SUBPROCESS_ATTRS:
            if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                return True
    if isinstance(func, ast.Name) and func.id in _SUBPROCESS_ATTRS:
        return True
    return False


def _extract_str_constants(node: ast.expr) -> Optional[List[str]]:
    """Extract the string constant elements from an ast.List.

    Returns a list of the string values that appear as constants. Non-constant
    elements (variable refs, function calls) are skipped — the caller works
    with the partial list.  Returns None if node is not an ast.List at all.
    """
    if not isinstance(node, ast.List):
        return None
    result = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            result.append(elt.value)
    return result


def _has_C_flag(args_list: ast.List) -> bool:
    """Return True if the git command list contains a '-C' flag constant."""
    for elt in args_list.elts:
        if isinstance(elt, ast.Constant) and elt.value == "-C":
            return True
    return False


def _is_tmp_path_scoped(node: ast.expr) -> bool:
    """Return True if the AST expression clearly references a tmp_path fixture.

    Handles: tmp_path, str(tmp_path), str(tmp_path / 'sub'), tmp_path.name, etc.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in _TMP_PATH_NAMES:
            return True
    return False


def _is_obviously_bad_cwd(node: ast.expr) -> bool:
    """Return True if cwd value is obviously NOT tmp_path-scoped.

    Detects: os.getcwd(), Path.cwd(), Path().cwd(), ".".
    Does NOT flag ambiguous variable references — only known-bad patterns.
    """
    # os.getcwd() or Path.cwd() — attribute call with bad attr name
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _OBVIOUSLY_BAD_CWD_ATTRS:
            return True
    # String literal "." or ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if node.value in (".", ""):
            return True
    return False


def _get_cwd_kwarg(call: ast.Call) -> Optional[ast.expr]:
    """Return the value of the cwd= keyword argument, or None if absent."""
    for kw in call.keywords:
        if kw.arg == "cwd":
            return kw.value
    return None


# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------

def _check_bare_init(call: ast.Call, args_list: ast.List) -> Optional[PollutionViolation]:
    """Detect: subprocess.run(['git','init','--bare',...], cwd=<bad-cwd>).

    Only flags when cwd= is explicitly present and obviously bad.
    Missing cwd= is NOT flagged (the git init path arg determines the repo
    location in that case, not the process cwd).
    """
    str_args = _extract_str_constants(args_list)
    if str_args is None:
        return None
    if "git" not in str_args or "init" not in str_args or "--bare" not in str_args:
        return None

    cwd_val = _get_cwd_kwarg(call)
    if cwd_val is None:
        return None

    if _is_tmp_path_scoped(cwd_val):
        return None

    if _is_obviously_bad_cwd(cwd_val):
        return PollutionViolation(
            pattern="bare-init-bad-cwd",
            detail=(
                "subprocess.run(['git','init','--bare',...], cwd=<non-tmp_path>) — "
                "bare repo init scoped to the process's working directory mutates "
                "shared git state. Use cwd=tmp_path or pass str(tmp_path) as the "
                "init path argument."
            ),
            lineno=call.lineno,
        )
    return None


def _check_core_bare_config(call: ast.Call, args_list: ast.List) -> Optional[PollutionViolation]:
    """Detect unscoped or badly-scoped git config core.bare true calls.

    PASS conditions (no violation):
      - '--worktree' in the command args (worktree-scoped, per #634 convention)
      - '-C' flag present (scoped via -C; we trust the caller knows its dir)
      - cwd= is a tmp_path reference

    FLAG conditions (violation):
      - No '-C', no 'cwd=', AND command contains 'core.bare' + 'true' (fully unscoped)
      - cwd= is explicitly bad (os.getcwd(), Path.cwd(), ".")
    """
    str_args = _extract_str_constants(args_list)
    if str_args is None:
        return None
    if "git" not in str_args or "config" not in str_args:
        return None
    if "core.bare" not in str_args or "true" not in str_args:
        return None

    # --worktree flag is always safe (worktree-scoped per #634 convention)
    if "--worktree" in str_args:
        return None

    # -C flag is present — scoped to a directory; trust the caller
    if _has_C_flag(args_list):
        return None

    cwd_val = _get_cwd_kwarg(call)

    # cwd= is a tmp_path reference — safe
    if cwd_val is not None and _is_tmp_path_scoped(cwd_val):
        return None

    # cwd= is obviously bad — flag
    if cwd_val is not None and _is_obviously_bad_cwd(cwd_val):
        return PollutionViolation(
            pattern="core-bare-unscoped",
            detail=(
                "subprocess.run(['git','config','core.bare','true'], cwd=<non-tmp_path>) — "
                "core.bare mutation scoped to the process's working directory contaminates "
                "the shared .git/config. Use -C str(tmp_path) or cwd=str(tmp_path)."
            ),
            lineno=call.lineno,
        )

    # No cwd= at all, no -C — fully unscoped mutation
    if cwd_val is None:
        return PollutionViolation(
            pattern="core-bare-unscoped",
            detail=(
                "subprocess.run(['git','config','core.bare','true']) — no -C flag and "
                "no cwd= argument: core.bare mutation is fully unscoped and will "
                "contaminate whatever repo the test process is running in. "
                "Use -C str(tmp_path) or cwd=str(tmp_path)."
            ),
            lineno=call.lineno,
        )

    # cwd= is some other expression (variable, complex expression) — ambiguous, skip
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_text(code: str, filename: str = "<string>") -> List[PollutionViolation]:
    """Scan a Python source string for test-pollution patterns.

    Args:
        code: Python source code text to scan.
        filename: Optional label for the file (used in PollutionViolation.file).

    Returns:
        List of PollutionViolation objects; empty when code is clean or
        cannot be parsed.
    """
    try:
        tree = ast.parse(code, filename=filename)
    except SyntaxError as exc:
        print(f"meta-validator: parse error in {filename}: {exc}", file=sys.stderr)
        return []

    violations: List[PollutionViolation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_subprocess_run(node):
            continue
        if not node.args:
            continue

        args_node = node.args[0]
        if not isinstance(args_node, ast.List):
            continue

        # Check for bare-init pattern
        v = _check_bare_init(node, args_node)
        if v is not None:
            v.file = filename
            violations.append(v)
            continue

        # Check for core.bare config pattern
        v = _check_core_bare_config(node, args_node)
        if v is not None:
            v.file = filename
            violations.append(v)

    return violations


def scan_repo(root: Path) -> List[PollutionViolation]:
    """Scan all test_*.py files under *root* for test-pollution patterns.

    Args:
        root: Directory to scan recursively (typically the atdd package dir).

    Returns:
        List of PollutionViolation objects across all scanned files; empty
        when the repo is clean.
    """
    violations: List[PollutionViolation] = []

    for test_file in sorted(root.rglob("test_*.py")):
        if "__pycache__" in str(test_file):
            continue
        try:
            code = test_file.read_text(encoding="utf-8")
        except OSError:
            continue

        rel = str(test_file.relative_to(root.parent))
        file_violations = scan_text(code, filename=rel)
        violations.extend(file_violations)

    return violations

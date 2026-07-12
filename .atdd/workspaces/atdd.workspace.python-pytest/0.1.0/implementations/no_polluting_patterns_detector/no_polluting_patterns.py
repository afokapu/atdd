"""python-pytest detector for tester.test-isolation.no-polluting-patterns.

REALIZES the agnostic CORE obligation
``tester.test-isolation.no-polluting-patterns`` (disposition ``strict``,
severity 4) for the Python stack. The obligation node is authored in CORE
(``src/atdd/tester/conventions/nodes/
tester.test-isolation.no-polluting-patterns.convention.yaml``); this module is the
python-pytest DETECTOR that realizes it — NOT a new node.

Test files must not contain AST-detectable patterns that mutate shared git state
outside ``tmp_path`` scope — the contamination class behind Wave 12 (2026-05-12,
PRs #625/#627). This detector inspects the consumer's TEST code: the
``ATDD_SCAN_ROOTS`` are TEST directories and only ``test_*.py`` / ``*_test.py``
files are scanned.

RED flags (one raw violation each):
  bare-init-bad-cwd:
    subprocess.run(['git','init','--bare',...], cwd=os.getcwd())
    subprocess.run(['git','init','--bare',...], cwd=Path.cwd())
  core-bare-unscoped:
    subprocess.run(['git','config','core.bare','true'])              # no -C, no cwd=
    subprocess.run(['git','config','core.bare','true'], cwd=os.getcwd())

PASS (properly isolated — no violation):
    subprocess.run(['git','-C',str(tmp_path),'config','core.bare','true'])
    subprocess.run(['git','config','core.bare','true'], cwd=str(tmp_path))
    subprocess.run(['git','config','--worktree','core.bare','true'])
    subprocess.run(['git','init','--bare',str(tmp_path)])            # no bad cwd=

PROVENANCE — ported from core
    src/atdd/tester/validators/_no_polluting_patterns.py
        :: scan_text / _is_subprocess_run / _check_bare_init /
           _check_core_bare_config / _extract_str_constants / _has_C_flag /
           _is_tmp_path_scoped / _is_obviously_bad_cwd / _get_cwd_kwarg
    The AST pattern detectors are copied in spirit; the ``atdd.coach.*`` couplings
    were REMOVED.

DECOUPLED FROM CORE (the 4 couplings, per task §3 / GOTCHAS):
  * ``bind_rule("tester.test-isolation.no-polluting-patterns")``  ->  module-level
    ``RULE_NO_POLLUTING_PATTERNS`` constant. Severity 4 / disposition strict live
    in the CORE convention node, not bound at import.
  * core ``PollutionViolation`` dataclass  ->  plain dicts in the v1.1
    violation-output shape ``{rule_id, file, line, col, evidence, source_line}``
    (PROVIDER-CONTRACT-v1.1 §3.2). The core ``pattern`` label is folded into
    ``evidence``; ``source_line`` carries the RAW offending line.
  * ``find_repo_root`` + ``scan_repo(ATDD_PKG_DIR)``  ->  REMOVED. Scan scope is
    supplied explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2).
  * ``assert_disposition_satisfied`` / ``pytest.fail`` gate  ->  OMITTED. ``strict``
    (any pollution pattern -> FAIL) is the downstream consumer's disposition
    decision; the detector only EMITS the RAW list.

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

# The CORE convention rule_id this detector realizes (NOT a new node).
RULE_NO_POLLUTING_PATTERNS = (
    "tester.test-isolation.no-polluting-patterns"  # disposition: strict
)

_TMP_PATH_NAMES = frozenset(
    {
        "tmp_path",
        "tmpdir",
        "tmp_dir",
        "temp_dir",
        "temp_repo",
        "tmppath",
        "tmp_path_factory",
    }
)
_SUBPROCESS_ATTRS = frozenset({"run", "call", "check_call", "check_output"})
_OBVIOUSLY_BAD_CWD_ATTRS = frozenset({"getcwd", "cwd"})


# ---------------------------------------------------------------------------
# AST helpers (pure — ported from core _no_polluting_patterns)
# ---------------------------------------------------------------------------


def _is_subprocess_run(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr in _SUBPROCESS_ATTRS:
            if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                return True
    if isinstance(func, ast.Name) and func.id in _SUBPROCESS_ATTRS:
        return True
    return False


def _extract_str_constants(node: ast.expr) -> list[str] | None:
    if not isinstance(node, ast.List):
        return None
    result = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            result.append(elt.value)
    return result


def _has_C_flag(args_list: ast.List) -> bool:
    for elt in args_list.elts:
        if isinstance(elt, ast.Constant) and elt.value == "-C":
            return True
    return False


def _is_tmp_path_scoped(node: ast.expr) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in _TMP_PATH_NAMES:
            return True
    return False


def _is_obviously_bad_cwd(node: ast.expr) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _OBVIOUSLY_BAD_CWD_ATTRS:
            return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if node.value in (".", ""):
            return True
    return False


def _get_cwd_kwarg(call: ast.Call) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == "cwd":
            return kw.value
    return None


# ---------------------------------------------------------------------------
# Pattern detectors — return (pattern, evidence) or None
# ---------------------------------------------------------------------------


def _check_bare_init(call: ast.Call, args_list: ast.List) -> tuple[str, str] | None:
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
        return (
            "bare-init-bad-cwd",
            "subprocess.run(['git','init','--bare',...], cwd=<non-tmp_path>) — "
            "bare repo init scoped to the process's working directory mutates "
            "shared git state. Use cwd=tmp_path or pass str(tmp_path) as the init "
            "path argument.",
        )
    return None


def _check_core_bare_config(call: ast.Call, args_list: ast.List) -> tuple[str, str] | None:
    str_args = _extract_str_constants(args_list)
    if str_args is None:
        return None
    if "git" not in str_args or "config" not in str_args:
        return None
    if "core.bare" not in str_args or "true" not in str_args:
        return None
    if "--worktree" in str_args:
        return None
    if _has_C_flag(args_list):
        return None
    cwd_val = _get_cwd_kwarg(call)
    if cwd_val is not None and _is_tmp_path_scoped(cwd_val):
        return None
    if cwd_val is not None and _is_obviously_bad_cwd(cwd_val):
        return (
            "core-bare-unscoped",
            "subprocess.run(['git','config','core.bare','true'], cwd=<non-tmp_path>) — "
            "core.bare mutation scoped to the process's working directory "
            "contaminates the shared .git/config. Use -C str(tmp_path) or "
            "cwd=str(tmp_path).",
        )
    if cwd_val is None:
        return (
            "core-bare-unscoped",
            "subprocess.run(['git','config','core.bare','true']) — no -C flag and "
            "no cwd= argument: core.bare mutation is fully unscoped and will "
            "contaminate whatever repo the test process runs in. Use -C "
            "str(tmp_path) or cwd=str(tmp_path).",
        )
    return None


def detect_pollution(source: str) -> list[tuple[int, int, str, str]]:
    """Return ``(lineno, col, pattern, evidence)`` for each pollution site (pure).

    A syntax error yields ``[]`` — an unparseable file is not a pollution finding
    (core parity: ``scan_text`` returns ``[]`` on ``SyntaxError``).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    findings: list[tuple[int, int, str, str]] = []
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

        hit = _check_bare_init(node, args_node)
        if hit is not None:
            findings.append((node.lineno, node.col_offset, hit[0], hit[1]))
            continue
        hit = _check_core_bare_config(node, args_node)
        if hit is not None:
            findings.append((node.lineno, node.col_offset, hit[0], hit[1]))

    findings.sort(key=lambda f: (f[0], f[1]))
    return findings


# ---------------------------------------------------------------------------
# Scan-root walk (scope supplied via ATDD_SCAN_ROOTS — never auto-discovered)
# ---------------------------------------------------------------------------


def is_test_file(path: Path) -> bool:
    """True for ``test_*.py`` / ``*_test.py`` (core's ``scan_repo`` scans these)."""
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

    Each violation is ``{rule_id, file, line, col, evidence, source_line}``;
    ``file`` is relative to ``root`` and ``source_line`` is the RAW offending line.
    The strict verdict (any pollution -> FAIL) is the consumer's decision.
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
        lines = source.splitlines()
        for lineno, col, pattern, evidence in detect_pollution(source):
            violations.append(
                {
                    "rule_id": RULE_NO_POLLUTING_PATTERNS,
                    "file": str(rel),
                    "line": lineno,
                    "col": col,
                    "evidence": f"[{pattern}] {evidence}",
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

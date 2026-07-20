# URN: component:govern-lifecycle:enforcement-substrate:doctor:backend:domain
# Runtime: python
# Purpose: `atdd doctor` — diagnose the source-repo / foreign-install mismatch that
#          silently makes the pre-push validator gate test stale code (#928 Gap 4).
"""
``atdd doctor`` — environment self-diagnosis.

The mismatch this catches (issue #928 Gap 4): you are standing in the atdd
source checkout, but the ``atdd`` Python package being imported comes from a
*foreign* install (typically a pipx-managed wheel). In that state
``atdd validate`` discovers its validators from the installed wheel
(``Path(atdd.__file__)``), so the pre-push gate tests the last *released*
toolkit against your working tree — not your edits. New validators look
like orphans, unrelated stale failures block the push, and the version
gate's bare ``python3`` (often a different interpreter still) can't import
atdd at all and prints the misleading "requires a newer atdd package".

This module turns that silent, reverse-engineer-it-yourself failure into a
single command that names the fault and the fix.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class EnvDiagnosis:
    """Structured result of an environment diagnosis.

    Attributes:
        interpreter: The interpreter running this diagnosis (``sys.executable``).
        can_import_atdd: Whether ``import atdd`` resolves to a real package
            (a namespace stub with ``__file__ is None`` counts as False).
        atdd_import_path: Directory ``atdd`` was imported from, or None.
        repo_root: Detected repo root, or None.
        repo_is_atdd_checkout: True when ``repo_root`` is an atdd *source*
            checkout (its pyproject declares ``name = "atdd"``), regardless of
            where ``atdd`` is imported from.
        imported_from_tree: True when the imported ``atdd`` lives under
            ``repo_root`` (i.e. an editable / source install of this tree).
        source_repo_mismatch: True when this is the atdd checkout but the
            imported ``atdd`` is foreign — the dogfooding bug.
        hook_python_can_import_atdd: Whether the bare ``python3`` the git
            hooks invoke can import atdd. False reproduces the version-gate
            misfire.
        healthy: Overall verdict.
    """

    interpreter: str
    can_import_atdd: bool
    atdd_import_path: Optional[str]
    repo_root: Optional[str]
    repo_is_atdd_checkout: bool
    imported_from_tree: bool
    source_repo_mismatch: bool
    hook_python_can_import_atdd: bool
    healthy: bool


def evaluate_diagnosis(
    *,
    interpreter: str,
    can_import_atdd: bool,
    atdd_import_path: Optional[str],
    repo_root: Optional[str],
    repo_is_atdd_checkout: bool,
    hook_python_can_import_atdd: bool,
) -> EnvDiagnosis:
    """Pure evaluator — derive the verdict booleans from raw inputs.

    Kept side-effect free so the logic is unit-testable without manipulating
    interpreters, import paths, or the filesystem.
    """
    imported_from_tree = False
    if can_import_atdd and atdd_import_path and repo_root:
        try:
            Path(atdd_import_path).resolve().relative_to(Path(repo_root).resolve())
            imported_from_tree = True
        except ValueError:
            imported_from_tree = False

    source_repo_mismatch = bool(
        repo_is_atdd_checkout and can_import_atdd and not imported_from_tree
    )

    healthy = (
        can_import_atdd
        and hook_python_can_import_atdd
        and not source_repo_mismatch
    )

    return EnvDiagnosis(
        interpreter=interpreter,
        can_import_atdd=can_import_atdd,
        atdd_import_path=atdd_import_path,
        repo_root=repo_root,
        repo_is_atdd_checkout=repo_is_atdd_checkout,
        imported_from_tree=imported_from_tree,
        source_repo_mismatch=source_repo_mismatch,
        hook_python_can_import_atdd=hook_python_can_import_atdd,
        healthy=healthy,
    )


def _repo_is_atdd_checkout(repo_root: Optional[Path]) -> bool:
    """True when repo_root's pyproject declares ``name = "atdd"``.

    Independent of where ``atdd`` is imported from — this asks "is the repo I
    am standing in the atdd toolkit source?", not "is atdd installed editable?".
    """
    if repo_root is None:
        return False
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        return 'name = "atdd"' in pyproject.read_text(encoding="utf-8")
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return False


#: Every symbol a git hook dispatches to via ``python3 -c``. Each one must be
#: importable by the bare ``python3`` the hooks invoke, or that gate is inert.
#: Probing only one of them would leave the others failing silently.
_HOOK_DISPATCH_IMPORTS = (
    "from atdd.version_check import _gate_main",
    "from atdd.coach.store_mirror_gate import _gate_main",
)


def _hook_python_can_import_atdd() -> bool:
    """Probe the bare ``python3`` the git hooks invoke for an atdd import.

    The hooks dispatch via ``python3 -c "from atdd.<module> import _gate_main"``.
    A namespace-only ``atdd`` (``__file__ is None``) fails the submodule import,
    so probe the actual symbols the hooks use, not bare ``import atdd`` — and
    probe *all* of them, since a hook whose module cannot be imported is a gate
    that silently never runs.
    """
    python3 = shutil.which("python3")
    if not python3:
        return False
    for statement in _HOOK_DISPATCH_IMPORTS:
        try:
            result = subprocess.run(
                [python3, "-c", statement],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
            return False
        if result.returncode != 0:
            return False
    return True


def diagnose_environment(repo_root: Optional[Path] = None) -> EnvDiagnosis:
    """Gather real environment facts and evaluate them into an EnvDiagnosis."""
    interpreter = sys.executable or "python"

    can_import = False
    import_path: Optional[str] = None
    try:
        import atdd  # local import; this module may be imported very early

        pkg_file = getattr(atdd, "__file__", None)
        if pkg_file:
            import_path = str(Path(pkg_file).resolve().parent)
            can_import = True
    except (ImportError, AttributeError, TypeError):
        can_import = False

    root: Optional[Path] = repo_root
    if root is None:
        try:
            from atdd.coach.utils.repo import find_repo_root

            root = find_repo_root().resolve()
        except Exception:
            root = None

    return evaluate_diagnosis(
        interpreter=interpreter,
        can_import_atdd=can_import,
        atdd_import_path=import_path,
        repo_root=str(root) if root else None,
        repo_is_atdd_checkout=_repo_is_atdd_checkout(root),
        hook_python_can_import_atdd=_hook_python_can_import_atdd(),
    )


def format_report(d: EnvDiagnosis) -> str:
    """Render a human-readable diagnosis with per-check status and remedies."""
    ok = "ok"
    warn = "WARN"
    fail = "FAIL"

    lines = ["atdd doctor — environment diagnosis", ""]
    lines.append(f"  interpreter            : {d.interpreter}")
    lines.append(f"  atdd imported from     : {d.atdd_import_path or '<cannot import atdd>'}")
    lines.append(f"  repo root              : {d.repo_root or '<not in a repo>'}")
    lines.append(f"  repo is atdd checkout  : {d.repo_is_atdd_checkout}")
    lines.append(f"  imported from this tree: {d.imported_from_tree}")
    lines.append("")

    status = ok if d.can_import_atdd else fail
    lines.append(f"  [{status}] this interpreter can import atdd")
    if not d.can_import_atdd:
        lines.append(
            "         atdd is not importable here — likely installed in an "
            "isolated venv (pipx) that is not on this interpreter's path."
        )

    status = ok if d.hook_python_can_import_atdd else fail
    lines.append(f"  [{status}] git hooks' python3 can import atdd")
    if not d.hook_python_can_import_atdd:
        lines.append(
            "         the bare `python3` your git hooks invoke cannot import "
            "atdd, so the pre-push version gate prints a misleading 'requires "
            "a newer atdd package' and blocks the push. This is an environment "
            "fault, NOT a stale package."
        )

    if d.repo_is_atdd_checkout:
        status = ok if not d.source_repo_mismatch else fail
        lines.append(f"  [{status}] atdd validators run against THIS working tree")
        if d.source_repo_mismatch:
            lines.append(
                "         you are in the atdd source checkout but `atdd` is "
                "imported from a foreign (pipx/wheel) install, so "
                "`atdd validate` tests the last RELEASED toolkit, not your "
                "edits — new validators look like orphans and unrelated stale "
                "failures block your push."
            )

    lines.append("")
    if d.healthy:
        lines.append("  verdict: healthy")
    else:
        lines.append("  verdict: NOT healthy — remedies:")
        if d.source_repo_mismatch or not d.hook_python_can_import_atdd:
            lines.append(
                "    • Develop atdd from source: install it editable into a venv "
                "(`pip install -e .`) and run hooks/validators with that venv on "
                "PATH, OR run validators with `PYTHONPATH=src` so `atdd.__file__` "
                "points at this working tree."
            )
            lines.append(
                "    • Until then your LOCAL pre-push gate is unreliable for "
                "toolkit changes — rely on CI, which validates repo source."
            )
        if not d.can_import_atdd:
            lines.append(
                "    • Ensure atdd is importable by this interpreter "
                "(`pipx upgrade atdd` only fixes genuine staleness, not path)."
            )

    return "\n".join(lines)


def run_doctor(repo_root: Optional[Path] = None) -> int:
    """CLI entry point for ``atdd doctor``. Returns 0 if healthy, else 1."""
    diagnosis = diagnose_environment(repo_root=repo_root)
    print(format_report(diagnosis))
    return 0 if diagnosis.healthy else 1


__all__ = [
    "EnvDiagnosis",
    "evaluate_diagnosis",
    "diagnose_environment",
    "format_report",
    "run_doctor",
]

# URN: component:enforce-conventions-ci:enforce-conventions-ci:static_ratchet:backend:domain
# Runtime: python
# Purpose: Ratchet external static-analysis findings against a frozen baseline (#1837).

"""Freeze today's lint and type findings; fail only on new ones.

The repository configures no linter and no type checker, so 528 pyright errors
and 401 ruff findings sit unguarded while 74% of source carries annotations
nothing verifies. Fixing them all first is not a plan anyone executes; freezing
them and failing on NEW ones is, and it is the shape `_four_tier_ratchet` (#958)
already established here:

    "The debt is frozen, visible (logged), and shrinking — never rewritten in one
    shot (strangler-fig at the process level)."

IDENTITY EXCLUDES THE LINE NUMBER, deliberately. Keying on it would re-report
every frozen finding the moment an unrelated edit moved it down the file, and a
baseline that decays into noise within days is worse than none.

AN UNRUNNABLE TOOL REFUSES. `resolve_tool` raises rather than returning nothing,
because a gate that skips when its tool is absent reports green over an
observation it never made — the defect shape this repository has now fixed in
five separate forms (#1747, #1719, #1824 among them).

TEMPORARY BY DESIGN. The right home is `atdd enforce`, which already ratchets 21
rules from `.atdd/enforce-ratchet.yaml`. A rule there is a workspace
implementation, and no implementation can declare the external binary a linter
needs — that gap is #1836. When it closes, these move and this module retires.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Set

import yaml

logger = logging.getLogger(__name__)


class ToolUnavailable(RuntimeError):
    """The analysis tool could not be run, so nothing was observed."""


@dataclass(frozen=True)
class Finding:
    """One finding from an external analyser."""

    path: str
    rule: str
    line: int
    message: str


def finding_identity(finding: Finding) -> str:
    """Stable identity for baselining: file and rule, never the line."""
    return f"{finding.rule}::{finding.path}"


def resolve_tool(name: str) -> List[str]:
    """The argv that runs *name*, or refuse saying how to get it.

    PATH only. A network-fetching fallback (`uvx`, `npx`) would make a gate's
    verdict depend on connectivity, so the dependency is declared instead — see
    the `dev` extra and validate-coder's install step.
    """
    found = shutil.which(name)
    if not found:
        raise ToolUnavailable(
            f"{name!r} is not installed, so nothing was analysed and this gate "
            f"cannot report a verdict. Install it: `pip install {name}` (it is "
            f"declared in the project's `dev` extra)."
        )
    return [found]


def new_findings(findings: Iterable[Finding], baseline: Set[str]) -> List[Finding]:
    """Findings whose identity is NOT frozen in *baseline*."""
    return [f for f in findings if finding_identity(f) not in baseline]


def load_baseline(path: Path) -> Set[str]:
    """Frozen identities, or an empty set when the file is absent."""
    if not path.exists():
        return set()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "static-analysis baseline unreadable; treating as empty",
            extra={"path": str(path), "error": str(exc)},
        )
        return set()
    return {str(item) for item in (data.get("frozen") or [])}


def write_baseline(path: Path, findings: Sequence[Finding], tool: str) -> Path:
    """Snapshot *findings* as a frozen, deterministically ordered register."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "tool": tool,
                "note": (
                    f"Frozen {tool} debt (#1837). The gate fails only on findings "
                    "NOT listed here. Shrink this list; never grow it to make a "
                    "red build green — that is what the gate is for."
                ),
                "frozen": sorted({finding_identity(f) for f in findings}),
            },
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return path


# --- baseline locations (relative to the repo root) -------------------------

LINT_BASELINE_REL = Path(".atdd/baselines/lint_toolkit.yaml")
TYPE_BASELINE_REL = Path(".atdd/baselines/types_toolkit.yaml")

_TOOL_TIMEOUT_S = 600


def _run(argv: Sequence[str], cwd: Path, tool: str) -> str:
    """Run an analyser and return stdout, refusing when it could not report.

    A non-zero exit is EXPECTED — both tools exit 1 when they find something —
    so the verdict is taken from the output, not the status. An empty stdout,
    however, means nothing was observed, and that must refuse rather than parse
    as "no findings".
    """
    try:
        proc = subprocess.run(
            list(argv), cwd=str(cwd), capture_output=True, text=True, timeout=_TOOL_TIMEOUT_S
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ToolUnavailable(f"{tool} could not be run ({exc}), so nothing was analysed.") from exc
    if not proc.stdout.strip():
        raise ToolUnavailable(
            f"{tool} produced no output (exit {proc.returncode}); stderr: "
            f"{proc.stderr.strip()[:400] or '<empty>'}. Nothing was analysed."
        )
    return proc.stdout


def _relative(path_str: str, repo_root: Path) -> str:
    """Repo-relative POSIX path, so an identity survives a different checkout.

    A path outside the root is an ordinary outcome, not an error — a tool may
    report on a symlinked or installed file — so it is tested for rather than
    caught, and the absolute path is kept as its own stable identity.
    """
    resolved = Path(path_str).resolve()
    root = repo_root.resolve()
    if resolved.is_relative_to(root):
        return resolved.relative_to(root).as_posix()
    return resolved.as_posix()


def collect_lint_findings(repo_root: Path) -> List[Finding]:
    """Every ruff diagnostic under the repository's own [tool.ruff] config."""
    argv = [*resolve_tool("ruff"), "check", "--no-cache", "--output-format", "json", "src"]
    raw = json.loads(_run(argv, repo_root, "ruff"))
    return [
        Finding(
            path=_relative(item["filename"], repo_root),
            rule=item.get("code") or "<no-code>",
            line=int((item.get("location") or {}).get("row") or 0),
            message=item.get("message", ""),
        )
        for item in raw
    ]


def pyright_argv() -> List[str]:
    """pyright, PINNED to the interpreter running this process.

    Left to itself pyright picks an interpreter off PATH, and its verdict depends
    on what that one has installed: measured on this tree, the same source yields
    575 errors against the environment holding the project's dependencies and 647
    against a bare one. A frozen baseline built under one and checked under the
    other is a gate that fails for a reason no commit caused.

    `sys.executable` is the environment the code under analysis actually imports
    from — in CI the job python that just ran `pip install -e .`, locally the venv
    running pytest — so the analysis matches the runtime rather than the PATH.
    """
    return [*resolve_tool("pyright"), "--outputjson", "--pythonpath", sys.executable]


def collect_type_findings(repo_root: Path) -> List[Finding]:
    """Every pyright diagnostic of severity error, per pyrightconfig.json."""
    argv = pyright_argv()
    raw = json.loads(_run(argv, repo_root, "pyright"))
    return [
        Finding(
            path=_relative(item["file"], repo_root),
            rule=item.get("rule") or "<no-rule>",
            line=int(((item.get("range") or {}).get("start") or {}).get("line") or 0) + 1,
            message=item.get("message", "").splitlines()[0] if item.get("message") else "",
        )
        for item in raw.get("generalDiagnostics", [])
        if item.get("severity") == "error"
    ]


def format_new_findings(findings: Sequence[Finding], tool: str, baseline_rel: Path) -> str:
    """The failure message: what is new, and what NOT to do about it."""
    shown = sorted(findings, key=lambda f: (f.path, f.rule, f.line))[:25]
    lines = [f"{len(findings)} new {tool} finding(s) not present in {baseline_rel}:", ""]
    lines += [f"  {f.path}:{f.line}  {f.rule}  {f.message}" for f in shown]
    if len(findings) > len(shown):
        lines.append(f"  ... and {len(findings) - len(shown)} more")
    lines += [
        "",
        "Fix them, or scope a suppression where the shape is deliberate. Do NOT add",
        f"these identities to {baseline_rel}: that file freezes debt which predates",
        "the gate, and growing it to green a red build is what makes a ratchet useless.",
    ]
    return "\n".join(lines)

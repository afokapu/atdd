"""
Session launch template generator.

`atdd session-template <issue-number>` reads a GitHub issue body, extracts the
metadata table, Dependencies section, and WMBT grep gates, then renders
SESSION-LAUNCH-TEMPLATE.md into a self-contained launch script for a parallel
agent session.

SPEC-COACH-ORCH-0008
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "SESSION-LAUNCH-TEMPLATE.md"


@dataclass
class IssueContext:
    number: int
    title: str = ""
    branch: str = "TBD"
    train: str = "TBD"
    feature: str = ""
    dependencies: list[str] = field(default_factory=list)
    grep_gates: list[str] = field(default_factory=list)
    worktree_path: str = ""
    stop_condition: str = (
        "Stop at the REFACTOR boundary. Do not proceed past REFACTOR "
        "without user confirmation unless --autonomous was set."
    )


_METADATA_ROW = re.compile(r"\|\s*([A-Za-z ]+?)\s*\|\s*(.+?)\s*\|")
_DEP_NUMBER = re.compile(r"#(\d+)")
_GREP_LINE = re.compile(r"`(grep[^`]+)`")


def parse_metadata(body: str) -> dict[str, str]:
    """Parse the Issue Metadata table at the top of an issue body."""
    meta: dict[str, str] = {}
    in_table = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_table:
                break
            if "Issue Metadata" in stripped:
                in_table = True
            continue
        if not in_table:
            continue
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").strip()) <= {"-", " ", ":"}:
            continue
        match = _METADATA_ROW.match(stripped)
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        if key.lower() == "field":
            continue
        value = value.strip("`")
        if "<!--" in value:
            value = value[: value.index("<!--")].strip()
        meta[key] = value
    return meta


def parse_section(body: str, heading: str) -> str:
    """Return the text of a section identified by its heading (e.g. '### Dependencies')."""
    lines = body.splitlines()
    capture = False
    target_level = heading.count("#")
    out: list[str] = []
    for line in lines:
        if line.strip().startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if capture and level <= target_level:
                break
            if line.strip() == heading:
                capture = True
                continue
        if capture:
            out.append(line)
    return "\n".join(out).strip()


def parse_dependencies(body: str) -> list[str]:
    """Extract dependency issue numbers from the ### Dependencies section.

    One dep per line; first #NNN wins. Falls back to Closes/Fixes/Resolves.
    """
    section = parse_section(body, "### Dependencies")
    deps: list[str] = []
    for line in section.splitlines():
        match = _DEP_NUMBER.search(line)
        if match:
            token = f"#{match.group(1)}"
            if token not in deps:
                deps.append(token)
    if not deps:
        for match in re.finditer(
            r"(?:Closes|Fixes|Resolves)\s+#(\d+)", body, flags=re.IGNORECASE
        ):
            token = f"#{match.group(1)}"
            if token not in deps:
                deps.append(token)
    return deps


def parse_grep_gates(body: str) -> list[str]:
    """Extract grep commands from the issue body (backtick-delimited)."""
    gates: list[str] = []
    for line in body.splitlines():
        for match in _GREP_LINE.finditer(line):
            cmd = match.group(1).strip()
            if cmd not in gates:
                gates.append(cmd)
    return gates


def fetch_issue(issue_number: int) -> dict:
    """Fetch an issue via `gh issue view`. Returns empty dict on failure."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json", "number,title,body"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def build_context(
    issue_number: int,
    body: str,
    title: str = "",
    worktree_path: str = "",
) -> IssueContext:
    meta = parse_metadata(body)
    deps = parse_dependencies(body)
    gates = parse_grep_gates(body)
    return IssueContext(
        number=issue_number,
        title=title or meta.get("Feature", ""),
        branch=meta.get("Branch", "TBD") or "TBD",
        train=meta.get("Train", "TBD") or "TBD",
        feature=meta.get("Feature", ""),
        dependencies=deps,
        grep_gates=gates,
        worktree_path=worktree_path or f"../{meta.get('Branch', '').replace('/', '-')}",
    )


def render(context: IssueContext, template_path: Path = TEMPLATE_PATH) -> str:
    template = template_path.read_text()
    deps_block = (
        "\n".join(f"- {d}" for d in context.dependencies)
        if context.dependencies
        else "_(no dependencies declared)_"
    )
    dep_search = " ".join(context.dependencies) if context.dependencies else ""
    gates_block = (
        "\n".join(f"- `{g}`" for g in context.grep_gates)
        if context.grep_gates
        else "_(no grep gates declared — add them to the issue body)_"
    )
    substitutions = {
        "{{issue_number}}": str(context.number),
        "{{title}}": context.title or "(untitled)",
        "{{branch}}": context.branch,
        "{{train}}": context.train,
        "{{feature}}": context.feature,
        "{{dependencies}}": deps_block,
        "{{dependency_search}}": dep_search,
        "{{grep_gates}}": gates_block,
        "{{stop_condition}}": context.stop_condition,
        "{{worktree_path}}": context.worktree_path,
    }
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(key, value)
    return rendered


def run(
    issue_number: int,
    output: Optional[Path] = None,
    worktree_path: str = "",
) -> int:
    issue = fetch_issue(issue_number)
    if not issue:
        print(
            f"❌ Could not fetch issue #{issue_number}. "
            f"Is `gh` authenticated and the issue accessible?",
            file=sys.stderr,
        )
        return 1
    body = issue.get("body") or ""
    title = issue.get("title") or ""
    context = build_context(
        issue_number=issue_number,
        body=body,
        title=title,
        worktree_path=worktree_path,
    )
    rendered = render(context)
    if output:
        output.write_text(rendered)
        print(f"✓ wrote launch script to {output}")
    else:
        sys.stdout.write(rendered)
    return 0

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
class Dependency:
    """A typed dependency entry from a ## Dependencies section."""
    number: str       # e.g. "#123"
    dep_class: str    # "prereq" | "sibling"
    bare: bool = False  # True when no classification tag was present


@dataclass
class IssueContext:
    number: int
    title: str = ""
    branch: str = "TBD"
    train: str = "TBD"
    feature: str = ""
    dependencies: list[str] = field(default_factory=list)
    typed_dependencies: list[Dependency] = field(default_factory=list)
    grep_gates: list[str] = field(default_factory=list)
    worktree_path: str = ""
    canonical_session_name: str = ""
    stop_condition: str = (
        "Stop at the REFACTOR boundary. Do not proceed past REFACTOR "
        "without user confirmation unless --autonomous was set."
    )
    wagon: str = ""


_METADATA_ROW = re.compile(r"\|\s*([A-Za-z ]+?)\s*\|\s*(.+?)\s*\|")
_DEP_NUMBER = re.compile(r"#(\d+)")
_GREP_LINE = re.compile(r"`(grep[^`]+)`")
_SIBLING_TAG = re.compile(r"\(\s*(?:sibling|parallel)[^)]*\)", re.IGNORECASE)
_PREREQ_TAG = re.compile(r"\(\s*(?:prereq|merged)[^)]*\)", re.IGNORECASE)


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


def parse_typed_dependencies(body: str) -> list[Dependency]:
    """Extract and classify dependency entries from the ### Dependencies section.

    Each line's first #NNN ref is extracted and classified by trailing tag:
      (sibling) / (parallel) → dep_class="sibling"
      (prereq)  / (merged)   → dep_class="prereq"
      no tag                 → dep_class="prereq", bare=True
    """
    section = parse_section(body, "### Dependencies")
    deps: list[Dependency] = []
    seen: set[str] = set()
    for line in section.splitlines():
        match = _DEP_NUMBER.search(line)
        if not match:
            continue
        number = f"#{match.group(1)}"
        if number in seen:
            continue
        seen.add(number)
        if _SIBLING_TAG.search(line):
            deps.append(Dependency(number=number, dep_class="sibling"))
        elif _PREREQ_TAG.search(line):
            deps.append(Dependency(number=number, dep_class="prereq"))
        else:
            deps.append(Dependency(number=number, dep_class="prereq", bare=True))
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
    except (FileNotFoundError, subprocess.CalledProcessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return {}


def _derive_worktree_path(branch: str) -> str:
    """Where a spawned agent should `cd` for this branch.

    Formerly `f"../{branch.replace('/', '-')}"` — a third derivation algorithm,
    emitting a relative path that hardcoded the flat-sibling layout. It now
    routes through the same resolver as the two creation paths, so the launch
    prompt names the directory that was actually created (#1524 E002).
    """
    if not branch:
        return ""
    from atdd.coach.commands.worktree_placement import resolve_worktree_path
    from atdd.coach.utils.repo import find_repo_root

    prefix, _, slug = branch.partition("/")
    if not slug:
        prefix, slug = "feat", branch
    try:
        return str(resolve_worktree_path(find_repo_root(), prefix, slug))
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Prompt rendering must not fail because a repo root is unresolvable;
        # fall back to the legacy relative form rather than emitting nothing.
        return f"../{branch.replace('/', '-')}"


def build_context(
    issue_number: int,
    body: str,
    title: str = "",
    worktree_path: str = "",
) -> IssueContext:
    from atdd.coach.utils.config import load_atdd_config
    from atdd.coach.utils.repo import find_repo_root
    from atdd.coach.utils.session_naming import (
        branch_to_slug,
        compute_canonical_name,
        compute_repo_short_name,
    )

    meta = parse_metadata(body)
    deps = parse_dependencies(body)
    typed_deps = parse_typed_dependencies(body)
    gates = parse_grep_gates(body)
    branch = meta.get("Branch", "TBD") or "TBD"
    # Issue #470: precompute the canonical session name so the launch prompt
    # can echo "your canonical name is X" — keeps the agent's self-rename
    # aligned with the cmux tab even if the dispatch-time pass missed.
    try:
        config = load_atdd_config(find_repo_root())
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        config = {}
    repo_short = compute_repo_short_name(config)
    slug = branch_to_slug(branch) if branch != "TBD" else f"issue-{issue_number}"
    canonical_name = compute_canonical_name(repo_short, issue_number, slug or f"issue-{issue_number}")
    return IssueContext(
        number=issue_number,
        title=title or meta.get("Feature", ""),
        branch=branch,
        train=meta.get("Train", "TBD") or "TBD",
        feature=meta.get("Feature", ""),
        dependencies=deps,
        typed_dependencies=typed_deps,
        grep_gates=gates,
        worktree_path=worktree_path or _derive_worktree_path(meta.get("Branch", "")),
        canonical_session_name=canonical_name,
    )


def _render_merge_wait_section(typed_deps: list[Dependency]) -> str:
    """Render the dependency wait block based on classified dep entries.

    - prereq entries → merge-wait bash loop
    - sibling entries → "Parallel siblings (for context)" block
    - bare entries → warning comment prepended
    - no prereqs → "begin planning immediately" note
    """
    prereq_nums = [d.number for d in typed_deps if d.dep_class == "prereq"]
    sibling_nums = [d.number for d in typed_deps if d.dep_class == "sibling"]
    bare_nums = [d.number for d in typed_deps if d.bare]

    parts: list[str] = []

    if bare_nums:
        joined = " ".join(bare_nums)
        parts.append(
            f"# WARNING: the following dep(s) have no classification tag: {joined}\n"
            "# Add (prereq), (merged), (sibling), or (parallel) to each entry\n"
            "# in ## Dependencies to suppress this warning and avoid future\n"
            "# infinite merge-wait loops for sibling issues."
        )

    if prereq_nums:
        dep_search = " ".join(prereq_nums)
        parts.append(
            "Before starting, wait for all prerequisite PRs to merge. Use this loop:\n"
            "\n"
            "```bash\n"
            "while true; do\n"
            f'  if gh pr list --state merged --search "{dep_search}" --json number --jq \'length\' | grep -qv \'^0$\'; then\n'
            '    echo "Dependencies merged — proceeding"\n'
            "    break\n"
            "  fi\n"
            '  echo "Waiting for dependencies..."\n'
            "  sleep 60\n"
            "done\n"
            "```"
        )
    else:
        parts.append(
            "# NOTE (manual dispatch, 2026-05-21): the rendered merge-wait\n"
            "# loop has been removed because some listed dependencies are open\n"
            "# sibling issues in the same release wave (per #831 bug). Treat\n"
            "# them as parallel-work context, not merge-prerequisites.\n"
            "# No prerequisites — begin planning immediately."
        )

    if sibling_nums:
        joined = " ".join(sibling_nums)
        parts.append(
            f"**Parallel siblings (for context — do not block):** {joined}\n\n"
            "These issues are designed to run in parallel in the same release wave.\n"
            "Do not wait for them to merge before beginning this session."
        )

    return "\n\n".join(parts)


def render(context: IssueContext, template_path: Path = TEMPLATE_PATH) -> str:
    template = template_path.read_text()
    # deps_block: display list uses typed_dependencies when available, else legacy strings
    if context.typed_dependencies:
        def _dep_label(d: Dependency) -> str:
            tag = f" ({d.dep_class})" if not d.bare else ""
            return f"- {d.number}{tag}"
        deps_block = "\n".join(_dep_label(d) for d in context.typed_dependencies)
    elif context.dependencies:
        deps_block = "\n".join(f"- {d}" for d in context.dependencies)
    else:
        deps_block = "_(no dependencies declared)_"

    merge_wait_section = _render_merge_wait_section(context.typed_dependencies)

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
        "{{merge_wait_section}}": merge_wait_section,
        "{{grep_gates}}": gates_block,
        "{{stop_condition}}": context.stop_condition,
        "{{worktree_path}}": context.worktree_path,
        "{{canonical_session_name}}": context.canonical_session_name,
    }
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(key, value)
    return rendered


def _format_checkpoint_block(checkpoint: dict) -> str:
    open_files = checkpoint.get("open_files") or []
    files_block = (
        "\n".join(f"- `{f}`" for f in open_files)
        if open_files
        else "_(no open files recorded)_"
    )
    summary = (checkpoint.get("summary") or "").strip() or "_(no summary recorded)_"
    return (
        "\n## Resumed from checkpoint\n\n"
        f"- **Phase:** `{checkpoint.get('phase', 'UNKNOWN')}`\n"
        f"- **Last commit:** `{checkpoint.get('last_commit', 'unknown')}`\n"
        f"- **Checkpointed at:** {checkpoint.get('checkpointed_at', 'unknown')}\n\n"
        "### Summary at last checkpoint\n\n"
        f"{summary}\n\n"
        "### Open files at last checkpoint\n\n"
        f"{files_block}\n"
    )


def render_with_checkpoint(
    context: IssueContext,
    template_path: Path = TEMPLATE_PATH,
    *,
    root: Optional[Path] = None,
) -> str:
    """Render the launch script with a `## Resumed from checkpoint` block
    inlined when ``.atdd/worker-state-<N>.json`` exists. Falls back to plain
    `render()` when no checkpoint is found.
    """
    from atdd.coach.commands.checkpoint import read_worker_checkpoint

    plain = render(context, template_path=template_path)
    checkpoint = read_worker_checkpoint(context.number, root=root)
    if checkpoint is None:
        return plain
    return plain + _format_checkpoint_block(checkpoint)


def run(
    issue_number: int,
    output: Optional[Path] = None,
    worktree_path: str = "",
    *,
    from_checkpoint: bool = False,
    root: Optional[Path] = None,
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
    rendered = (
        render_with_checkpoint(context, root=root)
        if from_checkpoint
        else render(context)
    )
    if output:
        output.write_text(rendered)
        print(f"✓ wrote launch script to {output}")
    else:
        sys.stdout.write(rendered)
    return 0

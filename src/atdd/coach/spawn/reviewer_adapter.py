# URN: component:review-phase-boundaries:reviewer-no-write-adapter:spawn:application
# Runtime: python

"""Reviewer-persona spawn-adapter variant (issue #526, spec §6.3).

Layers over the base spawn adapter from ``wagon:spawn-agents`` (#503) to:

1. Strip every commit/edit tool from the rendered tool allowlist so the
   reviewer cannot mutate the worktree.
2. Embed a no-write system prompt that explicitly forbids edits and names
   ``atdd agent review --target-commit <sha> --report-file <path>`` as the
   sole output channel.
3. Produce a tool allowlist section that enumerates the surviving (read-only)
   tools, making the deny-set auditable in the rendered prompt.

Observer rule ``08-reviewer-edit-attempt`` (#506) is the runtime catch;
this adapter is the structural floor.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Denied tools — every worktree-mutating surface the reviewer must not use
# ---------------------------------------------------------------------------

DENIED_TOOLS: frozenset[str] = frozenset({
    "Edit",
    "Write",
    "NotebookEdit",
    "MultiEdit",
    "Bash(git commit",
    "Bash(git push",
    "Bash(git reset",
    "Bash(dangerouslyDisableSandbox",
})

# ---------------------------------------------------------------------------
# Allowed tools — the read-only set the reviewer may use
# ---------------------------------------------------------------------------

ALLOWED_TOOLS: tuple[str, ...] = (
    "Read",
    "Bash(git log",
    "Bash(git diff",
    "Bash(git show",
    "Bash(git status",
    "Bash(git blame",
    "Bash(cat",
    "Bash(find",
    "Bash(grep",
    "Bash(python3",
    "Agent",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
)

# ---------------------------------------------------------------------------
# No-write system prompt
# ---------------------------------------------------------------------------

REVIEWER_NO_WRITE_PROMPT = textwrap.dedent("""\
    ## REVIEWER PERSONA — NO-WRITE CONSTRAINT (spec §6.3 hard rule)

    You are a **Reviewer** agent. Your role is adversarial review of the
    worktree at this phase boundary. You have **read-only** access.

    ### Forbidden actions (absolute, non-negotiable)

    You MUST NOT:
    - Edit, write, or modify any file in the worktree
    - Run `git commit`, `git push`, `git reset`, or any worktree-mutating git command
    - Use any tool that modifies the filesystem (Edit, Write, NotebookEdit, MultiEdit)
    - Use `dangerouslyDisableSandbox` or bypass any safety mechanism

    ### Sole output channel

    Your ONLY sanctioned output is:

        atdd agent review --target-commit <sha> --report-file <path>

    This command writes a structured review report. All findings, verdicts,
    and recommendations MUST flow through this channel. Do not commit, comment,
    or escalate ad-hoc.

    ### Tool allowlist

    You may ONLY use the following tools:
    {allowed_tools_block}

    Any tool not in this list is forbidden. If you believe you need a tool
    that is not listed, escalate via `atdd agent ask` — do not attempt to
    use it.
""")


def _render_allowed_tools_block() -> str:
    """Render the allowed-tools list as a markdown bullet list."""
    lines = []
    for tool in ALLOWED_TOOLS:
        lines.append(f"- `{tool}`")
    return "\n".join(lines)


def render_reviewer_launch_prompt(
    base_prompt: str,
    *,
    target_commit: Optional[str] = None,
) -> str:
    """Layer the reviewer no-write constraints over the base launch prompt.

    Appends the no-write system prompt section and tool allowlist to the
    base prompt. The base prompt is left untouched — only appended content
    diverges from the non-reviewer path.
    """
    allowed_block = _render_allowed_tools_block()
    no_write_section = REVIEWER_NO_WRITE_PROMPT.format(
        allowed_tools_block=allowed_block,
    )

    parts = [base_prompt.rstrip(), no_write_section]

    if target_commit:
        commit_anchor = textwrap.dedent(f"""\
            ### Review target

            Target commit: `{target_commit}`

            Run your review with:
                atdd agent review --target-commit {target_commit} --report-file <path>
        """)
        parts.append(commit_anchor)

    return "\n".join(parts)

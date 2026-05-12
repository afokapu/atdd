# URN: component:review-phase-boundaries:phase-boundary-review:coach-review-operator:application
# Runtime: python

"""`atdd coach review` — operator-facing reviewer trigger (issue #624, E002).

Spawns a reviewer-persona agent via the N1 no-write spawn adapter, waits
for the reviewer to call `atdd agent review`, validates the resulting
review-report.json, and prints a verdict summary (or JSON payload).

CLI surface:
    atdd coach review <N>               # Resolve PR number → head commit
    atdd coach review --commit <sha>    # Use commit directly
    atdd coach review --phase <phase>   # Override review phase (default: green)
    atdd coach review --llm <id>        # Override reviewer LLM
    atdd coach review --output text|json

Exit codes (spec §E002):
    0 — pass
    1 — fail
    2 — concern

Out of scope:
- Modifying `atdd agent review` semantics (agent-only)
- Auto-merging based on verdict
- Cross-LLM aggregation (that is `atdd issue review`)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_PHASE = "GREEN"
_DEFAULT_LLM = "claude-code"
_POLL_INTERVAL = float(os.environ.get("ATDD_REVIEWER_POLL_INTERVAL", "1.0"))
_TIMEOUT = float(os.environ.get("ATDD_REVIEWER_TIMEOUT", "3600.0"))

_EXIT_PASS = 0
_EXIT_FAIL = 1
_EXIT_CONCERN = 2

_VERDICT_EXIT: dict[str, int] = {
    "pass": _EXIT_PASS,
    "fail": _EXIT_FAIL,
    "concern": _EXIT_CONCERN,
}


# ---------------------------------------------------------------------------
# Commit resolution
# ---------------------------------------------------------------------------


def resolve_commit_from_pr(pr_number: int) -> str:
    """Resolve a PR number to its head commit SHA via `gh pr view`."""
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "headRefOid"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh pr view {pr_number} failed: {result.stderr.strip()}"
        )
    data = json.loads(result.stdout)
    sha: str = data["headRefOid"]
    return sha


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------


def _runtime_root() -> Path:
    env = os.environ.get("ATDD_RUNTIME_ROOT")
    return Path(env) if env else Path.cwd() / ".atdd" / "runtime"


def _find_review_report(reviewer_agent_dir: Path) -> Optional[dict]:
    reviews_dir = reviewer_agent_dir / "reviews"
    if not reviews_dir.exists():
        return None
    for review_file in sorted(reviews_dir.glob("*.json")):
        try:
            return json.loads(review_file.read_text())
        except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            continue
    return None


def _wait_for_report(
    reviewer_agent_dir: Path,
    *,
    timeout: float = _TIMEOUT,
    poll_interval: float = _POLL_INTERVAL,
) -> Optional[dict]:
    """Poll until a review report appears or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        report = _find_review_report(reviewer_agent_dir)
        if report is not None:
            return report
        time.sleep(poll_interval)
    return None


def _spawn_reviewer_agent(
    target_commit: str,
    *,
    llm: str = _DEFAULT_LLM,
    phase: str = _DEFAULT_PHASE,
    reviewer_agent_id: str,
    runtime_root: Path,
) -> str:
    """Spawn a reviewer-persona agent via the K1+N1 adapter.

    Returns the reviewer_agent_id. Errors propagate to the caller.
    """
    from atdd.coach.commands import spawn as spawn_mod
    from atdd.coach.utils.multiplexer import get_multiplexer

    multiplexer = get_multiplexer(preferred=None)
    worktree = Path.cwd()

    spawn_mod.cmd_spawn(
        persona="reviewer",
        llm=llm,
        worktree=worktree,
        issue=0,
        agent_id=reviewer_agent_id,
        runtime_root=runtime_root,
        phase=phase,
        target_commit=target_commit,
        multiplexer=multiplexer,
    )
    return reviewer_agent_id


def _write_reviewer_manifest(
    agent_dir: Path,
    agent_id: str,
    phase: str,
) -> None:
    manifest = {
        "agent_id": agent_id,
        "issue": 0,
        "persona": "reviewer",
        "phase": phase,
    }
    tmp = agent_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, sort_keys=True))
    tmp.replace(agent_dir / "manifest.json")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atdd coach review",
        description=(
            "Operator-facing reviewer trigger. Spawns a reviewer-persona agent "
            "against a PR or commit, waits for the review report, and prints "
            "the verdict. Exits 0 on pass, 1 on fail, 2 on concern."
        ),
    )
    p.add_argument(
        "pr_number",
        type=int,
        nargs="?",
        default=None,
        help="PR number to review (resolves to head commit via gh).",
    )
    p.add_argument(
        "--commit",
        type=str,
        default=None,
        dest="commit_sha",
        metavar="SHA",
        help="Review a specific commit SHA directly (bypasses gh).",
    )
    p.add_argument(
        "--phase",
        type=str,
        default=_DEFAULT_PHASE,
        help=f"Review phase to use in the reviewer prompt (default: {_DEFAULT_PHASE}).",
    )
    p.add_argument(
        "--llm",
        type=str,
        default=None,
        help="Override reviewer LLM (default: claude-code).",
    )
    p.add_argument(
        "--output",
        type=str,
        choices=["text", "json"],
        default="text",
        dest="output_format",
        help="Output format: text summary (default) or JSON payload.",
    )
    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_review(argv: list[str]) -> int:
    """Main entry point for `atdd coach review`.

    Returns an integer exit code.
    """
    parser = _build_parser()
    ns = parser.parse_args(argv)

    # Guard: ensure at least one LLM is registered before spawning anything.
    from atdd.coach.commands import judge as judge_mod
    if not judge_mod.LLM_REGISTRY:
        print(
            "error: no LLM clients configured — see docs/MODELS.md",
            file=sys.stderr,
        )
        return _EXIT_FAIL

    # Resolve commit SHA
    if ns.commit_sha:
        commit_sha = ns.commit_sha
    elif ns.pr_number is not None:
        try:
            commit_sha = resolve_commit_from_pr(ns.pr_number)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return _EXIT_FAIL
    else:
        parser.error("Provide a PR number or --commit <sha>.")

    llm = ns.llm or _DEFAULT_LLM
    phase = ns.phase.upper()

    runtime_root = _runtime_root()
    reviewer_agent_id = (
        f"reviewer-operator-{phase.lower()}-{uuid.uuid4().hex[:8]}"
    )
    reviewer_agent_dir = runtime_root / "agents" / reviewer_agent_id
    reviewer_agent_dir.mkdir(parents=True, exist_ok=True)

    _write_reviewer_manifest(reviewer_agent_dir, reviewer_agent_id, phase)

    try:
        _spawn_reviewer_agent(
            commit_sha,
            llm=llm,
            phase=phase,
            reviewer_agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
        )
    except Exception as exc:
        print(f"warning: spawn failed ({exc}); polling for pre-written report", file=sys.stderr)

    report = _wait_for_report(reviewer_agent_dir)
    if report is None:
        print(
            f"error: timeout waiting for review report from {reviewer_agent_id}",
            file=sys.stderr,
        )
        return _EXIT_FAIL

    from atdd.coach.utils.review_report_intake import validate_review_report
    intake = validate_review_report(report)
    if not intake.valid:
        print(
            "error: review report failed validation:\n"
            + "\n".join(f"  {m}" for m in intake.error_messages),
            file=sys.stderr,
        )
        return _EXIT_FAIL

    verdict = report.get("verdict", "fail")

    if ns.output_format == "json":
        print(json.dumps(report, indent=2))
    else:
        _print_text_summary(report, verdict)

    return _VERDICT_EXIT.get(verdict, _EXIT_FAIL)


def _print_text_summary(report: dict, verdict: str) -> None:
    verdict_icon = {"pass": "✓", "fail": "✗", "concern": "⚠"}.get(verdict, "?")
    print(f"{verdict_icon} verdict: {verdict}")
    print(f"  commit : {report.get('target_commit', 'unknown')}")
    print(f"  phase  : {report.get('phase', 'unknown')}")
    summary = report.get("summary", "")
    if summary:
        print(f"  summary: {summary}")
    findings = report.get("findings") or []
    if findings:
        print(f"  findings ({len(findings)}):")
        for f in findings:
            sev = f.get("severity", "?")
            desc = f.get("description", "")
            loc = f.get("location", "")
            print(f"    [sev={sev}] {loc}: {desc}")

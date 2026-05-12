# URN: component:review-phase-boundaries:operator-facing-review-trigger:coach-review:application
# Runtime: python
"""`atdd coach review` — operator-facing reviewer trigger (#624).

Wraps the same N1+N5 internals used by the coach state-machine reviewer
handler, but provides a direct operator surface:

    atdd coach review <N>                  # Review PR by number
    atdd coach review --commit <sha>       # Review a specific commit
    atdd coach review <N> --report-file <path>   # Persist verdict JSON
    atdd coach review <N> --output json    # JSON output instead of summary
    atdd coach review <N> --llm <id>       # Override reviewer LLM

Internal flow:
1. Resolve target commit (from PR number via gh, or --commit directly).
2. Guard: require at least one LLM client in LLM_REGISTRY.
3. Spawn a reviewer-persona agent via the N1 adapter.
4. Poll .atdd/runtime/agents/<reviewer-id>/reviews/ for the report.
5. Validate via review_report_intake.
6. Print verdict summary (or JSON with --output json).
7. Optionally persist report to --report-file.
8. Exit 0 on pass, nonzero on fail/concern/timeout.

Public surface (testable seams):
  ``run(*, pr_number, commit, llm, output, report_file) -> int``
  ``_spawn_reviewer_agent(reviewer_agent_id, target_commit, runtime_root, llm)``
  ``_resolve_pr_commit(pr_number) -> str``
  ``_print(msg)``  — stdout sink (monkeypatchable)
  ``_print_err(msg)``  — stderr sink (monkeypatchable)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

_POLL_INTERVAL = float(os.environ.get("ATDD_REVIEWER_POLL_INTERVAL", "1.0"))
_TIMEOUT = float(os.environ.get("ATDD_REVIEWER_TIMEOUT", "3600.0"))


# ---------------------------------------------------------------------------
# Stdout / stderr sinks — monkeypatchable in tests
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg)


def _print_err(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Runtime root resolution
# ---------------------------------------------------------------------------


def _runtime_root() -> Path:
    env = os.environ.get("ATDD_RUNTIME_ROOT")
    return Path(env) if env else Path.cwd() / ".atdd" / "runtime"


# ---------------------------------------------------------------------------
# PR → commit resolution (gh CLI seam)
# ---------------------------------------------------------------------------


def _resolve_pr_commit(pr_number: int) -> str:
    """Resolve a GitHub PR number to its head commit sha via `gh pr view`.

    Raises RuntimeError if gh exits nonzero or the sha is absent.
    """
    import subprocess

    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "headRefOid"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh pr view {pr_number} failed (rc={result.returncode}): {result.stderr}"
        )
    try:
        data = json.loads(result.stdout)
        sha = data.get("headRefOid", "")
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(
            f"could not parse gh output for PR {pr_number}: {exc}"
        ) from exc
    if not sha:
        raise RuntimeError(
            f"gh pr view {pr_number} returned empty headRefOid"
        )
    return sha


# ---------------------------------------------------------------------------
# Reviewer spawn seam
# ---------------------------------------------------------------------------


def _spawn_reviewer_agent(
    reviewer_agent_id: str,
    target_commit: str,
    runtime_root_arg: Path,
    llm: str = "claude-code",
) -> None:
    """Write the reviewer manifest and spawn via the N1 adapter.

    Writes manifest.json with persona=reviewer before attempting spawn so
    the runtime directory is always in a consistent state even when spawn
    fails (test environments pre-seed the report without a real process).
    """
    agent_dir = runtime_root_arg / "agents" / reviewer_agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "agent_id": reviewer_agent_id,
        "persona": "reviewer",
        "issue": None,
        "phase": None,
    }
    tmp = agent_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, sort_keys=True))
    tmp.replace(agent_dir / "manifest.json")

    try:
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
            runtime_root=runtime_root_arg,
            phase=None,
            target_commit=target_commit,
            multiplexer=multiplexer,
        )
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        _print_err(
            f"coach review: spawn failed for {reviewer_agent_id}: {exc}"
        )


# ---------------------------------------------------------------------------
# Report polling
# ---------------------------------------------------------------------------


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


def _wait_for_review_report(
    reviewer_agent_dir: Path,
    *,
    timeout: float = _TIMEOUT,
    poll_interval: float = _POLL_INTERVAL,
) -> Optional[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        report = _find_review_report(reviewer_agent_dir)
        if report is not None:
            return report
        time.sleep(poll_interval)
    return None


# ---------------------------------------------------------------------------
# Core run
# ---------------------------------------------------------------------------


def run(
    *,
    pr_number: Optional[int] = None,
    commit: Optional[str] = None,
    llm: Optional[str] = None,
    output: str = "text",
    report_file: Optional[str] = None,
) -> int:
    """Execute one `atdd coach review` invocation. Returns the process exit code."""
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY

    # 1. Guard: require at least one spawn adapter registered.
    if not ADAPTER_REGISTRY:
        _print_err(
            "no LLM clients configured — see docs/MODELS.md to register a client"
        )
        return 3

    # 2. Resolve target commit.
    if commit:
        target_commit = commit
    elif pr_number is not None:
        try:
            target_commit = _resolve_pr_commit(pr_number)
        except RuntimeError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            _print_err(f"coach review: failed to resolve PR {pr_number}: {exc}")
            return 2
    else:
        _print_err("coach review: must provide a PR number or --commit <sha>")
        return 2

    effective_llm = llm or next(iter(ADAPTER_REGISTRY), "claude-code")

    # 3. Create reviewer agent directory.
    runtime = _runtime_root()
    pr_slug = str(pr_number) if pr_number is not None else "commit"
    reviewer_agent_id = f"reviewer-op-{pr_slug}-{uuid.uuid4().hex[:8]}"

    # 4. Spawn reviewer (writes manifest, starts process).
    _spawn_reviewer_agent(reviewer_agent_id, target_commit, runtime, llm=effective_llm)

    # 5. Wait for report.
    reviewer_agent_dir = runtime / "agents" / reviewer_agent_id
    report = _wait_for_review_report(reviewer_agent_dir)
    if report is None:
        _print_err(
            f"coach review: timeout waiting for review report from {reviewer_agent_id}"
        )
        return 4

    # 6. Validate via intake gate.
    from atdd.coach.utils.review_report_intake import validate_review_report

    intake = validate_review_report(report)
    if not intake.valid:
        _print_err(
            "coach review: intake validation failed: "
            + "; ".join(intake.error_messages)
        )
        return 4

    # 7. Persist to --report-file if requested.
    if report_file:
        target = Path(report_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True))

    # 8. Output verdict.
    verdict = report.get("verdict", "unknown")
    if output == "json":
        _print(json.dumps(report, sort_keys=True))
    else:
        summary = report.get("summary", "")
        phase = report.get("phase", "")
        _print(
            f"coach review verdict: {verdict}  phase={phase}  "
            f"agent={reviewer_agent_id}  commit={target_commit[:12]}"
        )
        if summary:
            _print(f"  summary: {summary}")

    if verdict == "pass":
        return 0
    return 1


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach review",
        description=(
            "Run an adversarial reviewer on a PR or commit without a full "
            "coach lifecycle run. Spawns a reviewer-persona agent, waits for "
            "the report, and surfaces the verdict."
        ),
    )
    parser.add_argument(
        "pr_number",
        nargs="?",
        type=int,
        default=None,
        metavar="N",
        help="GitHub PR number to review (resolves to head commit).",
    )
    parser.add_argument(
        "--commit",
        default=None,
        help="Review a specific commit sha directly (bypasses gh PR resolution).",
    )
    parser.add_argument(
        "--llm",
        default=None,
        help="Override the reviewer LLM (must be registered in LLM_REGISTRY).",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format: text summary (default) or raw JSON report.",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        dest="report_file",
        help="Persist the validated review-report.json to this path.",
    )
    return parser


def parse_cli(argv: list[str]) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def run_review(argv: list[str]) -> int:
    """Entry point called by coach.run_cli when argv[0] == 'review'."""
    ns = parse_cli(argv)
    return run(
        pr_number=ns.pr_number,
        commit=ns.commit,
        llm=ns.llm,
        output=ns.output,
        report_file=ns.report_file,
    )

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
    atdd coach review <N> --no-spawn       # In-process mode (no cmux)
    atdd coach review <N> --in-process     # Alias for --no-spawn

Internal flow (spawn-based, default):
1. Resolve target commit (from PR number via gh, or --commit directly).
2. Guard: require at least one LLM client in LLM_REGISTRY.
3. Spawn a reviewer-persona agent via the N1 adapter.
4. Poll .atdd/runtime/agents/<reviewer-id>/reviews/ for the report.
5. Validate via review_report_intake.
6. Print verdict summary (or JSON with --output json).
7. Optionally persist report to --report-file.
8. Exit 0 on pass, nonzero on fail/concern/timeout.

Internal flow (in-process, --no-spawn/--in-process):
1. Resolve target commit.
2. Fetch PR diff via gh pr diff.
3. Call registered LLM client directly (no cmux spawn).
4. Build and validate review report from LLM response.
5. Write --report-file (always, even on LLM failure via sentinel).
6. Exit 0 always (enforce step in CI workflow reads verdict from the file).

Public surface (testable seams):
  ``run(*, pr_number, commit, llm, output, report_file, in_process) -> int``
  ``_spawn_reviewer_agent(reviewer_agent_id, target_commit, runtime_root, llm)``
  ``_run_in_process(*, target_commit, pr_number, llm, report_file, reviewer_agent_id, output) -> int``
  ``_get_pr_diff(*, pr_number, target_commit) -> str``
  ``_build_in_process_report(*, response, target_commit, reviewer_agent_id) -> dict``
  ``_write_broken_sentinel(*, report_file, target_commit, reviewer_agent_id, reason) -> int``
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
# In-process review helpers (--no-spawn / --in-process mode)
# ---------------------------------------------------------------------------


def _get_pr_diff(*, pr_number: Optional[int], target_commit: str) -> str:
    """Fetch a diff for the review prompt. Tries gh pr diff first, falls back to git show."""
    import subprocess

    if pr_number is not None:
        try:
            result = subprocess.run(
                ["gh", "pr", "diff", str(pr_number)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout[:24000]
        except (subprocess.TimeoutExpired, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            pass

    try:
        result = subprocess.run(
            ["git", "show", "--stat", target_commit],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout[:24000]
    except (subprocess.TimeoutExpired, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        pass

    return f"# Diff unavailable for commit {target_commit[:12]}"


def _render_review_prompt(*, diff: str, target_commit: str) -> str:
    return (
        f"Review the following git diff for commit {target_commit[:12]}.\n\n"
        "Evaluate the changes for code correctness, architecture quality, "
        "test coverage adequacy, and security concerns.\n\n"
        f"Diff:\n```\n{diff}\n```\n\n"
        'Return ONLY valid JSON: {"verdict": "pass"|"concern"|"fail", '
        '"summary": "<one paragraph>"}\n\n'
        'Use "pass" when changes look good, "concern" for minor issues that '
        'should be noted but do not block merge, "fail" for significant problems '
        "that should block merge."
    )


def _build_in_process_report(
    *,
    response: object,
    target_commit: str,
    reviewer_agent_id: str,
) -> dict:
    """Build a schema-conforming review report from an LLM response dict."""
    verdict = "fail"
    summary = "In-process review completed."

    if isinstance(response, dict):
        raw_verdict = response.get("verdict", "fail")
        if raw_verdict in ("pass", "concern", "fail"):
            verdict = raw_verdict
        raw_summary = response.get("summary", "")
        if raw_summary and isinstance(raw_summary, str):
            summary = raw_summary

    commit_field = target_commit if len(target_commit) >= 7 else target_commit.ljust(7, "0")

    return {
        "review_id": f"in-process-{uuid.uuid4().hex[:8]}",
        "target_commit": commit_field,
        "reviewer_agent_id": reviewer_agent_id,
        "wmbt_urn": "wmbt:integration-hardening:E005",
        "phase": "REFACTOR",
        "verdict": verdict,
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {},
        "summary": summary,
    }


def _write_broken_sentinel(
    *,
    report_file: Optional[str],
    target_commit: str,
    reviewer_agent_id: str,
    reason: str,
) -> int:
    """Write a review-step-broken sentinel and return 0 (operational failure, not verdict failure)."""
    sentinel = {
        "verdict": "review-step-broken",
        "summary": f"Review gate encountered an operational error: {reason}",
        "reviewer_agent_id": reviewer_agent_id,
        "target_commit": target_commit,
        "error": reason,
    }
    _print_err(
        f"coach review: review-step-broken sentinel written "
        f"(commit={target_commit[:12]}, reason={reason!r})"
    )
    if report_file:
        target = Path(report_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(sentinel, indent=2, sort_keys=True))
    _print(f"coach review verdict: review-step-broken  commit={target_commit[:12]}")
    return 0


def _run_in_process(
    *,
    target_commit: str,
    pr_number: Optional[int],
    llm: Optional[str],
    report_file: Optional[str],
    reviewer_agent_id: str,
    output: str,
) -> int:
    """Execute reviewer logic in-process (no cmux spawn). Always exits 0; verdict is in report file."""
    from atdd.coach.commands.judge import LLM_REGISTRY, LLMUnavailable

    effective_llm = llm or next(iter(LLM_REGISTRY), None)
    if effective_llm is None or effective_llm not in LLM_REGISTRY:
        reason = (
            "no LLM clients registered"
            if effective_llm is None
            else f"{effective_llm!r} not in LLM registry"
        )
        _print_err(f"coach review: in-process mode: {reason}")
        return _write_broken_sentinel(
            report_file=report_file,
            target_commit=target_commit,
            reviewer_agent_id=reviewer_agent_id,
            reason=reason,
        )

    diff = _get_pr_diff(pr_number=pr_number, target_commit=target_commit)

    try:
        factory = LLM_REGISTRY[effective_llm]
        client = factory()
        response = client.invoke(
            _render_review_prompt(diff=diff, target_commit=target_commit)
        )
    except LLMUnavailable as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        _print_err(f"coach review: in-process LLM unavailable ({effective_llm}): {exc}")
        return _write_broken_sentinel(
            report_file=report_file,
            target_commit=target_commit,
            reviewer_agent_id=reviewer_agent_id,
            reason=str(exc),
        )

    report = _build_in_process_report(
        response=response,
        target_commit=target_commit,
        reviewer_agent_id=reviewer_agent_id,
    )

    from atdd.coach.utils.review_report_intake import validate_review_report

    intake = validate_review_report(report)
    if not intake.valid:
        reason = "intake validation failed: " + "; ".join(intake.error_messages)
        _print_err(f"coach review: in-process {reason}")
        return _write_broken_sentinel(
            report_file=report_file,
            target_commit=target_commit,
            reviewer_agent_id=reviewer_agent_id,
            reason=reason,
        )

    if report_file:
        target = Path(report_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True))

    verdict = report.get("verdict", "fail")
    if output == "json":
        _print(json.dumps(report, sort_keys=True))
    else:
        summary = report.get("summary", "")
        _print(
            f"coach review verdict: {verdict}  mode=in-process  "
            f"agent={reviewer_agent_id}  commit={target_commit[:12]}"
        )
        if summary:
            _print(f"  summary: {summary}")

    return 0


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
    in_process: bool = False,
) -> int:
    """Execute one `atdd coach review` invocation. Returns the process exit code."""
    # 1. Resolve target commit.
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

    runtime = _runtime_root()
    pr_slug = str(pr_number) if pr_number is not None else "commit"
    reviewer_agent_id = f"reviewer-op-{pr_slug}-{uuid.uuid4().hex[:8]}"

    # 2. Dispatch: in-process mode skips cmux spawn entirely.
    if in_process:
        return _run_in_process(
            target_commit=target_commit,
            pr_number=pr_number,
            llm=llm,
            report_file=report_file,
            reviewer_agent_id=reviewer_agent_id,
            output=output,
        )

    # 3. Spawn-based path: guard requires at least one adapter.
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY

    if not ADAPTER_REGISTRY:
        _print_err(
            "no LLM clients configured — see docs/MODELS.md to register a client"
        )
        return 3

    effective_llm = llm or next(iter(ADAPTER_REGISTRY), "claude-code")

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
    parser.add_argument(
        "--no-spawn",
        action="store_true",
        dest="in_process",
        default=False,
        help=(
            "Run the reviewer in-process (no cmux spawn). "
            "Calls the registered LLM client directly; writes --report-file "
            "synchronously. Required on CI runners without a multiplexer."
        ),
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        dest="in_process",
        help="Alias for --no-spawn.",
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
        in_process=ns.in_process,
    )

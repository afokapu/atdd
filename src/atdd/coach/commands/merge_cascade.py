"""
`atdd merge-cascade` — wave-ordered PR merger.

For each PR in the supplied order:
    1. update-branch against target
    2. poll CI until all required checks pass
    3. merge via `gh pr merge`

Halts on conflict with a structured report of the offending PR.

SPEC IDs: SPEC-COACH-ORCH-0006, SPEC-COACH-ORCH-0007
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class MergeResult:
    pr: int
    status: str  # "merged" | "ci_failed" | "conflict" | "timeout" | "skipped"
    detail: str = ""


class MergeHalt(RuntimeError):
    def __init__(self, result: MergeResult):
        super().__init__(f"merge halted on PR #{result.pr}: {result.status} — {result.detail}")
        self.result = result


def _run_gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        check=check,
        capture_output=True,
        text=True,
    )


def update_branch(pr: int) -> MergeResult:
    """Run `gh pr update-branch <pr>`. Returns conflict result if git says so."""
    try:
        _run_gh(["pr", "update-branch", str(pr)])
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").lower()
        if "conflict" in stderr or "merge conflict" in stderr:
            return MergeResult(pr=pr, status="conflict", detail=exc.stderr.strip())
        return MergeResult(pr=pr, status="conflict", detail=f"update-branch failed: {exc.stderr.strip()}")
    return MergeResult(pr=pr, status="merged", detail="update-branch ok")


def fetch_ci_status(pr: int) -> tuple[str, str]:
    """Return (overall_state, detail).

    overall_state ∈ {'pass', 'fail', 'pending', 'unknown'}.
    """
    try:
        result = _run_gh([
            "pr", "checks", str(pr), "--required", "--json", "state,name,conclusion",
        ])
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "")
        if "no required" in stderr.lower() or "no checks" in stderr.lower():
            return "pass", "no required checks"
        return "unknown", stderr.strip()
    try:
        checks = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return "unknown", f"unparseable: {result.stdout[:100]}"
    if not checks:
        return "pass", "no required checks"
    states = [(c.get("state") or "").upper() for c in checks]
    conclusions = [(c.get("conclusion") or "").upper() for c in checks]
    if any(s in {"IN_PROGRESS", "QUEUED", "PENDING"} for s in states):
        return "pending", f"{sum(s == 'IN_PROGRESS' for s in states)} in progress"
    failed = [
        c["name"]
        for c, con in zip(checks, conclusions)
        if con in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}
    ]
    if failed:
        return "fail", f"failed: {', '.join(failed)}"
    return "pass", f"{len(checks)} check(s) passed"


def wait_for_ci(
    pr: int,
    poll_interval: int = 30,
    timeout: int = 1800,
    sleep=time.sleep,
    clock=time.time,
) -> MergeResult:
    """Poll CI until it passes, fails, or the timeout is reached."""
    start = clock()
    while True:
        state, detail = fetch_ci_status(pr)
        if state == "pass":
            return MergeResult(pr=pr, status="merged", detail=f"CI green — {detail}")
        if state == "fail":
            return MergeResult(pr=pr, status="ci_failed", detail=detail)
        if clock() - start >= timeout:
            return MergeResult(pr=pr, status="timeout", detail=f"no CI result after {timeout}s")
        sleep(poll_interval)


def merge_pr(pr: int) -> MergeResult:
    try:
        _run_gh(["pr", "merge", str(pr), "--squash", "--delete-branch"])
    except subprocess.CalledProcessError as exc:
        return MergeResult(pr=pr, status="conflict", detail=f"merge failed: {exc.stderr.strip()}")
    return MergeResult(pr=pr, status="merged", detail="squash-merged")


def cascade(
    pr_numbers: list[int],
    poll_interval: int = 30,
    timeout: int = 1800,
    auto: bool = False,
) -> list[MergeResult]:
    """Run the full update-branch → wait CI → merge loop for each PR in order.

    Halts on the first non-merged result.
    """
    results: list[MergeResult] = []
    for pr in pr_numbers:
        print(f"▶ PR #{pr}: update-branch")
        ub = update_branch(pr)
        if ub.status != "merged":
            results.append(ub)
            raise MergeHalt(ub)

        print(f"▶ PR #{pr}: waiting for CI")
        ci = wait_for_ci(pr, poll_interval=poll_interval, timeout=timeout)
        if ci.status != "merged":
            results.append(ci)
            raise MergeHalt(ci)

        if not auto:
            print(f"▶ PR #{pr}: merge? [y/N] ", end="", flush=True)
            try:
                answer = input().strip().lower()
            except EOFError:
                answer = ""
            if answer not in {"y", "yes"}:
                results.append(MergeResult(pr=pr, status="skipped", detail="user declined"))
                raise MergeHalt(results[-1])

        print(f"▶ PR #{pr}: merging")
        merged = merge_pr(pr)
        results.append(merged)
        if merged.status != "merged":
            raise MergeHalt(merged)
    return results


def run(
    pr_numbers: list[int],
    auto: bool = False,
    poll_interval: int = 30,
    timeout: int = 1800,
    dry_run: bool = False,
) -> int:
    if dry_run:
        print(f"Merge plan ({len(pr_numbers)} PR(s)):")
        for i, pr in enumerate(pr_numbers):
            print(f"  {i+1:>2}. #{pr}")
        return 0
    try:
        results = cascade(
            pr_numbers,
            poll_interval=poll_interval,
            timeout=timeout,
            auto=auto,
        )
    except MergeHalt as halt:
        r = halt.result
        print(f"\n❌ halted on PR #{r.pr} ({r.status}): {r.detail}", file=sys.stderr)
        return 1
    print(f"\n✓ merged {len(results)} PR(s) in order")
    return 0

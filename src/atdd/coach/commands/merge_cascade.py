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
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from atdd.coach.commands.merge_cascade_pyproject import (
    resolve_pyproject_version_conflict,
)
from atdd.coach.commands.merge_cascade_topology import (
    MergeCascadeCycleError,
    compute_merge_order,
)


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


_CONFLICT_FILE_RE = re.compile(r"(?:merge\s+)?conflict\s+in\s+(\S+)", re.IGNORECASE)


def classify_conflict(stderr: str) -> str:
    """Classify a conflict ``stderr`` blob.

    Returns:
        ``"pyproject_only"`` if every conflicting file is ``pyproject.toml``,
        ``"other"`` if any non-pyproject file is involved,
        ``"unknown"`` if no conflict markers are present at all.
    """
    files = [m.group(1) for m in _CONFLICT_FILE_RE.finditer(stderr or "")]
    if not files:
        return "unknown"
    return "pyproject_only" if all(f == "pyproject.toml" for f in files) else "other"


def attempt_pyproject_resolve(pr: int) -> bool:
    """Locally resolve a pyproject.toml version conflict on ``pr`` and push.

    Steps: fetch PR branch → checkout → merge target → resolve via
    :func:`resolve_pyproject_version_conflict` → commit → push.

    Returns ``True`` on success, ``False`` if the resolver could not produce
    a clean output or any git operation failed.
    """
    import os
    import tempfile

    try:
        view = _run_gh(["pr", "view", str(pr), "--json", "headRefName,baseRefName"])
    except subprocess.CalledProcessError:  # atdd:suppress(coder.logging.coach-silent-swallow)
        return False
    try:
        meta = json.loads(view.stdout or "{}")
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow)
        return False
    head = meta.get("headRefName")
    base = meta.get("baseRefName") or "main"
    if not head:
        return False

    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True
        )

    try:
        _git("fetch", "origin", head, base)
        _git("checkout", head)
        _git("pull", "--ff-only", "origin", head)
        merge = subprocess.run(
            ["git", "merge", "--no-edit", f"origin/{base}"],
            capture_output=True,
            text=True,
        )
        if merge.returncode != 0:
            pyproject_path = "pyproject.toml"
            if not os.path.exists(pyproject_path):
                _git("merge", "--abort")
                return False
            with open(pyproject_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            resolved = resolve_pyproject_version_conflict(content)
            if resolved is None:
                _git("merge", "--abort")
                return False
            with open(pyproject_path, "w", encoding="utf-8") as fh:
                fh.write(resolved)
            _git("add", pyproject_path)
            _git("commit", "--no-edit")
        _git("push", "origin", head)
        return True
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        print(
            f"⚠ pyproject auto-resolve failed for PR #{pr}: "
            f"{exc.cmd!r} → {(exc.stderr or '').strip()}",
            file=sys.stderr,
        )
        # Best-effort cleanup; failure here means there was no merge in progress.
        subprocess.run(
            ["git", "merge", "--abort"], capture_output=True, check=False
        )
        return False


def fetch_pr_files(pr: int) -> set[str]:
    """Return the set of file paths changed by ``pr``. Empty set on any error.

    A 404 / network failure here yields an empty set, so the topology engine
    treats the PR as having no overlap (it falls to PR-number tie-break).
    """
    try:
        result = _run_gh(["pr", "view", str(pr), "--json", "files"])
    except subprocess.CalledProcessError:  # atdd:suppress(coder.logging.coach-silent-swallow)
        return set()
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow)
        return set()
    return {entry["path"] for entry in data.get("files") or [] if entry.get("path")}


def _print_dry_run_plan(order: list[int], files_by_pr: dict[int, set[str]]) -> None:
    """Print the planned merge sequence with conflict-resolution hints."""
    print(f"Planned sequence (topological, {len(order)} PR(s)):")
    merged_files: set[str] = set()
    for wave_index, pr in enumerate(order):
        files = files_by_pr.get(pr, set())
        overlap = sorted(files & merged_files)
        if wave_index == 0 or not overlap:
            hint = "no deps" if wave_index == 0 else "independent"
            print(f"  Wave {wave_index}: #{pr} ({hint})")
        else:
            print(
                f"  Wave {wave_index}: #{pr} "
                f"(rebase on prior; resolve: {', '.join(overlap)})"
            )
        merged_files.update(files)
    print("No cycles detected.")


def update_branch(pr: int) -> MergeResult:
    """Run `gh pr update-branch <pr>`. Returns conflict result if git says so."""
    try:
        _run_gh(["pr", "update-branch", str(pr)])
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        stderr = (exc.stderr or "")
        if "no required" in stderr.lower() or "no checks" in stderr.lower():
            return "pass", "no required checks"
        return "unknown", stderr.strip()
    try:
        checks = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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
            if classify_conflict(ub.detail) == "pyproject_only":
                print(f"▶ PR #{pr}: pyproject conflict — auto-resolving")
                if attempt_pyproject_resolve(pr):
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


def _resolve_order(pr_numbers: list[int]) -> tuple[list[int], dict[int, set[str]]]:
    """Compute topological merge order. Caller handles MergeCascadeCycleError."""
    files_by_pr = {pr: fetch_pr_files(pr) for pr in pr_numbers}
    order = compute_merge_order(pr_numbers, lambda pr: files_by_pr[pr])
    return order, files_by_pr


def run(
    pr_numbers: list[int],
    auto: bool = False,
    poll_interval: int = 30,
    timeout: int = 1800,
    dry_run: bool = False,
) -> int:
    try:
        order, files_by_pr = _resolve_order(pr_numbers)
    except MergeCascadeCycleError as cyc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        path_str = " → ".join(f"#{n}" for n in cyc.cycle_path)
        print(
            f"\n❌ cycle detected in merge cascade: {path_str}",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        _print_dry_run_plan(order, files_by_pr)
        return 0

    try:
        results = cascade(
            order,
            poll_interval=poll_interval,
            timeout=timeout,
            auto=auto,
        )
    except MergeHalt as halt:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        r = halt.result
        print(f"\n❌ halted on PR #{r.pr} ({r.status}): {r.detail}", file=sys.stderr)
        return 1
    print(f"\n✓ merged {len(results)} PR(s) in topological order")
    return 0

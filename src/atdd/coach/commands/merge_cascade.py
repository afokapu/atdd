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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from atdd.coach.commands.merge_cascade_pyproject import (
    resolve_pyproject_version_conflict,
)
from atdd.coach.commands.merge_cascade_topology import (
    MergeCascadeCycleError,
    compute_merge_order,
)
from atdd.coach.utils.default_branch import resolve_default_branch
from atdd.coach.utils.ff_default_branch import fast_forward_default_branch


@dataclass
class MergeResult:
    pr: int
    # "merged" | "ci_failed" | "ci_error" | "conflict" | "timeout" | "skipped"
    # "ci_error": the CI read itself failed terminally — see fetch_ci_status.
    status: str
    detail: str = ""


class MergeHalt(RuntimeError):
    def __init__(self, result: MergeResult):
        super().__init__(f"merge halted on PR #{result.pr}: {result.status} — {result.detail}")
        self.result = result


@dataclass
class OrphanScreen:
    """Outcome of the pre-merge graph orphan check (#656).

    ``blocked`` is True when merging the screened tree would leave a declared
    URN with no resolving artifact; ``orphaned_urns`` names those URNs and
    ``escalation`` is a human-readable message naming them.
    """
    blocked: bool
    orphaned_urns: list[str] = field(default_factory=list)
    escalation: Optional[str] = None


def screen_merge_for_orphans(repo_root: Path) -> OrphanScreen:
    """Pre-merge graph check: would the merged tree orphan a URN? (#656)

    Walks ``plan/<wagon>/_<wagon>.yaml`` and, for every declared feature URN,
    verifies a resolving artifact exists under ``plan/<wagon>/features/``.
    A declared feature URN with no matching feature file is an orphan: the
    merge is blocked and an escalation naming the URN is returned.
    """
    plan_dir = Path(repo_root) / "plan"
    orphaned: list[str] = []
    if plan_dir.is_dir():
        for wagon_yaml in sorted(plan_dir.glob("*/_*.yaml")):
            data = yaml.safe_load(wagon_yaml.read_text()) or {}
            if not isinstance(data, dict):
                continue
            resolved: set[str] = set()
            features_dir = wagon_yaml.parent / "features"
            if features_dir.is_dir():
                for feature_file in features_dir.glob("*.yaml"):
                    fdata = yaml.safe_load(feature_file.read_text()) or {}
                    if isinstance(fdata, dict) and fdata.get("urn"):
                        resolved.add(str(fdata["urn"]))
            for feature in data.get("features") or []:
                urn = feature.get("urn") if isinstance(feature, dict) else None
                if urn and str(urn) not in resolved:
                    orphaned.append(str(urn))

    if not orphaned:
        return OrphanScreen(blocked=False)
    escalation = (
        "merge blocked — would orphan declared URN(s): "
        + ", ".join(sorted(orphaned))
    )
    return OrphanScreen(
        blocked=True, orphaned_urns=orphaned, escalation=escalation
    )


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
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
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
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        stderr = (exc.stderr or "").lower()
        if "conflict" in stderr or "merge conflict" in stderr:
            return MergeResult(pr=pr, status="conflict", detail=exc.stderr.strip())
        return MergeResult(pr=pr, status="conflict", detail=f"update-branch failed: {exc.stderr.strip()}")
    return MergeResult(pr=pr, status="merged", detail="update-branch ok")


# The `--json` field list sent to `gh pr checks`. Every name here must be one
# the installed gh advertises — gh exits 1 and returns nothing for any field it
# does not know, and that refusal is indistinguishable from a pending check
# unless it is classified as terminal (see `wait_for_ci`). `conclusion` used to
# be on this list; gh does not serve it on `pr checks`, and `bucket` is its
# successor. acc:coach-ops:M003-SMOKE-001 pins the list against a live gh.
_CI_CHECK_FIELDS = "name,bucket,state"

# gh reports "no required checks" as a non-zero exit. That is not a fault.
_BENIGN_STDERR_PHRASES = ("no required", "no checks")


def fetch_ci_status(pr: int) -> tuple[str, str]:
    """Return (overall_state, detail).

    overall_state ∈ {'pass', 'fail', 'pending', 'error'}.

    Only 'pending' is worth retrying. 'error' is TERMINAL — the read failed for
    a reason no amount of waiting changes (a field gh refuses, a dead
    credential, a pull request that does not exist, a payload that is not JSON).
    It replaces the old 'unknown', which `wait_for_ci` neither passed nor failed
    on and therefore polled to the timeout.

    The verdict comes from each check's `bucket`, which is gh's own summary:
    pass / fail / pending / skipping / cancel. Only `fail` fails and only
    `pending` waits — a skipped or cancelled required check does not halt a
    cascade GitHub itself treats as satisfiable. `state` rides along in the
    detail as corroboration for whoever reads the transcript.
    """
    try:
        result = _run_gh([
            "pr", "checks", str(pr), "--required", "--json", _CI_CHECK_FIELDS,
        ])
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        stderr = (exc.stderr or "")
        if any(phrase in stderr.lower() for phrase in _BENIGN_STDERR_PHRASES):
            return "pass", "no required checks"
        return "error", stderr.strip()
    try:
        checks = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        return "error", f"unparseable gh output: {(result.stdout or '')[:200]}"
    if not checks:
        return "pass", "no required checks"
    buckets = [(c.get("bucket") or "").lower() for c in checks]
    pending = sum(bucket == "pending" for bucket in buckets)
    if pending:
        return "pending", f"{pending} in progress"
    failed = [
        f"{c.get('name') or '?'} ({(c.get('state') or '?').upper()})"
        for c, bucket in zip(checks, buckets)
        if bucket == "fail"
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
    """Poll CI until it passes, fails, errors terminally, or the timeout is reached.

    Only a genuinely in-flight check keeps the loop alive. A terminal read error
    ends the wait on the spot carrying gh's own stderr, so a permanent fault is
    reported as itself rather than spent as a timeout (#1612).
    """
    start = clock()
    while True:
        state, detail = fetch_ci_status(pr)
        if state == "pass":
            return MergeResult(pr=pr, status="merged", detail=f"CI green — {detail}")
        if state == "fail":
            return MergeResult(pr=pr, status="ci_failed", detail=detail)
        if state == "error":
            return MergeResult(pr=pr, status="ci_error", detail=f"CI read failed: {detail}")
        if clock() - start >= timeout:
            return MergeResult(pr=pr, status="timeout", detail=f"no CI result after {timeout}s")
        sleep(poll_interval)


def merge_pr(pr: int) -> MergeResult:
    try:
        _run_gh(["pr", "merge", str(pr), "--squash", "--delete-branch"])
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
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

        # Fast-forward the local default-branch worktree after each merge (#770).
        repo_root = Path.cwd()
        default_branch = resolve_default_branch(repo_root)
        fast_forward_default_branch(repo_root, default_branch)

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
    except MergeCascadeCycleError as cyc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
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
    except MergeHalt as halt:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        r = halt.result
        print(f"\n❌ halted on PR #{r.pr} ({r.status}): {r.detail}", file=sys.stderr)
        return 1
    print(f"\n✓ merged {len(results)} PR(s) in topological order")
    return 0

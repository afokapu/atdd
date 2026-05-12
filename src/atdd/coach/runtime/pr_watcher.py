"""Rate-limit-aware batched PR watcher for coach runtime.

Design:
- poll() issues ONE gh pr list call for all requested PRs (never per-PR).
- failures() is the ONLY path that fetches statusCheckRollup (expensive).
- wait_any() blocks until any PR reaches the target mergeStateStatus.
- PRWatcher class carries per-instance backoff state and budget-warning flag.

Backoff sequence on secondary rate-limit (403 abuse):
  1st failure → 600s sleep
  2nd failure → 1200s sleep
  Recovery: reset to normal interval on next success

Pre-flight: gh api rate_limit is checked before each poll cycle.
Cycles are skipped when < BUDGET_THRESHOLD (500) graphql points remain.
The low-budget warning is emitted at most once per PRWatcher instance to
avoid spam when the budget stays low for multiple cycles.

Default poll interval: 180s (configurable via .atdd/config.yaml
  coach.pr_watcher_interval_seconds, min 60).

Usage::

    from atdd.coach.runtime.pr_watcher import poll, failures, wait_any

    # Functional API (no state between calls — suitable for one-shot use)
    states = poll(prs=[101, 102, 103])
    broken = failures(pr=101)

    # Stateful API (carries backoff + budget-warning state across calls)
    watcher = PRWatcher(repo="owner/repo", poll_interval=180)
    states = watcher.poll(prs=[101, 102, 103])
    pr_number = watcher.wait_any(prs=[101, 102, 103], target_state="CLEAN")
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

BUDGET_THRESHOLD = 500
_BACKOFF_STEPS = [600, 1200]
_SECONDARY_LIMIT_MARKERS = ("secondary rate limit", "abuse", "403")


@dataclass
class PRWatcher:
    repo: str = "afokapu/atdd"
    poll_interval: int = 180
    _backoff_index: int = field(default=0, init=False, repr=False)
    _budget_warned: bool = field(default=False, init=False, repr=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def poll(self, prs: list[int]) -> dict[int, str]:
        """Fetch mergeStateStatus for all PRs in a single gh pr list call.

        Returns {} (empty dict) if the rate-limit budget is below threshold.
        Sleeps and retries (with exponential backoff) on 403-abuse errors.
        """
        remaining = self._check_budget()
        if remaining is not None and remaining < BUDGET_THRESHOLD:
            if not self._budget_warned:
                print(
                    f"[pr_watcher] rate limit budget low ({remaining} graphql points remaining) "
                    "— skipping poll cycle.",
                    file=sys.stderr,
                )
                self._budget_warned = True
            return {}

        result = self._run_pr_list(prs)
        if result is None:
            return {}
        self._backoff_index = 0
        self._budget_warned = False
        return result

    def wait_any(
        self,
        prs: list[int],
        target_state: str = "CLEAN",
    ) -> Optional[int]:
        """Block until any PR in *prs* reaches *target_state*.

        Returns the PR number of the first match.
        Polls every self.poll_interval seconds.
        """
        while True:
            states = self.poll(prs=prs)
            for pr, state in states.items():
                if state == target_state:
                    return pr
            time.sleep(self.poll_interval)

    def failures(self, pr: int) -> list[str]:
        """Fetch failing check names for a single PR via statusCheckRollup.

        This is the ONLY method that fetches statusCheckRollup — it is
        intentionally expensive and must only be called for diagnostics.
        """
        return _run_failures(pr=pr, repo=self.repo)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_budget(self) -> Optional[int]:
        cmd = ["gh", "api", "rate_limit"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return None
            data = json.loads(r.stdout)
            return data["resources"]["graphql"]["remaining"]
        except Exception:
            return None

    def _run_pr_list(self, prs: list[int]) -> Optional[dict[int, str]]:
        cmd = [
            "gh", "pr", "list",
            "--repo", self.repo,
            "--state", "open",
            "--limit", "100",
            "--json", "number,mergeStateStatus",
        ]
        while True:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                items = json.loads(r.stdout)
                pr_set = set(prs) if prs else None
                return {
                    item["number"]: item["mergeStateStatus"]
                    for item in items
                    if pr_set is None or item["number"] in pr_set
                }
            stderr = r.stderr or ""
            if any(m in stderr.lower() for m in _SECONDARY_LIMIT_MARKERS):
                if self._backoff_index < len(_BACKOFF_STEPS):
                    delay = _BACKOFF_STEPS[self._backoff_index]
                    self._backoff_index += 1
                    print(
                        f"[pr_watcher] secondary rate limit hit; backing off {delay}s",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                    continue
                # Max backoff reached — return None to signal failure
                return None
            # Non-rate-limit error — return None
            return None


# ---------------------------------------------------------------------------
# Module-level functional API (convenience wrappers over a default instance)
# ---------------------------------------------------------------------------

_default_watcher: Optional[PRWatcher] = None


def _get_default() -> PRWatcher:
    global _default_watcher
    if _default_watcher is None:
        _default_watcher = PRWatcher()
    return _default_watcher


def poll(prs: list[int], *, repo: str = "afokapu/atdd") -> dict[int, str]:
    """One-shot batched poll — functional API without persistent backoff state."""
    w = PRWatcher(repo=repo)
    return w.poll(prs=prs)


def failures(pr: int, *, repo: str = "afokapu/atdd") -> list[str]:
    """Return failing check names for a single PR (fetches statusCheckRollup)."""
    return _run_failures(pr=pr, repo=repo)


def wait_any(
    prs: list[int],
    target_state: str = "CLEAN",
    *,
    repo: str = "afokapu/atdd",
    poll_interval: int = 180,
) -> Optional[int]:
    """Block until any PR reaches target_state; return its PR number."""
    w = PRWatcher(repo=repo, poll_interval=poll_interval)
    return w.wait_any(prs=prs, target_state=target_state)


def _run_failures(pr: int, repo: str) -> list[str]:
    cmd = [
        "gh", "pr", "view", str(pr),
        "--repo", repo,
        "--json", "statusCheckRollup",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return []
    data = json.loads(r.stdout)
    rollup = data.get("statusCheckRollup") or []
    return [
        item["name"]
        for item in rollup
        if item.get("conclusion") == "FAILURE"
    ]

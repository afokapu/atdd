"""``FakeGitHub`` — in-memory stand-in for the GitHub integration layer.

Models exactly what the lifecycle parity test observes: issue labels, the PR
state for an issue, and the Projects v2 Status field. ``set_phase`` performs the
atomic label-swap + Projects-v2 sync that the real
``integrations.github.issue_state.transition_phase`` will own (§4.10, closes
#882) — modelling the atomicity here lets the parity test assert the board stays
in lock-step with the label, which is the #882 regression guard.

No network, no ``gh`` subprocess: this is the Child-2 dry-run double. The real
adapter ships in Child 4.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atdd.coach.core.types import IssueType, Phase

ISSUE_LABEL = "atdd-issue"


@dataclass
class FakeIssue:
    number: int
    slug: str
    type: IssueType
    labels: set[str] = field(default_factory=set)


@dataclass
class FakePr:
    number: int
    issue_number: int
    state: str = "OPEN"  # OPEN | MERGED | CLOSED


class FakeGitHub:
    """In-memory GitHub double. Single source for issue/PR/board state."""

    def __init__(self) -> None:
        self._issues: dict[int, FakeIssue] = {}
        self._prs: dict[int, FakePr] = {}
        self._project_status: dict[int, str] = {}
        self._next_issue = 816
        self._next_pr = 1000

    # --- issues ---------------------------------------------------------- #
    def create_issue(self, *, slug: str, type: IssueType) -> FakeIssue:
        number = self._next_issue
        self._next_issue += 1
        issue = FakeIssue(
            number=number,
            slug=slug,
            type=type,
            labels={ISSUE_LABEL, f"atdd:{Phase.INIT.value}"},
        )
        self._issues[number] = issue
        self._project_status[number] = Phase.INIT.value
        return issue

    def issue(self, number: int) -> FakeIssue:
        return self._issues[number]

    def set_phase(self, number: int, phase: Phase) -> None:
        """Atomic label swap + Projects v2 status sync (§4.10, closes #882)."""
        issue = self._issues[number]
        issue.labels = {label for label in issue.labels if not label.startswith("atdd:")}
        issue.labels.add(f"atdd:{phase.value}")
        # Same call site updates the board — they can never drift (the #882 fix).
        self._project_status[number] = phase.value

    def project_v2_status(self, number: int) -> str:
        return self._project_status[number]

    # --- pull requests --------------------------------------------------- #
    def open_pr(self, issue_number: int) -> FakePr:
        number = self._next_pr
        self._next_pr += 1
        pr = FakePr(number=number, issue_number=issue_number, state="OPEN")
        self._prs[issue_number] = pr
        return pr

    def pr_for(self, issue_number: int) -> FakePr | None:
        return self._prs.get(issue_number)

    def merge_pr(self, issue_number: int) -> FakePr:
        pr = self._prs[issue_number]
        pr.state = "MERGED"
        return pr

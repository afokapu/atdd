"""``FakeGitHub`` — in-memory stand-in for the GitHub integration layer.

Models exactly what the lifecycle parity test observes: issue labels and the PR
state for an issue. ``set_phase`` swaps the ``atdd:<phase>`` label, matching what
``integrations.github.issue_state.transition_phase`` does.

It used to model a Projects v2 Status field too, and the parity test asserted
the board stayed in lock-step with the label — the #882 guard. #1051
decommissioned that board and #1761 removed its last writers, so the double
stopped standing in for anything real; a fake that models a system nobody talks
to only proves the fake works.

No network, no ``gh`` subprocess.
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
        return issue

    def issue(self, number: int) -> FakeIssue:
        return self._issues[number]

    def set_phase(self, number: int, phase: Phase) -> None:
        """Swap the ``atdd:<phase>`` label — the whole of the phase projection."""
        issue = self._issues[number]
        issue.labels = {label for label in issue.labels if not label.startswith("atdd:")}
        issue.labels.add(f"atdd:{phase.value}")

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

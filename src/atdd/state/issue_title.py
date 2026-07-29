# Component: component:author-atdd-substrate:author-issue-body:IssueTitle:backend:domain
"""The issue title and the body's H1, read as ONE fact (#1654).

A work item carries its title twice: in ``data.title`` and as the leading H1 of
``data.body``. They are two representations of the same thing, so any path that
writes one must write the other — and something has to be able to say, of a
record already written, whether they agree.

WHY THIS LIVES IN ``atdd.state``
    Both title-writing paths need it and they sit on opposite sides of a
    boundary: ``atdd.planner``'s ``author issue --revise`` (#1654) and
    ``atdd.state.work_item_writer.rename_work_item`` (#1653). ``work_item_writer``
    is forbidden from importing ``atdd.planner`` — that is the reverse of the
    dependency it exists to serve — so a planner-side extractor would have
    forced #1653 to keep a private copy. Two independently-written H1 parsers
    that disagree would reproduce, one layer down, the very defect this module
    closes: one fact with two representations and nothing binding them. So it
    lives in the foundational layer both consume, and planner re-exports it.

    Dependency discipline: stdlib only. Nothing here knows what a provider is —
    it parses markdown and compares two strings.

WHY THE FENCE TRACKING IS NOT OPTIONAL
    A body that quotes ``# atdd author issue --revise …`` inside a fenced block
    has not declared a title. Reading it as one is not a hypothetical: scanning
    the 822-work-item Control Root store with a fence-blind regex accused 105
    records; the fence-aware scan below finds 24 (surveyed 2026-07-29).
"""
from __future__ import annotations

import re
from typing import List, Optional

#: A fenced-code delimiter — three or more backticks or tildes, up to three
#: leading spaces (CommonMark). The opening marker's CHARACTER is remembered so
#: a tilde line cannot close a backtick fence, and vice versa.
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

#: An ATX H1: a single ``#`` followed by whitespace and the title text.
_H1_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$")


def extract_issue_title(body: str) -> Optional[str]:
    """Return ``body``'s leading H1 — the declared title — or ``None``.

    Scanned line-wise rather than by a multiline regex because fenced code has
    to be tracked ACROSS lines. A fence opened with backticks is closed only by
    backticks (likewise tildes), so a body that nests one fence style inside
    another is not truncated at the wrong place. An unterminated fence swallows
    the remainder of the document: the conservative reading, since the only
    alternative is to credit a code sample with naming the issue.

    ``None`` means *undeclared*, never *empty* — :func:`title_violations`
    depends on that distinction to skip rather than accuse.
    """
    fence: Optional[str] = None
    for line in (body or "").splitlines():
        marker = _FENCE_RE.match(line)
        if marker:
            token = marker.group(1)[0]
            if fence is None:
                fence = token
            elif fence == token:
                fence = None
            continue
        if fence is not None:
            continue
        m = _H1_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def title_violations(title: Optional[str], body: str) -> List[str]:
    """Violations when ``title`` and ``body``'s H1 state different things.

    The predicate is deliberately severity-neutral: it reports, and the caller
    decides how loudly to react. The coach store-mirror gate blocks on the work
    item bound to the branch being pushed and counts the rest as an advisory,
    because 24 pre-existing disagreements must not red-gate every branch.

    A body with **no H1 is skipped, not failed**. 619 of the 822 work items in
    the Control Root store carry none, legitimately — failing them would
    red-line three quarters of the corpus on day one and the check would be
    switched off within the week. Absence is not disagreement, and synthesising
    H1s into those 619 is a corpus migration, not a check.

    ``None`` is symmetric with the H1 side: it means *undeclared*, and an
    undeclared title cannot contradict anything, so it is skipped too. An
    explicitly EMPTY title (``""``) is a different claim — the record states it
    has no title while its body states one — and that IS a disagreement.

    Comparison is on stripped text: trailing whitespace is a typo, not a
    contradiction.
    """
    h1 = extract_issue_title(body)
    if h1 is None:
        return []
    if title is None:
        return []
    stored = title.strip()
    if stored == h1.strip():
        return []
    return [
        f"stored title {stored!r} disagrees with the body H1 {h1!r} "
        f"(one fact, two representations — see #1654)"
    ]


__all__ = ["extract_issue_title", "title_violations"]

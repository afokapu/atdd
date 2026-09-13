# URN: component:govern-lifecycle:issue-fetch-separates-absent-from-unavailable:gh_failure:backend:domain
# Runtime: python
# Purpose: Tell "there is no such issue" apart from "GitHub would not answer", so a refusal names the right cause (#1895).

"""Why a `gh` call failed — an ANSWER, or no answer at all.

`gh issue view` exits 1 for both "that issue does not exist" and "the API
declined to talk to you", and the callers here collapsed both into `None`. The
operator then read `could not fetch issue #1876` and went looking for a missing
issue that was sitting there, open, perfectly fine — while the actual cause was a
rate limit that would clear on its own.

Only ONE of these outcomes is an answer. "No such issue" is a fact about the
repository. Everything else is the absence of a fact, and the two must not print
the same sentence.

Every pattern below was captured from a real failure, not composed:
`gh issue view 99999999` and a live rate-limited call, both against this
repository during the session that filed #1895.

This module does not decide what to DO. Callers still refuse — an unestablished
verdict blocks, exactly as `coach.documentation.verdict` treats COULD_NOT_CHECK.
What changes is that the refusal names a cause the operator can act on.
"""
from __future__ import annotations

from typing import NamedTuple

ABSENT = "ABSENT"                 # an answer: the issue is not there
UNAVAILABLE = "UNAVAILABLE"       # no answer: the API would not say
MALFORMED = "MALFORMED"           # exit 0 but the payload was not usable


class GhVerdict(NamedTuple):
    """What a failed `gh` invocation established, and what to tell the operator."""

    kind: str
    established: bool   # True only when the call actually answered the question
    detail: str
    remedy: str


# Ordered: the first match wins, so the specific rate-limit strings are tested
# before the generic ones they contain.
_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("could not resolve to an issue", ABSENT,
     "no issue or pull request with that number exists in this repository",
     "Check the number. `atdd coach issues open` lists what is there."),
    # The REST spelling of the line above (#1989). `gh issue view` said "could
    # not resolve to an issue"; `gh api repos/<repo>/issues/<n>` says
    # "gh: Not Found (HTTP 404)". Without this the reads moved to REST would
    # classify a missing issue as UNRECOGNISED — which is UNAVAILABLE, so the
    # refusal would stop offering a remedy and start saying "treat it as
    # unknown" about an issue GitHub had positively answered about.
    #
    # 404 is honest as ABSENT *on this path*: GitHub also returns 404 for a
    # repository the credential cannot see, but every other call would be
    # failing too in that case, and the alternative — never claiming absence
    # over REST — loses the one distinction this module exists to draw.
    ("not found (http 404)", ABSENT,
     "no issue or pull request with that number exists in this repository",
     "Check the number. `atdd coach issues open` lists what is there."),
    ("secondary rate limit", UNAVAILABLE,
     "GitHub applied a secondary rate limit, so it did not answer",
     "Wait a few minutes and retry. Nothing about the issue is known yet."),
    ("rate limit", UNAVAILABLE,
     "the GitHub API rate limit is exhausted, so it did not answer",
     "Check `gh api rate_limit --jq .resources` for the reset time, then retry. "
     "Note the REST and GraphQL buckets are separate: one can be exhausted while "
     "the other reports full."),
    ("gh_token", UNAVAILABLE,
     "the GitHub CLI has no credential, so it did not answer",
     "Run `gh auth login`, or set GH_TOKEN in this environment."),
    ("authentication", UNAVAILABLE,
     "the GitHub CLI could not authenticate, so it did not answer",
     "Run `gh auth status` to see which host is failing."),
    ("no such host", UNAVAILABLE,
     "the GitHub API was unreachable, so it did not answer",
     "Check network connectivity, then retry."),
    ("dial tcp", UNAVAILABLE,
     "the GitHub API was unreachable, so it did not answer",
     "Check network connectivity, then retry."),
    ("connection refused", UNAVAILABLE,
     "the GitHub API refused the connection, so it did not answer",
     "Check network connectivity or a proxy, then retry."),
    ("something went wrong while executing your query", UNAVAILABLE,
     "GitHub returned a server error, so it did not answer",
     "Retry; if it persists, check https://www.githubstatus.com."),
)

_UNKNOWN = GhVerdict(
    UNAVAILABLE,
    False,
    "the GitHub CLI failed for a reason this does not recognise, so nothing about "
    "the issue was established",
    "The CLI's own output is above. Treat it as unknown, not as absent.",
)


def classify(stderr: str, returncode: int = 1) -> GhVerdict:
    """Classify a failed `gh issue view`.

    An UNRECOGNISED failure is UNAVAILABLE, never ABSENT. Guessing "the issue
    does not exist" from a message this module has not seen would reintroduce the
    exact conflation it exists to remove, and would do it silently.
    """
    haystack = (stderr or "").lower()
    for needle, kind, detail, remedy in _PATTERNS:
        if needle in haystack:
            return GhVerdict(kind, kind == ABSENT, detail, remedy)
    return _UNKNOWN


def malformed(payload: str) -> GhVerdict:
    """`gh` exited 0 but the payload did not parse.

    Distinct from UNAVAILABLE: the call succeeded, so retrying will not help, and
    distinct from ABSENT, because nothing said the issue is missing.
    """
    preview = (payload or "").strip()[:120]
    return GhVerdict(
        MALFORMED,
        False,
        f"the GitHub CLI exited 0 but its output did not parse as JSON: {preview!r}",
        "Check the installed `gh` version; the --json contract may have changed.",
    )


def render(issue_number: int, verdict: GhVerdict, needed_for: str = "") -> str:
    """The operator-facing explanation, phrased so it cannot assert absence.

    The cause leads and the remedy trails, so the first line is the sentence the
    operator will act on. `needed_for` rides on that first line rather than after
    the remedy, where it read as part of the fix.
    """
    lead = "does not exist" if verdict.established else "could not be read"
    context = f" (needed {needed_for})" if needed_for else ""
    return (
        f"issue #{issue_number} {lead}{context}: {verdict.detail}\n"
        f"  {verdict.remedy}"
    )

"""Evidence gathering for ``atdd coach reconcile-state`` (#1338).

Split out of ``issue_reconcile_state`` so the classification core stays a
readable module and this GitHub-facing boundary can be stubbed wholesale in a
test. Deliberately imports NOTHING from the core — the dependency runs one way
(core → evidence), so there is no cycle to unpick later.

WHAT COUNTS AS EVIDENCE
    A repair verb must decide the *true* phase of a record whose label lies. The
    honest inventory is short:

    - ``objects.state`` — the trustworthy floor; read by the core, not here.
    - **closed by a merged PR** — the only proof the work actually landed. That
      is what this module fetches.
    - the ``atdd:<PHASE>`` label — read here, but SUSPECT: it is the corrupted
      artifact, the input to the bug, not evidence about the work.

    The ``events`` table is absent from that list on purpose: it carries no
    phase transitions at all, so history cannot be replayed from it.
"""
from __future__ import annotations

import json
import subprocess
from typing import List, Optional, Sequence, Set

_GH_TIMEOUT = 120


def fetch_merged_closers(limit: int = 1000) -> Set[int]:
    """Issue numbers closed by a **merged** PR — the only "work landed" evidence.

    One ``gh pr list`` call rather than a per-issue query: classifying 236
    records must not cost 236 round trips.

    Every failure path returns an empty set, which is fail-SAFE by construction:
    with no merge evidence every class-2 candidate degrades to class 3, and
    class 3 never advances the store. A broken ``gh`` can therefore make the
    verb do *less*, never something unearned.
    """
    prs = _gh_json(
        [
            "gh", "pr", "list",
            "--state", "merged",
            "--limit", str(limit),
            "--json", "number,closingIssuesReferences",
        ],
        on_error=(
            "treating every record as class 3 (no store advance) — the verb "
            "degrades to doing less, never to advancing a store unearned"
        ),
    )
    if prs is None:
        return set()

    closed: Set[int] = set()
    for pr in prs:
        for ref in pr.get("closingIssuesReferences") or []:
            number = ref.get("number")
            if number is not None:
                closed.add(int(number))
    return closed


def fetch_labelled_issues(limit: int = 1000) -> Optional[List[dict]]:
    """Every ``atdd-issue`` (open AND closed) with its labels.

    Closed issues are the whole point — the ``label=COMPLETE`` signature only
    exists on records a merge closed. Restricting to open issues, as the
    backfill ``reconcile`` does, would never reach 217 of the 236.

    Returns ``None`` (after printing) on failure, which the caller must treat as
    "cannot decide" and abort — unlike merge evidence, an empty issue list is
    not a safe degrade, it is an empty report that looks like good news.
    """
    return _gh_json(
        [
            "gh", "issue", "list",
            "--label", "atdd-issue",
            "--state", "all",
            "--limit", str(limit),
            "--json", "number,title,state,labels",
        ],
        on_error="cannot classify without the issue list",
    )


def phase_from_labels(labels: Sequence) -> Optional[str]:
    """The ``atdd:<PHASE>`` label's phase, or None when the issue carries none.

    Accepts both the dict shape ``gh --json labels`` returns and a plain list of
    names, so callers and fixtures need not agree on a wire format.
    """
    for entry in labels or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if isinstance(name, str) and name.startswith("atdd:") and name != "atdd-issue":
            return name.split(":", 1)[1].upper()
    return None


def _gh_json(argv: List[str], *, on_error: str) -> Optional[list]:
    """Run a ``gh`` query and parse its JSON. ``None`` (after printing) on failure.

    One helper for both queries so the three ways a ``gh`` call can fail —
    the binary missing, a non-zero exit, unparseable output — are handled
    identically and reported in the operator's terms rather than as a traceback.
    """
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=_GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-30
        print(f"  Warning: `{' '.join(argv[:3])}` could not run ({exc}); {on_error}.")
        return None

    if result.returncode != 0:
        print(f"  Warning: `{' '.join(argv[:3])}` failed: {result.stderr.strip()}; {on_error}.")
        return None

    try:
        return json.loads(result.stdout) or []
    except (json.JSONDecodeError, ValueError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-30
        print(f"  Warning: could not parse `{' '.join(argv[:3])}` output ({exc}); {on_error}.")
        return None

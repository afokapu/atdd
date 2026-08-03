# URN: test:coach-ops:read-check-status:M003-SMOKE-001-installed-gh-accepts-the-query
# Acceptance: acc:coach-ops:M003-SMOKE-001-installed-gh-accepts-the-query
# WMBT: wmbt:coach-ops:M003
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""M003-SMOKE-001 — the ``gh`` actually installed accepts the exact query the
shipped code sends.

Every unit test in this feature replays a recorded payload, so none of them can
notice the field list drifting out of the CLI — which is precisely how this
defect shipped and then sat unobserved through several releases. This one runs
the real binary against the real API and lets gh answer.

Nothing is substituted: no ``monkeypatch``, no recorded payload, no wrapper over
``subprocess``. The evidence comes from what the shipped ``fetch_ci_status``
returns when it talks to the real GitHub API — a refused query surfaces in its
own detail string, which is the operator-visible symptom this acceptance
governs. Capturing argv would require standing in for a production collaborator,
which is the unit sibling's job (``acc:coach-ops:M003-UNIT-001``) and forbidden
here by ``tester.smoke.no-collaborator-substitution``.

The last test is the drift guard that earns the unit sibling its recorded field
set: it reads the field list out of this gh and fails if the recording no longer
matches what the CLI serves.

Skips only when the environment cannot answer at all — no ``gh`` on PATH, no
credential, no pull request in the repository. It never skips because the
assertion is inconvenient.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from atdd.coach.commands import merge_cascade
from atdd.coach.commands.tests.test_m003_unit_001_verdict_derives_from_advertised_fields import (
    ADVERTISED_FIELDS,
)

pytestmark = [pytest.mark.platform, pytest.mark.smoke]


_AVAILABLE_FIELDS_RE = re.compile(r"Available fields:\s*\n((?:\s+\S+\n?)+)")


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


@pytest.fixture(scope="module")
def live_gh() -> None:
    """Refuse to pretend: skip only when the real environment cannot answer."""
    if shutil.which("gh") is None:
        pytest.skip("gh is not on PATH — no installed CLI to interrogate")
    if _gh("auth", "status").returncode != 0:
        pytest.skip("gh is not authenticated — cannot reach the GitHub API")


@pytest.fixture(scope="module")
def some_pull_request(live_gh) -> int:
    """Any pull request in this repository — the query shape is what is under test."""
    listing = _gh("pr", "list", "--state", "all", "--limit", "1", "--json", "number")
    if listing.returncode != 0:
        pytest.skip(f"could not list pull requests: {listing.stderr.strip()}")
    entries = json.loads(listing.stdout or "[]")
    if not entries:
        pytest.skip("this repository has no pull requests to read checks for")
    return int(entries[0]["number"])


def test_installed_gh_does_not_refuse_the_query(some_pull_request):
    """gh must not answer the shipped query with `Unknown JSON field`."""
    _, detail = merge_cascade.fetch_ci_status(some_pull_request)

    assert "Unknown JSON field" not in detail, (
        "the installed gh REFUSED the query the shipped code sends; it reported:\n"
        f"  {detail.strip()}"
    )


def test_a_real_read_reaches_a_verdict_rather_than_unknown(some_pull_request):
    """Against a real PR the read must produce a verdict, not the pollable `unknown`."""
    state, detail = merge_cascade.fetch_ci_status(some_pull_request)

    assert state != "unknown", (
        f"the real read produced no verdict — state={state!r} detail={detail!r}; "
        "wait_for_ci polls anything that is not pass/fail, so this is the value "
        "that becomes 'no CI result after 1800s'"
    )
    assert state in {"pass", "fail", "pending"}


def test_recorded_field_set_still_matches_what_this_gh_serves(live_gh):
    """Drift guard: gh names its own fields, and the unit sibling's recording must agree.

    Field validation happens before pull-request resolution, so an unresolvable
    number is enough to make gh enumerate its fields without touching a real PR.
    """
    probe = _gh("pr", "checks", "99999999", "--json", "__atdd_field_probe__")
    match = _AVAILABLE_FIELDS_RE.search(probe.stderr or "")
    assert match, (
        "could not read gh's advertised field list from its refusal message; "
        f"stderr was {probe.stderr!r}"
    )
    live_fields = frozenset(match.group(1).split())

    assert live_fields == ADVERTISED_FIELDS, (
        "the field set recorded for the unit tests no longer matches this gh.\n"
        f"  gh serves:  {sorted(live_fields)}\n"
        f"  recorded:   {sorted(ADVERTISED_FIELDS)}\n"
        f"  gh added:   {sorted(live_fields - ADVERTISED_FIELDS)}\n"
        f"  gh dropped: {sorted(ADVERTISED_FIELDS - live_fields)}\n"
        "Update ADVERTISED_FIELDS and re-check what fetch_ci_status asks for."
    )

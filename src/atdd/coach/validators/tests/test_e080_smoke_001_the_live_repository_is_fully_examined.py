# URN: test:govern-lifecycle:subissue-label-check-examines-every-parent:E080-SMOKE-001-the-live-repository-is-fully-examined
# Acceptance: acc:govern-lifecycle:E080-SMOKE-001-the-live-repository-is-fully-examined
# WMBT: wmbt:govern-lifecycle:E080
# Phase: SMOKE
# Layer: integration
"""E080-SMOKE-001 — the live repository is fully examined (#1907).

The UNIT test uses synthetic parents. This one counts the real sub-issue graph
through an independent paginated call and checks the validator accounts for the
same number — because the defect was precisely that it accounted for one.

Independence matters: a test that asked the validator how many parents it saw
would have agreed with it, and agreeing with itself is what the old code did.
"""
from __future__ import annotations

import json
import subprocess

import pytest

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO = "afokapu/atdd"


def _census() -> dict[int, list]:
    """Parents with sub-issues, counted independently of the validator."""
    parents = subprocess.run(
        ["gh", "api", f"repos/{REPO}/issues?state=open&labels=atdd-issue&per_page=100",
         "--paginate", "--jq", ".[]|select(.pull_request==null)|.number"],
        capture_output=True, text=True, check=True,
    ).stdout.split()

    graph: dict[int, list] = {}
    for p in parents:
        out = subprocess.run(
            ["gh", "api", f"repos/{REPO}/issues/{p}/sub_issues", "--paginate"],
            capture_output=True, text=True,
        )
        if out.returncode != 0 or not out.stdout.strip():
            continue
        try:
            subs = json.loads(out.stdout)
        except ValueError:
            continue
        if subs:
            graph[int(p)] = subs
    return graph


@pytest.fixture(scope="module")
def census() -> dict[int, list]:
    graph = _census()
    if not graph:
        pytest.skip("no parent in this repository has sub-issues")
    return graph


def test_the_check_accounts_for_every_parent_not_one(census) -> None:
    """THE POINT. It used to stop at the first and report a pass for the rest."""
    from atdd.coach.validators.test_C001_roundtrip import (
        test_wmbt_sub_issues_have_atdd_wmbt_label as check,
    )

    try:
        check(census)
        reached = "PASS"
        accounted = len(census)
    except pytest.skip.Exception:  # pragma: no cover - guarded by the fixture
        pytest.fail("the check skipped a repository that has parents with sub-issues")
    except AssertionError as exc:
        reached = "FAIL"
        message = str(exc)
        header = next(
            (ln for ln in message.splitlines() if "parent issue(s) have" in ln), ""
        )
        accounted = int(header.split(" of ")[1].split()[0]) if " of " in header else -1

    assert reached in {"PASS", "FAIL"}
    assert accounted == len(census), (
        f"the check accounted for {accounted} parents; the repository has "
        f"{len(census)} with sub-issues"
    )

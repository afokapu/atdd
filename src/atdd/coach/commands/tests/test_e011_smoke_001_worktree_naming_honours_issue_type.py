"""#1948 SMOKE — the naming path that mis-named this very branch now gets it right.

This is a LIVE end-to-end check, not a unit test with the resolver mocked out.
It drives the real production chain that `atdd worktree create` uses to choose a
branch and a worktree directory:

    issue type -> issue_prefixes.prefix_for -> worktree_placement.resolve_worktree_path

and it runs in a SUBPROCESS against a real temporary git repository, because
everything about this defect was a thing that looked correct in isolation. The
map looked complete. `ALLOWED_BRANCH_PREFIXES` looked authoritative. The branch
name only came out wrong when the two met at the call site.

The regression it pins is recorded and dated: the worktree for #1948 itself —
a `chore`-typed issue — was created as `feat/retire-dead-issue-type-vocabularies`,
because `chore` was absent from `TYPE_TO_PREFIX` and `.get(issue_type, "feat")`
answered for it. All four worktrees cut for that batch of issues came out `feat/`
regardless of their declared type.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

# type -> the branch prefix a worktree for that issue must carry.
EXPECTED = {
    "implementation": "feat",
    "feature": "feat",
    "bug": "fix",
    "refactor": "refactor",
    "docs": "docs",
    "chore": "chore",
    "devops": "devops",
}

_DRIVER = textwrap.dedent("""
    import json, sys
    sys.path.insert(0, {src!r})
    from atdd.coach.commands.issue_prefixes import (
        ALLOWED_BRANCH_PREFIXES, UnknownIssueType, prefix_for,
    )
    from atdd.coach.commands.worktree_placement import resolve_worktree_path
    from pathlib import Path

    out, root = {{}}, Path({repo!r})
    for issue_type in {types!r}:
        prefix = prefix_for(issue_type)
        path = resolve_worktree_path(root, prefix, "retire-dead-issue-type-vocabularies")
        out[issue_type] = {{
            "prefix": prefix,
            "branch": prefix + "/retire-dead-issue-type-vocabularies",
            "worktree_dir": path.name,
            "prefix_allowed": prefix in ALLOWED_BRANCH_PREFIXES,
        }}
    try:
        prefix_for("cleanup")
        out["_retired_type_raises"] = False
    except UnknownIssueType:
        out["_retired_type_raises"] = True
    print(json.dumps(out))
""")


@pytest.fixture(scope="module")
def live_result(tmp_path_factory):
    """Run the real naming chain in a subprocess against a real git repo."""
    repo = tmp_path_factory.mktemp("smoke-1948-repo")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=repo, check=True)

    src = str(Path(__file__).resolve().parents[4])  # .../src
    driver = repo / "driver.py"
    driver.write_text(_DRIVER.format(src=src, repo=str(repo), types=sorted(EXPECTED)))

    proc = subprocess.run(
        [sys.executable, str(driver)], cwd=repo, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"live naming run failed:\n{proc.stdout}\n{proc.stderr}"
    import json
    return json.loads(proc.stdout)


@pytest.mark.parametrize("issue_type,expected_prefix", sorted(EXPECTED.items()))
def test_worktree_branch_carries_the_prefix_its_type_declares(
    live_result, issue_type, expected_prefix
):
    got = live_result[issue_type]
    assert got["prefix"] == expected_prefix, (
        f"a {issue_type!r} issue produced branch {got['branch']!r}"
    )
    assert got["prefix_allowed"], f"{got['prefix']!r} is not in ALLOWED_BRANCH_PREFIXES"


def test_the_exact_regression_that_misnamed_this_branch_is_gone(live_result):
    """#1948 is `chore`; its worktree came out `feat/`. It must not any more."""
    chore = live_result["chore"]
    assert chore["branch"] == "chore/retire-dead-issue-type-vocabularies"
    assert chore["worktree_dir"].startswith("chore-"), chore["worktree_dir"]
    assert not chore["branch"].startswith("feat/")


def test_no_two_distinct_prefixes_collapse_onto_feat(live_result):
    """Five of seven types used to answer `feat`. Now only the two that mean it do."""
    feat_types = {t for t in EXPECTED if live_result[t]["prefix"] == "feat"}
    assert feat_types == {"implementation", "feature"}, sorted(feat_types)


def test_a_retired_type_raises_rather_than_naming_a_branch(live_result):
    assert live_result["_retired_type_raises"], (
        "prefix_for('cleanup') must raise; the silent 'feat' fallback is the defect"
    )

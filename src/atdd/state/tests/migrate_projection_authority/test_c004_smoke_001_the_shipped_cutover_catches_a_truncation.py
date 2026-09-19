# URN: test:migrate-projection-authority:migrate-store-projection:C004-SMOKE-001-the-shipped-cutover-catches-a-truncation
# Acceptance: acc:migrate-projection-authority:C004-SMOKE-001-the-shipped-cutover-catches-a-truncation
# WMBT: wmbt:migrate-projection-authority:C004
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the shipped `atdd state cutover` exits non-zero and names the missing uid when the committed projection has had a document removed, against a real git checkout and a real .atdd/state/state.sqlite, with no mocks and no patching. Refs #2042.
"""The shipped command must refuse it (C004-SMOKE-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:C004

The unit acceptances call `cutover.check` in-process. This drives the verb an operator
actually runs, by subprocess, and asserts on the **exit code** — because that is what the
gate consumes. A criterion that reports UNMET in a dataclass while the command still exits
zero has not blocked anything.

It also asserts the intact case exits zero first. Without that, a command that exited
non-zero for any reason at all would satisfy this test, and the whole point of #2042 is
that a check which cannot discriminate is not a check.

HERMETIC on the three pins this wagon's SMOKEs keep: `--root`, `HOME` and `PYTHONPATH`
inside `tmp_path`. The developer's shared Control Root store — which other worktrees are
writing to right now — is never opened.
"""
from __future__ import annotations

import pytest

from ._coverage_helpers import committed_filenames, new_repo, project_and_commit, remove_document, seed
from ._live import atdd_state

pytestmark = [pytest.mark.platform]


def test_the_shipped_cutover_exits_non_zero_on_a_truncated_projection(tmp_path) -> None:
    """`atdd state cutover` refuses a truncated committed projection and says which uid."""
    root = new_repo(tmp_path / "checkout")
    minted = seed(root, [("alpha-item", "PLANNED"), ("beta-item", "RED"), ("gamma-item", "SMOKE")])
    out = project_and_commit(root)

    intact = atdd_state(root, "cutover", "--from", str(out))
    assert intact.returncode == 0, (
        "the intact projection must pass through the shipped command first, or a non-zero "
        f"exit below proves nothing:\n{intact.stdout}\n{intact.stderr}"
    )

    victim = minted["beta-item"]
    remove_document(root, f"{victim}.yaml")
    assert len(committed_filenames(root)) == len(minted) - 1

    truncated = atdd_state(root, "cutover", "--from", str(out))
    assert truncated.returncode != 0, (
        "the shipped cutover exited zero on a projection missing an object the store holds. "
        f"stdout:\n{truncated.stdout}\nstderr:\n{truncated.stderr}"
    )
    assert victim in (truncated.stdout + truncated.stderr), (
        f"the output must name the missing uid {victim} so an operator can act on it"
    )

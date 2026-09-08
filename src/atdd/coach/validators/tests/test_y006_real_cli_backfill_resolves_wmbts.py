# URN: test:govern-lifecycle:bind-issue-feature:Y006-INTEGRATION-001-real-cli-backfill-resolves-wmbts
# Acceptance: acc:govern-lifecycle:Y006-INTEGRATION-001-backfill-populates-null-bindings
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Against the real CLI in a real checkout with a real State Store, `atdd coach backfill-bindings` writes the binding the body declared and `atdd coach issues <N>` then resolves real WMBTs for an issue that reported "no feature binding" moments earlier.
"""#1689 — the backfill proved through the shipped commands, with nothing stubbed.

WHY THIS EXISTS, AND WHY A STUB COULD NOT REPLACE IT

``test_y006_backfill_bindings_verb_wiring`` patches the engine in every test. It
proves the verb is discovered and delegates — and it proves NOTHING about what
lands in a store, because the only thing it ever observes is the spy it installed.
A green built entirely out of stubs certifies the stub.

That is not a hypothetical in this repo. It is the failure mode the whole program
is about:

* ``WMBTs: none found`` printed for every issue in the repo for months, because
  #1477 deleted the producer and left the consumer standing. Nothing asserted the
  two ends still met.
* ``live_smoke_obligation`` returns ``acceptance_urns=()`` and the SMOKE gate
  passes as *not applicable* — a green certifying nothing.
* On #1622 an agent's own suite reported 28 passed while ``atdd author issue`` was
  broken outright, exiting 2 on every invocation. Stubs hid it; a cross-scope real
  run caught it.

So this test spawns the real ``python -m atdd`` in a separate process, against a
real on-disk SQLite State Store and a real ``plan/`` tree, and reads the store
back through a fresh connection rather than believing the command's own report.
Several commands in this repo report success while writing nothing; the assertion
is the row, never the stdout.

THE DISCRIMINATOR. ``test_the_same_command_reports_no_binding_before_the_backfill``
runs ``atdd coach issues <N>`` BEFORE the backfill and pins the "no feature
binding" message. Without it, the WMBT lines the after-case asserts could have
come from a fixture that was already bound, and the test would pass while the
backfill did nothing. The stub ``gh`` reinforces this from the other side: it
answers ``gh issue list --label atdd-wmbt`` with ``[]`` — the honest live answer,
since nothing has minted that label since #1477 — so any WMBT in the output
provably came from ``plan/`` and from nowhere else.

HERMETIC, AND THE ISOLATION IS ASSERTED RATHER THAN ASSUMED. The live store at
the repo's Control Root is shared with other agents' worktrees; a test that wrote
to it would corrupt work in flight. Isolation rests on ``ATDD_CONTROL_ROOT``
(resolver Rule 1, the explicit override) plus ``cwd``, because the backfill
resolves its STORE from the Control Root and its ``plan/`` from the CURRENT
DIRECTORY — two different anchors that must both land inside ``tmp_path``.
``TestTheSharedStoreIsNeverTouched`` proves both: one test asserts the resolved
store path is inside ``tmp_path`` and outside the repo, the other digests the
repo's own store before and after a real write run and asserts it is unchanged.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    FEATURE_WMBT,
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    stub_issue,
    write_plan_tree,
    write_stub_gh,
)

pytestmark = [pytest.mark.platform]

_ISSUE = 93002
_SLUG = "backfill-smoke-probe"
_REPO_SRC = Path(__file__).resolve().parents[4]  # .../src


def _cli_env(root: Path, bindir: Path) -> dict:
    """The environment the real CLI runs under, pinned to ``root``.

    ``ATDD_CONTROL_ROOT`` is resolver Rule 1 (the explicit override) and anchors
    the STORE. ``cwd=root`` — set by the caller — anchors ``plan/``. Both are
    required: the backfill resolves the two from different places, so pinning
    only one would leave the other pointing at the real repo.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_SRC)
    env["ATDD_CONTROL_ROOT"] = str(root)
    # The stub `gh` first, then the interpreter's own bin so `python -m atdd`
    # still resolves. Nothing else from the developer's PATH leaks in.
    env["PATH"] = os.pathsep.join([str(bindir), str(Path(sys.executable).parent)])
    return env


def _run_cli(root: Path, bindir: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke the real CLI in a separate process against ``root``."""
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=root,
        env=_cli_env(root, bindir),
        capture_output=True,
        text=True,
        timeout=180,
    )


def _stored_feature(root: Path) -> object:
    """The stored binding, read back through a FRESH store connection.

    Deliberately not the command's stdout: `atdd` commands in this repo have
    reported success while writing nothing, which is the defect family #1689
    sits inside. The row is the evidence.
    """
    return read_issue_data(open_store(root), _ISSUE).get("feature")


@pytest.fixture()
def repo(tmp_path):
    """A real Control Root, a real store, a real plan/ tree, and a stub `gh`.

    The work item reproduces the measured status quo exactly: ``feature`` is
    NULL in the store while the body's Metadata table declares a URN that
    resolves. That divergence is the whole of #1689.
    """
    from atdd.planner.commands.author_issue import create_issue_body

    root = control_root(tmp_path)
    write_plan_tree(root)

    # A schema-valid body carrying the Feature row the backfill derives from.
    # Hand-rolling a fragment would risk deriving from a body the real authoring
    # path would never have produced.
    body = create_issue_body({"title": "backfill smoke probe", "feature": FEATURE_URN})

    store = open_store(root)
    seed_issue(store, slug=_SLUG, issue_number=_ISSUE, state="INIT",
               feature=None, body=body)

    # INIT keeps `atdd coach issues <N>` on its read-only branch: the
    # branch-carrying phases create a worktree (see #1704), which would make
    # this test mutate the developer's checkout to observe a print statement.
    bindir = write_stub_gh(root, {_ISSUE: stub_issue(_ISSUE, body=body, status="INIT")})

    assert _stored_feature(root) is None, "fixture must start from a NULL binding"
    return root, bindir


# ---------------------------------------------------------------------------
# 1. The real command writes the binding the body already declared
# ---------------------------------------------------------------------------
class TestTheRealBackfillWritesTheBinding:
    def test_the_shipped_command_writes_the_declared_feature_to_the_store(self, repo):
        root, bindir = repo

        result = _run_cli(root, bindir, "coach", "backfill-bindings")

        assert result.returncode == 0, (
            f"real CLI backfill exited {result.returncode}\nstderr:\n{result.stderr}"
        )
        assert _stored_feature(root) == FEATURE_URN, (
            "the real command exited 0 and left the stored binding NULL — the "
            "shape of every defect #1689 sits inside: a tool reporting success "
            "while writing nothing"
        )

    def test_the_report_names_what_it_wrote(self, repo):
        """An operator must be able to tell a write from a silently-skipped row."""
        root, bindir = repo

        result = _run_cli(root, bindir, "coach", "backfill-bindings")

        assert "wrote 1 binding(s)" in result.stdout, result.stdout
        assert "would write" not in result.stdout, (
            "a real run described itself as a preview"
        )

    def test_a_dry_run_previews_without_writing(self, repo):
        """The preview is exercised against the REAL engine, not a spy.

        The wiring suite asserts the flag reaches a stub. That cannot catch a
        dry-run that writes anyway — only reading the row back can.
        """
        root, bindir = repo

        result = _run_cli(root, bindir, "coach", "backfill-bindings", "--dry-run")

        assert result.returncode == 0, result.stderr
        assert "would write 1 binding(s)" in result.stdout, result.stdout
        assert _stored_feature(root) is None, (
            "--dry-run mutated the store; a preview that writes is worse than no "
            "preview, because it is trusted"
        )

    def test_a_second_run_writes_nothing(self, repo):
        """Idempotence, observed across two real processes."""
        root, bindir = repo

        first = _run_cli(root, bindir, "coach", "backfill-bindings")
        second = _run_cli(root, bindir, "coach", "backfill-bindings")

        assert "wrote 1 binding(s)" in first.stdout, first.stdout
        assert "wrote 0 binding(s)" in second.stdout, (
            "the second run rewrote an existing binding; the backfill must never "
            "overwrite one it did not create"
        )
        assert _stored_feature(root) == FEATURE_URN


# ---------------------------------------------------------------------------
# 2. The consumer resolves real WMBTs afterwards — the whole point of #1635
# ---------------------------------------------------------------------------
class TestCoachIssuesResolvesWmbtsAfterTheBackfill:
    def test_the_same_command_reports_no_binding_before_the_backfill(self, repo):
        """The discriminator. Without this the after-case proves nothing.

        If the fixture were already bound, the WMBT lines asserted below would
        appear with or without the backfill and the suite would be green over a
        no-op.
        """
        root, bindir = repo

        result = _run_cli(root, bindir, "coach", "issues", str(_ISSUE))

        assert result.returncode == 0, result.stderr
        assert "WMBTs: no feature binding" in result.stdout, (
            "the pre-backfill state is not the one #1689 describes, so the "
            "after-case below would not be attributable to the backfill\n"
            f"{result.stdout}"
        )

    def test_real_wmbts_are_resolved_after_the_real_backfill(self, repo):
        """`atdd coach issues <N>` resolves through the freshly written binding."""
        root, bindir = repo

        backfill = _run_cli(root, bindir, "coach", "backfill-bindings")
        assert backfill.returncode == 0, backfill.stderr

        result = _run_cli(root, bindir, "coach", "issues", str(_ISSUE))

        assert result.returncode == 0, result.stderr
        assert f"WMBTs: 1 declared by {FEATURE_URN}" in result.stdout, result.stdout
        assert FEATURE_WMBT in result.stdout, (
            "the feature resolved but its WMBT was not rendered, so the walk "
            "issue -> feature -> wmbts: stops short of the thing an operator needs"
            f"\n{result.stdout}"
        )

    def test_the_resolved_wmbt_never_reads_none_found(self, repo):
        """The string that stood for four different states is gone for good."""
        root, bindir = repo

        _run_cli(root, bindir, "coach", "backfill-bindings")
        result = _run_cli(root, bindir, "coach", "issues", str(_ISSUE))

        assert "none found" not in result.stdout, (
            "the decommissioned label lookup's output is back"
        )
        assert "no feature binding" not in result.stdout, (
            "the binding was written but the consumer still reports it absent — "
            "producer and consumer have come apart again"
        )

    def test_the_wmbt_came_from_plan_not_from_the_provider(self, repo):
        """The stub `gh` returns [] for every wmbt label query.

        So a WMBT in the output cannot have come from GitHub. It also cannot be
        a swallowed-subprocess artefact: the old lookup returned [] on failure,
        which is why a merely-absent provider would prove nothing here.
        """
        root, bindir = repo

        _run_cli(root, bindir, "coach", "backfill-bindings")
        result = _run_cli(root, bindir, "coach", "issues", str(_ISSUE))

        assert FEATURE_WMBT in result.stdout
        # Rendered with the path its URN implies, under the tmp plan/ tree —
        # a second, independent sign the resolution walked plan/ on disk.
        assert str(root / "plan" / "govern_lifecycle") in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# 3. Isolation, asserted rather than assumed
# ---------------------------------------------------------------------------
class TestTheSharedStoreIsNeverTouched:
    """The live store is shared across worktrees. A leak here corrupts other agents."""

    def test_the_cli_resolves_its_store_inside_the_tmp_root(self, repo, tmp_path):
        """The store the CLI would open is under tmp_path, not the repo.

        Replicates ``issue_feature_binding._open_store(None)`` exactly — the
        call the verb makes — in a subprocess carrying the CLI's own env and
        cwd, so this is the resolution that actually happens rather than an
        in-process approximation of it.
        """
        root, bindir = repo

        probe = subprocess.run(
            [sys.executable, "-c",
             "from atdd.state.db import init_state_store; print(init_state_store())"],
            cwd=root, env=_cli_env(root, bindir),
            capture_output=True, text=True, timeout=120,
        )

        assert probe.returncode == 0, probe.stderr
        resolved = Path(probe.stdout.strip()).resolve()
        assert tmp_path.resolve() in resolved.parents, (
            f"the CLI resolves its store to {resolved}, outside the test's tmp "
            "root — every write in this module would land in a shared store"
        )
        assert _REPO_SRC.parent.resolve() not in resolved.parents, (
            f"the CLI resolves its store to {resolved}, inside the repo checkout"
        )

    def test_a_real_write_run_leaves_the_repo_store_byte_identical(self, repo):
        """Digest the repo's own store around a real write run.

        Meaningful whether or not that store exists: present → the digest must
        not move; absent (a fresh CI checkout, where ``.atdd/state`` is
        gitignored) → the run must not conjure one into being.
        """
        root, bindir = repo
        from atdd.state.db import STATE_STORE_RELATIVE
        from atdd.state.paths import resolve_control_root

        # Resolved WITHOUT the override, so this is the real shared store.
        shared = (
            resolve_control_root(Path(__file__).resolve().parent).control_root
            / STATE_STORE_RELATIVE
        )
        before = (
            hashlib.sha256(shared.read_bytes()).hexdigest() if shared.is_file() else None
        )

        result = _run_cli(root, bindir, "coach", "backfill-bindings")
        assert result.returncode == 0, result.stderr
        assert _stored_feature(root) == FEATURE_URN, "the run must really have written"

        after = (
            hashlib.sha256(shared.read_bytes()).hexdigest() if shared.is_file() else None
        )
        assert after == before, (
            f"the shared State Store at {shared} changed during a hermetic test "
            "(or was created by one) — other agents' worktrees read this file"
        )

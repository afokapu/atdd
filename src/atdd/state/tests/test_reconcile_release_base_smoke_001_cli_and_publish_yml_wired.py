# URN: test:govern-lifecycle:state:reconcile-release-base-smoke-cli-and-publish-yml-wired
# Issue: #1326 (#1172 CI publication path)
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1326 — the real ``reconcile-base`` CLI and the wired ``publish.yml``.

Drives the REAL ``atdd state version reconcile-base`` CLI (the entry point
``publish.yml`` calls) and lints the workflow to confirm the reconcile base now
flows through the helper rather than the raw ``git describe`` tag:

- ``--no-pypi`` path is deterministic (no network): the base equals the git tag.
- A best-effort real-PyPI query proves the end-to-end contract holds regardless
  of network state — the base is NEVER below the git tag (fallback keeps it so),
  so the assertion is honest, not flaky.
- ``publish.yml`` invokes ``version reconcile-base --git-tag`` and feeds it into
  ``set`` + ``bump``.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.cli import run
from atdd.state import version as ver

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PUBLISH_YML = _REPO_ROOT / ".github" / "workflows" / "publish.yml"


def test_real_cli_reconcile_base_no_pypi_prints_the_git_tag(capsys):
    """The real CLI, with the PyPI query disabled, echoes the git tag base."""
    assert run(["version", "reconcile-base", "--git-tag", "3.151.4", "--no-pypi"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == "3.151.4"


def test_reconcile_base_is_never_below_the_git_tag_end_to_end():
    """Best-effort real PyPI: the resolved base never regresses below the tag.

    Honest and non-flaky: if PyPI is reachable the base is ``max(pypi, tag)``; if
    it is unreachable :func:`latest_on_pypi` returns ``None`` and the base falls
    back to the tag. Either way ``base >= tag`` holds.
    """
    tag = "3.151.4"
    base = ver.resolve_release_base(tag, ver.latest_on_pypi())
    assert ver.parse(base) >= ver.parse(tag)


def test_publish_workflow_wires_reconcile_base_into_set_and_bump():
    text = _PUBLISH_YML.read_text()
    # The reconcile base flows through the helper, not the raw git tag alone.
    assert "version reconcile-base" in text
    assert "--git-tag" in text
    # ...and is still fed into the store set + bump sequence.
    assert "atdd state version set" in text and "atdd state version bump" in text
    # The drain wiring (E058) is untouched.
    assert "drain_version_decided" in text

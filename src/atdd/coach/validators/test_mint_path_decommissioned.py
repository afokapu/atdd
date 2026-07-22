"""#1477: the orphaned ``IssueManager`` mint path stays decommissioned.

`atdd author issue` (#1272) is the store-first, schema-driven create path. The
pre-schema ``IssueManager`` mint path that predates it — ``create_new_issue``,
``new``/``_new_github_issue``, and the ``atdd new`` CLI surface that was its only
live entry point — is removed.

Two cadavers rode on that path and are removed with it:

* ``_discover_wmbts`` called ``wmbt.get("id", "")`` on feature-YAML entries the
  schema mandates are URN *strings* (the #837 crash).
* ``sync_wmbts`` / ``_discover_wmbts_from_feature`` resolved plan artifacts
  through a store ``wagon`` field. Nothing has written ``wagon`` since the
  taxonomy moved to Train + Feature, so the backfill refused on every
  canonically-authored issue (#839) — a command that could not succeed.

These are regression guards, not behavior tests: they fail if the mint path is
reintroduced. Deliberately free of the ``github_api``/``platform`` markers so
they run in core CI — a guard that is deselected is not a guard.
"""
from __future__ import annotations

import pytest

# The mint-path surface removed by #1477. Reintroducing any of these means a
# second create path is back alongside `atdd author issue`.
REMOVED_ISSUE_MANAGER_METHODS = (
    "create_new_issue",
    "new",
    "_new_github_issue",
    "_discover_wmbts",
    "_discover_wmbts_from_feature",
    "sync_wmbts",
    "edit_issue_body",
    "_register_issue_in_manifest",
)

REMOVED_ISSUE_MODULE_SYMBOLS = (
    "IssueBodyChecker",
    "IssueBodyComplianceError",
    "dup_check_before_file",
    "STEP_CODES",
)


def test_issue_manager_mint_path_methods_are_gone():
    """SPEC-COACH-MINT-0001: IssueManager carries no mint-path method."""
    from atdd.coach.commands.issue import IssueManager

    resurrected = [m for m in REMOVED_ISSUE_MANAGER_METHODS if hasattr(IssueManager, m)]

    assert not resurrected, (
        "The IssueManager mint path was decommissioned by #1477, but these "
        f"methods are back: {', '.join(resurrected)}.\n"
        "Creation is `atdd author issue --title <t> --slug <s>` (store-first, "
        "schema-driven — #1272). Do not reintroduce a second create path."
    )


def test_issue_module_mint_helpers_are_gone():
    """SPEC-COACH-MINT-0002: the mint path's module-level helpers are gone."""
    import atdd.coach.commands.issue as issue_module

    resurrected = [s for s in REMOVED_ISSUE_MODULE_SYMBOLS if hasattr(issue_module, s)]

    assert not resurrected, (
        "These mint-path helpers were removed by #1477 but are back: "
        f"{', '.join(resurrected)}. Body validation lives in the planner's "
        "`issue.schema.json` gate (`atdd author issue --check`)."
    )


def test_issue_lifecycle_create_is_gone():
    """SPEC-COACH-MINT-0003: IssueLifecycle no longer wraps the mint path."""
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    assert not hasattr(IssueLifecycle, "create"), (
        "IssueLifecycle.create was removed by #1477 — it existed only to drive "
        "IssueManager.new. Creation is `atdd author issue`."
    )


def test_atdd_new_is_a_removed_command_naming_its_replacement():
    """SPEC-COACH-MINT-0004: `atdd new` is refused, and names `atdd author issue`.

    Removed, not merely un-registered: argparse would answer a bare
    ``invalid choice: 'new'`` that names no replacement.
    """
    from atdd.cli import REMOVED_COMMANDS

    assert "new" in REMOVED_COMMANDS, (
        "`atdd new` was removed by #1477 and must stay in REMOVED_COMMANDS so "
        "invoking it names the replacement instead of an argparse error."
    )
    assert "atdd author issue" in REMOVED_COMMANDS["new"], (
        "The `atdd new` removal notice must name `atdd author issue` — the "
        "replacement must be a real, live command (see the E006 "
        "no-dangling-replacement-target gate)."
    )


def test_atdd_new_is_refused_before_argparse(capsys):
    """SPEC-COACH-MINT-0005: invoking `atdd new` exits non-zero and explains.

    Exercises the real guard rather than a parser internal: it must intercept
    `new` pre-parse, exit non-zero, and print the replacement.
    """
    import io

    from atdd.cli import _removed_command_guard

    stream = io.StringIO()
    rc = _removed_command_guard(["new", "some-slug"], stream=stream)

    assert rc == 2, f"`atdd new` must exit non-zero; got rc={rc!r}"
    assert "atdd author issue" in stream.getvalue(), (
        "`atdd new` must name its replacement on refusal; got:\n"
        f"{stream.getvalue()}"
    )


def test_live_commands_still_pass_the_removed_guard():
    """SPEC-COACH-MINT-0007: the guard rejects only removed commands.

    Guards against an over-broad match that would take a live verb down with it.
    """
    from atdd.cli import _removed_command_guard

    for live in ("author", "coach", "validate", "worktree"):
        assert _removed_command_guard([live], stream=None) is None, (
            f"`atdd {live}` is a live command but the removed-command guard "
            "intercepted it."
        )


def test_sync_wmbts_is_not_a_coach_verb():
    """SPEC-COACH-MINT-0006: `atdd coach sync-wmbts` is gone.

    The verb is an auto-discovered drop-in, so its absence from the package IS
    its absence from the CLI.
    """
    from importlib import import_module

    with pytest.raises(ModuleNotFoundError):
        import_module("atdd.coach.commands.coach_verbs.sync_wmbts")

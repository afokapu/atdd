# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-UNIT-003-every-registered-flag-is-consumed-or-refused
# Acceptance: acc:govern-lifecycle:Y007-UNIT-003-every-registered-flag-is-consumed-or-refused
# WMBT: wmbt:govern-lifecycle:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: The guard enumerates the `author issue` parser's own declared arguments, so a flag added to the CLI and forgotten in a handler fails a test instead of exiting 0.
"""
RED Test for test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-UNIT-003-every-registered-flag-is-consumed-or-refused
wagon: govern-lifecycle | feature: issue-author-validate-locally-publish-once | phase: RED
WMBT: wmbt:govern-lifecycle:Y007

Purpose: close the CLASS, not the instance.

`atdd author issue` registers eleven flags on one subparser and dispatches them
to three handlers, each reading a different subset. Nothing checks that the two
sets agree, so a flag can be registered, documented in --help, accepted at the
command line, and read by nobody.

Y006-UNIT-001 already carries a test named
``test_no_accepted_revise_flag_is_dropped`` whose docstring says it asserts
"against the parser's own declared arguments rather than a hand-maintained
list". It does not: it iterates the literal tuple ``("body", "issue_type",
"feature")``. That is why it was green while `--title` was being dropped. A
hand-maintained guard against hand-maintained drift cannot work — it has to be
edited by the same person who forgot to wire the flag.

This guard derives its list from the parser object itself, so no one has to
remember to update it.

Fails today because `--title` is registered and read by no handler and is in no
refusal set.
"""
from __future__ import annotations

import argparse
import inspect

import pytest

import atdd.planner.commands.author as author

from .test_y007_unit_002_revise_refuses_the_flags_it_cannot_honour import (
    UNSUPPORTED_ON_REVISE,
)

pytestmark = [pytest.mark.platform]

# The create-side flag known to be accepted and discarded, tracked by its own
# issue and its own fix site. Recorded here so this guard REPORTS it rather
# than being weakened to accommodate it — the alternative would be widening the
# tolerated set until the guard stops guarding.
KNOWN_GAPS: dict[str, str] = {
    "body_file": "#1631 — --body-file is ignored on the create path",
}


def _issue_subparser() -> argparse.ArgumentParser:
    """The real `atdd author issue` subparser, found by walking the parser tree."""
    parser = author.build_parser()

    def walk(node):
        for action in node._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                for name, sub in choices.items():
                    if name == "issue":
                        return sub
                    found = walk(sub)
                    if found is not None:
                        return found
        return None

    found = walk(parser)
    assert found is not None, (
        "could not locate the `author issue` subparser; the guard must read the "
        "real parser, never a copy of its flag list"
    )
    return found


def _registered_dests() -> set[str]:
    """Every option destination the `issue` subparser declares."""
    return {
        action.dest
        for action in _issue_subparser()._actions
        if action.option_strings and action.dest != "help"
    }


def _handler_sources() -> dict[str, str]:
    """The source text of each handler the `issue` subparser dispatches to.

    The revise "handler" is the whole chain the flag must survive, not just its
    entry function — a value read in ``_run_issue_revise`` and then not passed
    on by ``_publish_revision`` is still dropped.
    """
    return {
        "create": inspect.getsource(author._run_issue_create),
        "revise": (
            inspect.getsource(author._run_issue_revise)
            + inspect.getsource(author._publish_revision)
            + inspect.getsource(author._revision_violations)
        ),
        "check": inspect.getsource(author._run_issue_check),
    }


def _reads(handler: str, dest: str) -> bool:
    """Whether ``handler`` reads ``args.<dest>`` (directly or via getattr)."""
    src = _handler_sources()[handler]
    return f"args.{dest}" in src or f'getattr(args, "{dest}"' in src


# `--check` and `--revise` are mode selectors read by the dispatcher, not
# payload carried into a write, so they are not required of every path.
_MODE_SELECTORS = {"check", "revise"}


def test_every_flag_the_revise_path_accepts_is_read_or_refused() -> None:
    """A flag is dropped when its OWN path neither reads nor refuses it.

    Checking global consumption is not enough and was the trap: `--title` is
    read by the create path, so any guard asking merely "does some handler read
    this?" stays green while `--revise --title` discards the value. The
    contract is per-path.
    """
    refused = {flag.lstrip("-").replace("-", "_") for flag in UNSUPPORTED_ON_REVISE}
    dropped = sorted(
        dest for dest in _registered_dests() - _MODE_SELECTORS
        if not _reads("revise", dest) and dest not in refused
    )

    assert not dropped, (
        "these flags are accepted by `atdd author issue --revise` and neither "
        f"read by the revise chain nor refused by it: {dropped}. The CLI takes "
        "the value and exits 0 having discarded it. Either wire the flag to "
        "the writer that must consume it, or add it to UNSUPPORTED_ON_REVISE "
        "so the command exits non-zero naming it."
    )


def test_every_flag_the_create_path_accepts_is_read() -> None:
    """The same contract on the create side, where #1631 lives."""
    dropped = sorted(
        dest for dest in _registered_dests() - _MODE_SELECTORS
        if not _reads("create", dest) and dest not in KNOWN_GAPS
    )

    assert not dropped, (
        "these flags are accepted by `atdd author issue` on the create path "
        f"and read by nothing in it: {dropped}"
    )


def test_the_refusal_set_is_exactly_the_flags_the_revise_path_declines() -> None:
    """Widening the refusal set to hide a new drop fails this test.

    Without this, the previous test has a trivial escape: add the newly-dropped
    flag to UNSUPPORTED_ON_REVISE and it goes quiet again. Pinning the set
    means suppressing a drop requires editing an explicit list of things the
    command REFUSES — a visible, reviewable act, not a silent one.
    """
    assert set(UNSUPPORTED_ON_REVISE) == {"--slug", "--status", "--branch", "--train"}, (
        "the revise refusal set changed. Every entry must be a flag the revise "
        "path deliberately declines, never a flag it silently drops: "
        f"{sorted(UNSUPPORTED_ON_REVISE)}"
    )


def test_the_guard_reads_the_parser_not_a_copy_of_it() -> None:
    """A flag added to the CLI must fail this guard without anyone editing it.

    The failure mode being prevented is Y006-UNIT-001's: a guard whose flag
    list is a literal in the test file, which therefore only ever knows about
    flags someone remembered to add to it.
    """
    dests = _registered_dests()

    assert {"title", "slug", "status", "branch", "train", "feature",
            "issue_type", "body_file", "revise", "check"} <= dests, (
        f"the parser walk did not find the known `author issue` flags: {sorted(dests)}"
    )

    source = inspect.getsource(_registered_dests) + inspect.getsource(_issue_subparser)
    assert "build_parser" in source, (
        "the guard must derive its flag list from the real parser object; a "
        "hand-maintained tuple cannot catch the flag its author forgot to wire"
    )


def test_the_known_create_side_gap_is_still_reported() -> None:
    """#1631 stays visible while it is open, and this test dies when it closes.

    A tolerated gap that nobody re-checks becomes permanent. This asserts the
    gap is REAL — if `--body-file` starts being read on the create path, this
    fails and the entry must be deleted from KNOWN_GAPS.
    """
    for dest, why in KNOWN_GAPS.items():
        assert not _reads("create", dest), (
            f"{dest} is now read by the create path, so the gap recorded as "
            f"{why!r} has closed. Delete it from KNOWN_GAPS so the guard covers "
            f"it like any other flag."
        )

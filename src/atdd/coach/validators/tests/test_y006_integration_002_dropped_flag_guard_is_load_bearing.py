# URN: test:govern-lifecycle:bind-issue-feature:Y006-INTEGRATION-002-dropped-flag-guard-is-load-bearing
# Acceptance: acc:govern-lifecycle:Y006-INTEGRATION-002-dropped-flag-guard-is-load-bearing
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Removing the feature argument from the revise call chain, and separately the derive-or-require branch at create, must each turn the suite RED.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:Y006-INTEGRATION-002-dropped-flag-guard-is-load-bearing
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:Y006

Purpose: prove the threading is load-bearing rather than incidental.

Break 4 is a guard that was never there. Once it exists, this proves it can
fail: each link is removed IN ISOLATION from a COPY of the source (the real
tree is never mutated) and the corresponding contract is shown to break.

Regex fault injection FAILS OPEN — a non-matching anchor mutates nothing and a
no-op edit then reads as "guard removed, suite stayed green". Every injection
therefore asserts the anchor matched EXACTLY ONCE and that the mutated source
still parses. Mirrors acc:govern-lifecycle:C010-INTEGRATION-002.

Today every anchor matches ZERO times, because the threading does not exist.
That is the failure this test is supposed to report.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from ._bind_issue_feature_helpers import source_of

pytestmark = [pytest.mark.platform]

# The two links Break 4 is missing, each expressed as the smallest anchor that
# identifies it without pinning incidental formatting.
_STORE_MERGE = re.compile(r'updates\[\s*["\']feature["\']\s*\]\s*=\s*feature')
_CLI_FORWARD = re.compile(r'feature\s*=\s*args\.feature')


def _inject(source: str, pattern: re.Pattern, what: str) -> str:
    """Remove one link, proving the edit landed and the result still parses."""
    matched = len(pattern.findall(source))
    assert matched == 1, (
        f"fault-injection anchor for {what} matched {matched} times, expected "
        f"EXACTLY 1 — pattern {pattern.pattern!r}. Zero matches means the link "
        f"does not exist yet, so there is no guard to remove and `--feature` is "
        f"discarded between the CLI and the store (#1635 Break 4)."
    )
    mutated = pattern.sub("pass  # fault injected", source)
    assert mutated != source, "injection produced an identical source (no-op edit)"
    ast.parse(mutated)  # a SyntaxError would fail this test for the WRONG reason
    return mutated


def test_store_merge_link_exists_and_is_removable() -> None:
    """`revise_work_item_issue` must merge the feature into the object data."""
    source = source_of("atdd.state.work_item_writer")
    _inject(source, _STORE_MERGE, "the store-side feature merge")


def test_cli_forward_link_exists_and_is_removable() -> None:
    """The revise CLI path must forward `args.feature` into the publish call."""
    source = source_of("atdd.planner.commands.author")
    _inject(source, _CLI_FORWARD, "the CLI-side feature forward")


def test_revise_signature_carries_feature_end_to_end() -> None:
    """Every hop between the parser and the store must name `feature`.

    The three call sites the measurement on 2026-07-28 traversed: argparse
    accepted the flag, and each hop below silently omitted it.
    """
    import inspect

    from atdd.planner.commands.author_publish import revise_issue
    from atdd.state.work_item_writer import revise_work_item_issue

    missing = [
        f"{fn.__module__}.{fn.__name__}"
        for fn in (revise_issue, revise_work_item_issue)
        if "feature" not in inspect.signature(fn).parameters
    ]
    assert not missing, (
        "the revise chain drops `--feature` at: " + ", ".join(missing)
    )


def test_no_fault_injected_leaves_both_sources_parseable() -> None:
    """The negative control: unmutated sources parse, so a later SyntaxError
    in an injection is attributable to the injection alone."""
    for module in ("atdd.state.work_item_writer", "atdd.planner.commands.author"):
        ast.parse(source_of(module))
        assert Path(__file__).exists()

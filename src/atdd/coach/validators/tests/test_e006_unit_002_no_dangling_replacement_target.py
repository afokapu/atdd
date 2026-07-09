# URN: test:coach-verb-split:coach-verb-split:E006-UNIT-002-no-dangling-replacement-target
# Acceptance: acc:coach-verb-split:E006-UNIT-002-no-dangling-replacement-target-in-fix-hints
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C5b (#1309) — the C2 fix-hint registry gains a dangling-replacement-target audit.

The C2 registry is DYNAMIC: `build_deprecation_registry()` regexes cli.py for
`_deprecation_warning("<old>", "<new>")` callsites and keys on the OLD form. That
shape has a blind spot this issue exposes:

    audit_c2_no_deprecation_contradiction  flags a hint recommending a DEPRECATED
                                           form (a registry KEY).
    ...nothing                             flags a hint recommending a NONEXISTENT
                                           form (a registry VALUE naming a command
                                           that was deleted).

`atdd issue` was never a registry KEY — the C1-C5a shims used direct
`print(..., file=sys.stderr)` on purpose, precisely so no wholesale `atdd issue`
key would land and false-flag the still-valid `atdd issue <N>` hints. It appears
only as a replacement VALUE, in four surviving `_deprecation_warning` callsites
(`atdd archive`, `atdd update` x2, `atdd close-wmbt`). Deleting the command would
leave those four telling operators to run a command that no longer exists, and
C2 would stay green.

Repointing the four strings fixes it once. `audit_c2b_no_dangling_replacement_target`
makes it un-reappearable: every replacement target must name a registered
top-level subcommand.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators.test_fix_hint_completeness import (  # noqa: F401
    audit_c1_placeholder_resolution,
    audit_c2_no_deprecation_contradiction,
    audit_c2b_no_dangling_replacement_target,
    build_deprecation_registry,
    build_subcommand_registry,
    iter_deprecation_callsites,
)

pytestmark = [pytest.mark.platform]


class TestSubcommandRegistry:
    """`build_subcommand_registry` reads the TOP-LEVEL subparser names from cli.py."""

    def test_reads_top_level_subcommands_only(self):
        subs = build_subcommand_registry()
        # Real, stable top-level commands.
        for expected in ("coach", "author", "validate", "pr", "list"):
            assert expected in subs, f"top-level `atdd {expected}` not discovered"

    def test_excludes_nested_subparsers(self):
        """`registry_subparsers.add_parser("build")` must NOT register `build`.

        Nested groups (registry_/worktree_/repo_/rules_/suppress_/manifest_/
        substrate_subparsers) all end in `subparsers`, so a naive regex would
        hoist their children to the top level and make the audit vacuous.
        """
        source = '''
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("coach")
    registry_subparsers = registry_parser.add_subparsers(dest="registry_command")
    registry_subparsers.add_parser("build")
'''
        subs = build_subcommand_registry(source)
        assert subs == {"coach"}, f"nested subparser leaked into top level: {subs}"


class TestDanglingReplacementTargetAudit:
    """The new audit fails loud on a hint naming a command that does not exist."""

    def test_flags_a_hint_recommending_a_nonexistent_command(self):
        source = '''
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("coach")
    _deprecation_warning("atdd archive <N>", "atdd issue <N> --status COMPLETE")
'''
        registry = build_deprecation_registry(source)
        subcommands = build_subcommand_registry(source)
        violations = audit_c2b_no_dangling_replacement_target(registry, subcommands)

        assert violations, (
            "a hint recommending `atdd issue` when `issue` is not a registered "
            "subcommand must be flagged"
        )
        old, new, missing = violations[0]
        assert old == "atdd archive"
        assert "atdd issue" in new
        assert missing == "issue"

    def test_passes_when_the_replacement_target_exists(self):
        source = '''
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("coach")
    _deprecation_warning("atdd archive <N>", "atdd coach transition <N> COMPLETE")
'''
        registry = build_deprecation_registry(source)
        subcommands = build_subcommand_registry(source)
        assert audit_c2b_no_dangling_replacement_target(registry, subcommands) == []

    def test_audits_callsites_not_the_deduped_registry(self):
        """A dangling callsite hidden by head-dedupe must still be caught.

        `build_deprecation_registry` keeps the FIRST callsite per head. With two
        `atdd update` callsites, the second — the one recommending the removed
        command — never reaches the registry. Auditing the registry would pass
        vacuously; auditing callsites catches it. This is the real shape of
        cli.py:2452 vs cli.py:2461.
        """
        source = '''
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("coach")
    _deprecation_warning("atdd update <N> --status <S>", "atdd coach transition <N> <TO>")
    _deprecation_warning("atdd update", "atdd issue")
'''
        subcommands = build_subcommand_registry(source)

        registry = build_deprecation_registry(source)
        assert "atdd issue" not in registry.get("atdd update", ""), (
            "precondition: the dedupe must hide the second callsite"
        )
        assert audit_c2b_no_dangling_replacement_target(registry, subcommands) == [], (
            "precondition: auditing the deduped registry misses it"
        )

        callsites = iter_deprecation_callsites(source)
        assert len(callsites) == 2
        violations = audit_c2b_no_dangling_replacement_target(callsites, subcommands)
        assert violations == [("atdd update", "atdd issue", "issue")]


class TestRealCliIsClean:
    """Against the REAL cli.py, after C5b: no `atdd issue` key, no `atdd issue` hint."""

    def test_registry_has_no_atdd_issue_key(self):
        registry = build_deprecation_registry()
        assert "atdd issue" not in registry, (
            "`atdd issue` must never be a C2 registry KEY — the shims used direct "
            "stderr prints for exactly this reason"
        )

    def test_no_surviving_hint_recommends_atdd_issue(self):
        registry = build_deprecation_registry()
        offenders = {
            old: new for old, new in registry.items() if "atdd issue" in new
        }
        assert not offenders, (
            "these deprecation hints still recommend the removed `atdd issue` "
            f"command: {offenders}"
        )

    def test_real_cli_has_no_dangling_replacement_targets(self):
        registry = build_deprecation_registry()
        subcommands = build_subcommand_registry()
        violations = audit_c2b_no_dangling_replacement_target(registry, subcommands)
        assert violations == [], (
            f"deprecation hints name commands that do not exist: {violations}"
        )

    def test_archive_and_close_wmbt_hints_name_their_coach_homes(self):
        registry = build_deprecation_registry()
        assert "coach transition" in registry.get("atdd archive", "")
        assert "coach close-wmbt" in registry.get("atdd close-wmbt", "")


class TestExistingAuditsStillPass:
    """The new audit is additive: C1 and the original C2 are untouched."""

    def test_c1_placeholder_audit_unchanged(self):
        assert audit_c1_placeholder_resolution("Fix: run atdd coach transition") == []
        assert audit_c1_placeholder_resolution("Fix: replace FOO") == []
        assert audit_c1_placeholder_resolution("do <thing> now") == ["thing"]

    def test_c2_contradiction_audit_still_flags_a_deprecated_key(self):
        registry = {"atdd update": "atdd coach transition <N> <TO>"}
        hit = audit_c2_no_deprecation_contradiction(
            "Fix: run atdd update 467 --status RED", registry
        )
        assert hit == ("atdd update", "atdd coach transition <N> <TO>")

    def test_c2_contradiction_audit_ignores_a_live_command(self):
        registry = {"atdd update": "atdd coach transition <N> <TO>"}
        assert (
            audit_c2_no_deprecation_contradiction(
                "Fix: run atdd coach transition 467 RED", registry
            )
            is None
        )

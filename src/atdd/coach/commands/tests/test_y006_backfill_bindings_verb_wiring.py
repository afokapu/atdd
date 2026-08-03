# URN: test:govern-lifecycle:bind-issue-feature:Y006-INTEGRATION-001-backfill-bindings-verb-wiring
# Acceptance: acc:govern-lifecycle:Y006-INTEGRATION-001-backfill-populates-null-bindings
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The backfill that Y006 requires is reachable as a sanctioned CLI verb, not only as a Python import, and the verb delegates to the shipped engine rather than reimplementing derivation.
"""#1689 — `atdd coach backfill-bindings` wiring.

DELEGATION-ONLY: #1635 shipped the engine
(``issue_feature_binding.backfill_feature_bindings``) and its own integration
suite (``validators/tests/test_y006_integration_001_...``). What it did not ship
was a way to RUN it: the rule
``coach.issue.feature-binding-must-resolve`` told operators to repair a backlog
by importing a Python dotted path by hand. These tests prove the wiring only —
never the derivation, which is the engine suite's job.

HERMETIC BY CONSTRUCTION: the engine is ALWAYS patched with a recording spy, so
no State Store is opened, no ``plan/`` is read and no work item is ever mutated.
The live store is shared with other agents; a wiring test must not touch it.

SCOPE NOTE (honest gap): Y006's acceptances were authored against the engine, so
none of them names the CLI surface. This test binds to the backfill acceptance
because the verb is the operator-facing half of "the backfill is run", but an
acceptance covering the command surface itself should be authored at PLANNED
rather than inferred from this file.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

_ENGINE = "atdd.coach.commands.issue_feature_binding.backfill_feature_bindings"


def _report(written=(), unresolved=()):
    from atdd.coach.commands.issue_feature_binding import BackfillReport

    return BackfillReport(written=tuple(written), unresolved=tuple(unresolved))


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so any leaked store write is contained."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# 1. The #1304 pattern: auto-discovery resolves the verb with zero shared edits
# ---------------------------------------------------------------------------
class TestBackfillBindingsVerbAutoDiscovery:
    def test_resolve_verb_finds_the_dropin(self):
        from atdd.coach.commands.coach_verbs import discover, resolve_verb
        from atdd.coach.commands.coach_verbs.backfill_bindings import (
            run as canonical_run,
        )

        assert resolve_verb("backfill-bindings") is canonical_run
        assert discover().get("backfill-bindings") is canonical_run

    def test_module_declares_the_hyphenated_verb_token(self):
        from atdd.coach.commands.coach_verbs import backfill_bindings

        assert backfill_bindings.VERB == "backfill-bindings"
        assert callable(backfill_bindings.run)


# ---------------------------------------------------------------------------
# 2. Delegation: the verb calls the shipped engine, and reimplements nothing
# ---------------------------------------------------------------------------
class TestBackfillBindingsDelegatesToTheEngine:
    def test_run_cli_reaches_the_engine_once_and_writes_by_default(self, hermetic):
        """`atdd coach backfill-bindings` routes through auto-discovery to the
        engine exactly once, in WRITE mode (dry_run=False) by default."""
        from atdd.coach.commands import coach

        spy = MagicMock(return_value=_report(written=(1630, 1453)))
        with patch(_ENGINE, spy):
            rc = coach.run_cli(["backfill-bindings"])

        assert rc == 0
        spy.assert_called_once_with(dry_run=False)

    def test_dry_run_flag_reaches_the_engine(self, hermetic):
        from atdd.coach.commands.coach_verbs.backfill_bindings import run

        spy = MagicMock(return_value=_report(written=(1630,)))
        with patch(_ENGINE, spy):
            rc = run(["--dry-run"])

        assert rc == 0
        spy.assert_called_once_with(dry_run=True)

    def test_verb_does_not_derive_bindings_itself(self, hermetic):
        """With the engine stubbed to write nothing, the verb reports nothing —
        proving it has no derivation path of its own to fall back on."""
        from atdd.coach.commands.coach_verbs.backfill_bindings import run

        with patch(_ENGINE, MagicMock(return_value=_report())) as spy:
            rc = run([])

        assert rc == 0
        spy.assert_called_once()


# ---------------------------------------------------------------------------
# 3. The report is honest about what it did and what it refused to guess
# ---------------------------------------------------------------------------
class TestBackfillBindingsReportsHonestly:
    def test_write_run_says_wrote_and_counts_both_sets(self, hermetic, capsys):
        from atdd.coach.commands.coach_verbs.backfill_bindings import run

        with patch(_ENGINE, MagicMock(return_value=_report((1630, 1453), (1183,)))):
            run([])

        out = capsys.readouterr().out
        assert "wrote 2 binding(s)" in out
        assert "would write" not in out, "a real run must not describe itself as a preview"
        assert "left NULL" in out and "1" in out

    def test_dry_run_says_would_write_not_wrote(self, hermetic, capsys):
        """The preview must never claim to have written — the defect family this
        repo keeps hitting is tools reporting success without acting."""
        from atdd.coach.commands.coach_verbs.backfill_bindings import run

        with patch(_ENGINE, MagicMock(return_value=_report((1630,), (1183,)))):
            run(["--dry-run"])

        out = capsys.readouterr().out
        assert "would write 1 binding(s)" in out
        assert "verify:" not in out, "a preview must not tell the operator to verify a write"

    def test_show_unresolved_lists_the_skipped_issue_numbers(self, hermetic, capsys):
        from atdd.coach.commands.coach_verbs.backfill_bindings import run

        with patch(_ENGINE, MagicMock(return_value=_report((), (1183, 963)))):
            run(["--show-unresolved"])

        out = capsys.readouterr().out
        assert "#1183" in out and "#963" in out

    def test_unresolved_are_not_listed_unless_asked(self, hermetic, capsys):
        from atdd.coach.commands.coach_verbs.backfill_bindings import run

        with patch(_ENGINE, MagicMock(return_value=_report((), (1183, 963)))):
            run([])

        out = capsys.readouterr().out
        assert "#1183" not in out
        assert "left NULL" in out, "the count must still be reported"

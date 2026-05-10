# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D004-UNIT-001-legacy-alias-triggers-call-site
# Acceptance: acc:judge-ambiguous-decisions:D004-UNIT-001-legacy-alias-triggers-call-site
# WMBT: wmbt:judge-ambiguous-decisions:D004
# Phase: GREEN
# Layer: unit
"""D004-UNIT-001 -- legacy alias triggers call site #6 precisely.

Per spec §6.7 / §6.9 #6 (and issue #524):

  * A Violation whose rule_id is a legacy alias whose canonical rule has
    ``superseded_by`` set fires call site #6.
  * A Violation whose rule_id is a canonical rule (even with superseded_by)
    does NOT fire call site #6.
  * A Violation whose rule_id is a legacy alias whose canonical has NO
    superseded_by does NOT fire call site #6.
  * Cache key is (legacy_alias, target_commit_sha) — repeated violations
    of the same alias on the same commit produce one judge call.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.utils.rule_binding import RuleMetadata, clear_cache

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_judge_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


@pytest.fixture(autouse=True)
def _isolate_rule_registry():
    clear_cache()
    yield
    clear_cache()


def _make_metadata(
    rule_id: str,
    aliases: tuple = (),
    superseded_by: str | None = None,
) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        severity=3,
        description="test rule",
        recipe=None,
        introduced_in=None,
        source_path=Path("/fake/convention.yaml"),
        disposition="strict",
        aliases=aliases,
        superseded_by=superseded_by,
    )


# ---------------------------------------------------------------------------
# Trigger predicate
# ---------------------------------------------------------------------------


class TestShouldFireSupersededRule:
    """``should_fire_superseded_rule`` fires only for legacy aliases
    whose canonical rule has superseded_by set."""

    def test_legacy_alias_with_superseded_by_fires(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import should_fire_superseded_rule

        meta = _make_metadata(
            "coder.dead-code.reachability",
            aliases=("DEAD-CODE-REACHABILITY-001",),
            superseded_by="coder.dead-code.reachability-v2",
        )
        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            violation = {"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "a.py:10"}
            result = should_fire_superseded_rule(violation, target_commit_sha="abc123")
        assert result is True

    def test_canonical_rule_with_superseded_by_does_not_fire(self, repo: Path):
        """A canonical rule_id (not an alias) with superseded_by is not
        a legacy-alias hit — call site #6 only fires on aliases."""
        from atdd.coach.commands.judge_call_sites import should_fire_superseded_rule

        meta = _make_metadata(
            "coder.dead-code.reachability",
            superseded_by="coder.dead-code.reachability-v2",
        )
        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            violation = {"rule_id": "coder.dead-code.reachability", "location": "a.py:10"}
            result = should_fire_superseded_rule(violation, target_commit_sha="abc123")
        assert result is False

    def test_legacy_alias_without_superseded_by_does_not_fire(self, repo: Path):
        """Legacy alias whose canonical has no superseded_by — the alias is
        still live, no migration needed."""
        from atdd.coach.commands.judge_call_sites import should_fire_superseded_rule

        meta = _make_metadata(
            "coder.dead-code.reachability",
            aliases=("DEAD-CODE-REACHABILITY-001",),
        )
        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            violation = {"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "a.py:10"}
            result = should_fire_superseded_rule(violation, target_commit_sha="abc123")
        assert result is False

    def test_plain_canonical_no_alias_no_superseded_by_does_not_fire(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import should_fire_superseded_rule

        meta = _make_metadata("coder.dead-code.reachability")
        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            violation = {"rule_id": "coder.dead-code.reachability", "location": "a.py:10"}
            result = should_fire_superseded_rule(violation, target_commit_sha="abc123")
        assert result is False


class TestCacheKeyDeduplication:
    """Repeated violations of the same alias on the same commit produce one
    judge call, not N."""

    def test_same_alias_same_commit_deduplicates(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            inputs_hash_for_superseded_rule,
            should_fire_superseded_rule,
        )

        meta = _make_metadata(
            "coder.dead-code.reachability",
            aliases=("DEAD-CODE-REACHABILITY-001",),
            superseded_by="coder.dead-code.reachability-v2",
        )
        v1 = {"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "a.py:10"}
        v2 = {"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "b.py:20"}
        sha = "abc123"

        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            assert should_fire_superseded_rule(v1, target_commit_sha=sha) is True
            assert should_fire_superseded_rule(v2, target_commit_sha=sha) is True

        # Same alias + same commit → same hash (dedup key)
        h1 = inputs_hash_for_superseded_rule(
            legacy_alias="DEAD-CODE-REACHABILITY-001",
            target_commit_sha=sha,
            canonical_rule_id="coder.dead-code.reachability",
        )
        h2 = inputs_hash_for_superseded_rule(
            legacy_alias="DEAD-CODE-REACHABILITY-001",
            target_commit_sha=sha,
            canonical_rule_id="coder.dead-code.reachability",
        )
        assert h1 == h2

    def test_same_alias_different_commit_different_hash(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import inputs_hash_for_superseded_rule

        h1 = inputs_hash_for_superseded_rule(
            legacy_alias="DEAD-CODE-REACHABILITY-001",
            target_commit_sha="aaa111",
            canonical_rule_id="coder.dead-code.reachability",
        )
        h2 = inputs_hash_for_superseded_rule(
            legacy_alias="DEAD-CODE-REACHABILITY-001",
            target_commit_sha="bbb222",
            canonical_rule_id="coder.dead-code.reachability",
        )
        assert h1 != h2

    def test_different_alias_same_commit_different_hash(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import inputs_hash_for_superseded_rule

        h1 = inputs_hash_for_superseded_rule(
            legacy_alias="DEAD-CODE-REACHABILITY-001",
            target_commit_sha="abc123",
            canonical_rule_id="coder.dead-code.reachability",
        )
        h2 = inputs_hash_for_superseded_rule(
            legacy_alias="OLD-LOGGING-RULE-007",
            target_commit_sha="abc123",
            canonical_rule_id="coder.logging.check",
        )
        assert h1 != h2


class TestNoJudgmentLineWhenPredicateDoesNotFire:
    """When the trigger predicate returns False, no judgments.jsonl line
    is appended for call site #6."""

    def test_canonical_no_superseded_by_no_judgment_line(self, repo: Path):
        from atdd.coach.commands import judge as judge_mod
        from atdd.coach.commands.judge_call_sites import invoke_superseded_rule_judge

        class _StubClient:
            def invoke(self, prompt: str):
                return {
                    "guidance": "migrate now",
                    "suggested_aliases": [],
                    "canonical_rule_id": "x",
                    "fix_hint": "fix it",
                }

        judge_mod.register_llm_client("stub-d004", lambda: _StubClient())

        meta = _make_metadata("coder.dead-code.reachability")
        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            result = invoke_superseded_rule_judge(
                violation={"rule_id": "coder.dead-code.reachability", "location": "a.py:10"},
                target_commit_sha="abc123",
                llm="stub-d004",
            )
        assert result["fired"] is False
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        assert not log.exists() or log.read_text().strip() == ""

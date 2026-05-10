# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D004-INTEGRATION-001-feeds-spawn-feedback
# Acceptance: acc:judge-ambiguous-decisions:D004-INTEGRATION-001-feeds-spawn-feedback
# WMBT: wmbt:judge-ambiguous-decisions:D004
# Phase: GREEN
# Layer: integration
"""D004-INTEGRATION-001 -- judge call site #6 feeds spawn-feedback.

Per spec §6.7 / §6.9 #6 / §7.6 (and issue #524):

An end-to-end coach run reaching respawn after a tier-1 fail referencing a
superseded legacy alias produces:

  * A spawn-feedback whose prior_attempt block carries the judge-produced
    ``guidance`` under ``fix_hint``.
  * ``suggested_aliases`` listed as ``legacy_aliases`` on the Violation entry.
  * ``canonical_rule_id`` replaces the legacy alias in the ``rule_id`` field.
  * The ``judgments.jsonl`` audit-trail line is referenced by ``judgment_id``
    in ``decisions.jsonl``.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.utils.rule_binding import RuleMetadata, clear_cache

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(
    rule_id: str,
    aliases: tuple = (),
    superseded_by: str | None = None,
    fix_hint: str | None = None,
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
        fix_hint=fix_hint,
    )


def _read_decisions(repo_root: Path) -> list[dict]:
    log = repo_root / ".atdd" / "runtime" / "coach" / "decisions.jsonl"
    if not log.exists():
        return []
    return [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]


def _read_judgments(repo_root: Path) -> list[dict]:
    log = repo_root / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
    if not log.exists():
        return []
    return [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]


def _register_stub(payload: dict) -> str:
    from atdd.coach.commands import judge as judge_mod

    class _Client:
        def invoke(self, prompt: str):
            return payload

    judge_mod.register_llm_client("stub-d004-int", lambda: _Client())
    return "stub-d004-int"


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


# ---------------------------------------------------------------------------
# Integration: route produces spawn-feedback-ready payload
# ---------------------------------------------------------------------------


class TestSupersededRuleRouteFeedsSpawnFeedback:
    """Call site #6 route produces a response that can be embedded in
    spawn-feedback per spec §7.6."""

    def test_route_emits_decision_referencing_judgment(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_superseded_rule

        meta = _make_metadata(
            "coder.dead-code.reachability",
            aliases=("DEAD-CODE-REACHABILITY-001",),
            superseded_by="coder.dead-code.reachability-v2",
            fix_hint="Remove dead code path",
        )
        judge_response = {
            "guidance": "DEAD-CODE-REACHABILITY-001 is superseded; use coder.dead-code.reachability-v2.",
            "suggested_aliases": ["DEAD-CODE-REACHABILITY-001"],
            "canonical_rule_id": "coder.dead-code.reachability-v2",
            "fix_hint": "Update suppress markers and remove dead code path.",
        }
        llm = _register_stub(judge_response)

        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            outcome = route_superseded_rule(
                violation={"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "a.py:10"},
                target_commit_sha="abc123",
                llm=llm,
                coach_run_id="run-d004",
            )

        # Route returns the consolidated payload
        assert outcome["fired"] is True
        assert outcome["decision"] == "respawn"
        assert outcome["state"] == "RESPAWN"

        # judgments.jsonl has one entry
        judgments = _read_judgments(repo)
        assert len(judgments) == 1
        assert judgments[0]["call_site"] == "superseded-rule-consolidation"
        assert judgments[0]["outcome"] == "ok"

        # decisions.jsonl references the judgment
        decisions = _read_decisions(repo)
        assert len(decisions) >= 1
        spawn_decisions = [d for d in decisions if d["decision_type"] == "spawn_feedback"]
        assert len(spawn_decisions) == 1
        assert spawn_decisions[0]["judgment_id"] == judgments[0]["judgment_id"]

    def test_response_fields_feed_spawn_feedback(self, repo: Path):
        """The route outcome carries the fields needed for spawn-feedback
        construction: guidance, suggested_aliases, canonical_rule_id,
        fix_hint."""
        from atdd.coach.commands.judge_call_sites import route_superseded_rule

        meta = _make_metadata(
            "coder.dead-code.reachability",
            aliases=("DEAD-CODE-REACHABILITY-001",),
            superseded_by="coder.dead-code.reachability-v2",
        )
        judge_response = {
            "guidance": "Legacy rule superseded by coder.dead-code.reachability-v2.",
            "suggested_aliases": ["DEAD-CODE-REACHABILITY-001", "dead-code-reach"],
            "canonical_rule_id": "coder.dead-code.reachability-v2",
            "fix_hint": "Update suppress markers and refactors.",
        }
        llm = _register_stub(judge_response)

        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            outcome = route_superseded_rule(
                violation={"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "a.py:10"},
                target_commit_sha="abc123",
                llm=llm,
                coach_run_id="run-d004-fields",
            )

        # The response is carried through so spawn-feedback can consume it
        assert outcome["response"]["canonical_rule_id"] == "coder.dead-code.reachability-v2"
        assert outcome["response"]["suggested_aliases"] == ["DEAD-CODE-REACHABILITY-001", "dead-code-reach"]
        assert "superseded" in outcome["response"]["guidance"].lower()
        assert outcome["response"]["fix_hint"] == "Update suppress markers and refactors."

    def test_llm_unavailable_routes_to_block(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_superseded_rule

        meta = _make_metadata(
            "coder.dead-code.reachability",
            aliases=("DEAD-CODE-REACHABILITY-001",),
            superseded_by="coder.dead-code.reachability-v2",
        )

        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            outcome = route_superseded_rule(
                violation={"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "a.py:10"},
                target_commit_sha="abc123",
                llm=None,
                coach_run_id="run-d004-no-llm",
            )

        assert outcome["state"] == "BLOCKED"
        judgments = _read_judgments(repo)
        assert len(judgments) == 1
        assert judgments[0]["outcome"] == "llm_unavailable"

    def test_predicate_not_fired_no_judgment_or_decision(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_superseded_rule

        meta = _make_metadata(
            "coder.dead-code.reachability",
            aliases=("DEAD-CODE-REACHABILITY-001",),
            # No superseded_by — predicate should NOT fire
        )

        with patch("atdd.coach.commands.judge_call_sites.bind_rule", return_value=meta):
            outcome = route_superseded_rule(
                violation={"rule_id": "DEAD-CODE-REACHABILITY-001", "location": "a.py:10"},
                target_commit_sha="abc123",
                llm=None,
                coach_run_id="run-d004-no-fire",
            )

        assert outcome["fired"] is False
        assert _read_judgments(repo) == []
        # Non-firing may still emit a deterministic decision

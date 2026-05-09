# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D005-UNIT-001-multi-pass-cross-llm-discipline
# Acceptance: acc:judge-ambiguous-decisions:D005-UNIT-001-multi-pass-cross-llm-discipline
# WMBT: wmbt:judge-ambiguous-decisions:D005
# Phase: RED
# Layer: application
"""D005-UNIT-001 — `atdd issue review` runs N independent passes by
distinct LLMs, fails loudly on `--passes < 2` (single-LLM bias
inadmissible per spec §6.10), fails loudly when `--passes > len(--llms)`,
and is idempotent under re-runs unless `--force` is supplied.

Spec §5.6 / §6.10. Per-pass files land at
``.atdd/runtime/issue-reviews/<N>/pass-<i>-<llm>.json``; pass `i` is
produced by ``--llms[i-1]`` so re-runs are reproducible (issue body
"pass identities are recorded").
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _conformant_dimensions() -> dict:
    """Stub LLM payload — every dimension `pass` with no findings."""
    return {
        "dimensions": {
            "systemic":          {"verdict": "pass", "findings": []},
            "ambiguities":       {"verdict": "pass", "findings": []},
            "gap":               {"verdict": "pass", "findings": []},
            "regression":        {"verdict": "pass", "findings": []},
            "comprehensiveness": {"verdict": "pass", "findings": []},
        }
    }


class _StubClient:
    def __init__(self, payload):
        self._payload = payload
        self.invocations = 0

    def invoke(self, prompt: str):
        self.invocations += 1
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture(autouse=True)
def _reset_registry():
    """Each test starts with a clean LLM registry so stubs do not leak."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


@pytest.fixture
def review_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        yaml.safe_dump({"version": "1.0"})
    )
    return tmp_path


def _register(name: str, payload):
    from atdd.coach.commands import judge as judge_mod

    def _factory():
        return _StubClient(payload)

    judge_mod.register_llm_client(name, _factory)


def _register_three_stubs():
    _register("claude-haiku", _conformant_dimensions())
    _register("gpt-5-mini",   _conformant_dimensions())
    _register("gemini-flash", _conformant_dimensions())


# ---------------------------------------------------------------------------
# AC-UNIT-001: three passes write three pass files
# ---------------------------------------------------------------------------


class TestThreePassesWriteThreeFiles:
    def test_three_passes_write_pass_files_under_runtime(
        self, review_workspace: Path
    ):
        from atdd.coach.commands.issue_review import run

        _register_three_stubs()

        rc = run(
            issue_number=358,
            passes=3,
            llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
        )
        assert rc == 0

        review_dir = review_workspace / ".atdd" / "runtime" / "issue-reviews" / "358"
        assert (review_dir / "pass-1-claude-haiku.json").exists()
        assert (review_dir / "pass-2-gpt-5-mini.json").exists()
        assert (review_dir / "pass-3-gemini-flash.json").exists()
        assert (review_dir / "aggregate.json").exists()

    def test_pass_file_records_identity_for_reproducibility(
        self, review_workspace: Path
    ):
        from atdd.coach.commands.issue_review import run

        _register_three_stubs()
        run(
            issue_number=42,
            passes=3,
            llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
        )

        path = review_workspace / ".atdd" / "runtime" / "issue-reviews" / "42" / "pass-2-gpt-5-mini.json"
        record = json.loads(path.read_text())
        assert record["pass_id"] == 2
        assert record["llm"] == "gpt-5-mini"
        assert record["issue"] == 42
        assert "timestamp" in record


# ---------------------------------------------------------------------------
# AC-UNIT-001: --passes < 2 fails loudly (single-LLM-once is inadmissible)
# ---------------------------------------------------------------------------


class TestPassesBelowMinimumFailsLoudly:
    def test_passes_one_exits_nonzero(
        self, review_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.issue_review import run

        _register("claude-haiku", _conformant_dimensions())
        rc = run(
            issue_number=1,
            passes=1,
            llms=["claude-haiku"],
        )
        assert rc != 0
        msg = (capsys.readouterr().err + capsys.readouterr().out).lower()
        # Test re-runs to capture twice if needed; fall through is fine.
        captured_msg = msg or ""
        # Re-capture to be safe after the first call.

    def test_passes_one_message_mentions_minimum_two(
        self, review_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.issue_review import run

        _register("claude-haiku", _conformant_dimensions())
        rc = run(
            issue_number=1,
            passes=1,
            llms=["claude-haiku"],
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "passes" in msg
        # Per spec §6.10 single-LLM is inadmissible — message should hint at the floor.
        assert "2" in msg or "two" in msg or "minimum" in msg

    def test_passes_zero_exits_nonzero(
        self, review_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.issue_review import run

        rc = run(
            issue_number=1,
            passes=0,
            llms=["claude-haiku", "gpt-5-mini"],
        )
        assert rc != 0


# ---------------------------------------------------------------------------
# AC-UNIT-001: --passes > len(--llms) fails loudly (insufficient distinct LLMs)
# ---------------------------------------------------------------------------


class TestInsufficientLlmsFailsLoudly:
    def test_passes_four_with_three_llms_exits_nonzero(
        self, review_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.issue_review import run

        _register_three_stubs()
        rc = run(
            issue_number=1,
            passes=4,
            llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
        )
        assert rc != 0
        captured = capsys.readouterr()
        msg = (captured.err + captured.out).lower()
        assert "llm" in msg
        assert "passes" in msg or "insufficient" in msg or "fewer" in msg

    def test_two_passes_with_one_llm_exits_nonzero(
        self, review_workspace: Path, capsys: pytest.CaptureFixture
    ):
        from atdd.coach.commands.issue_review import run

        _register("claude-haiku", _conformant_dimensions())
        rc = run(
            issue_number=1,
            passes=2,
            llms=["claude-haiku"],
        )
        assert rc != 0


# ---------------------------------------------------------------------------
# AC-UNIT-001: idempotency / --force semantics
# ---------------------------------------------------------------------------


class TestIdempotencyUnderForce:
    def test_without_force_existing_pass_files_are_reused(
        self, review_workspace: Path
    ):
        from atdd.coach.commands import judge as judge_mod
        from atdd.coach.commands.issue_review import run

        clients: dict[str, _StubClient] = {}

        def _make_factory(name: str):
            def _factory():
                client = _StubClient(_conformant_dimensions())
                clients.setdefault(name, client)
                return clients[name]
            return _factory

        for name in ("claude-haiku", "gpt-5-mini", "gemini-flash"):
            judge_mod.register_llm_client(name, _make_factory(name))

        rc = run(
            issue_number=358,
            passes=3,
            llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
        )
        assert rc == 0
        first_invocations = {n: c.invocations for n, c in clients.items()}
        assert all(v == 1 for v in first_invocations.values())

        # Re-run without --force — existing per-pass files should be reused
        # (no LLM invocations for already-produced passes).
        rc = run(
            issue_number=358,
            passes=3,
            llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
            force=False,
        )
        assert rc == 0
        second_invocations = {n: c.invocations for n, c in clients.items()}
        assert second_invocations == first_invocations

    def test_force_reruns_all_passes(self, review_workspace: Path):
        from atdd.coach.commands import judge as judge_mod
        from atdd.coach.commands.issue_review import run

        clients: dict[str, _StubClient] = {}

        def _make_factory(name: str):
            def _factory():
                client = _StubClient(_conformant_dimensions())
                clients.setdefault(name, client)
                return clients[name]
            return _factory

        for name in ("claude-haiku", "gpt-5-mini", "gemini-flash"):
            judge_mod.register_llm_client(name, _make_factory(name))

        run(
            issue_number=358,
            passes=3,
            llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
        )
        first = {n: c.invocations for n, c in clients.items()}
        assert all(v == 1 for v in first.values())

        run(
            issue_number=358,
            passes=3,
            llms=["claude-haiku", "gpt-5-mini", "gemini-flash"],
            force=True,
        )
        second = {n: c.invocations for n, c in clients.items()}
        assert all(second[n] == first[n] + 1 for n in first)


# ---------------------------------------------------------------------------
# AC-UNIT-001: argparse surface
# ---------------------------------------------------------------------------


class TestArgparseSurface:
    def test_parser_accepts_full_flag_surface(self):
        from atdd.coach.commands.issue_review import parse_cli

        cfg = parse_cli([
            "358",
            "--passes", "3",
            "--llms", "claude-haiku,gpt-5-mini,gemini-flash",
            "--dimensions", "systemic,ambiguities,gap,regression,comprehensiveness",
            "--show",
            "--force",
        ])
        assert cfg.issue_number == 358
        assert cfg.passes == 3
        assert cfg.llms == ["claude-haiku", "gpt-5-mini", "gemini-flash"]
        assert cfg.dimensions == [
            "systemic", "ambiguities", "gap", "regression", "comprehensiveness",
        ]
        assert cfg.show is True
        assert cfg.force is True

    def test_parser_defaults_match_spec(self):
        from atdd.coach.commands.issue_review import parse_cli

        cfg = parse_cli(["358"])
        # Defaults are pulled from coach config at run-time (not parser-time),
        # so the parser surfaces None for the optional knobs.
        assert cfg.issue_number == 358
        assert cfg.show is False
        assert cfg.force is False

    def test_parser_requires_issue_number(self):
        from atdd.coach.commands.issue_review import parse_cli

        with pytest.raises(SystemExit):
            parse_cli([])

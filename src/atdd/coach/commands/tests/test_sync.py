"""
Tests for AgentConfigSync (atdd sync).

Covers issue #457: extending the agent registry with GLM (z.ai) and
Mistral Vibe. The parametrized round-trip test (`test_every_agent_round_trips`)
iterates `AgentConfigSync.AGENT_FILES` so the test surface grows
automatically as new agents are added — catching future regressions
where a code path silently skips an agent.

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/commands/tests/test_sync.py -v
"""
from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync


def _make_sync(tmp_path: Path) -> AgentConfigSync:
    """Return a sync instance whose target dir is an empty tmp dir."""
    return AgentConfigSync(target_dir=tmp_path)


@pytest.mark.parametrize(
    ("agent", "filename"),
    sorted(AgentConfigSync.AGENT_FILES.items()),
)
def test_every_agent_round_trips(tmp_path: Path, agent: str, filename: str) -> None:
    """Every entry in AGENT_FILES must produce its config file with a managed block.

    Self-scaling: parametrized over the dict, so adding a new agent to
    AGENT_FILES automatically extends the test surface.
    """
    sync = _make_sync(tmp_path)
    rc = sync.sync(agents=[agent])
    assert rc == 0

    target = tmp_path / filename
    assert target.exists(), f"{filename} should be written for agent={agent}"

    content = target.read_text()
    assert AgentConfigSync.BLOCK_BEGIN in content
    assert AgentConfigSync.BLOCK_END in content


def test_glm_registered() -> None:
    """GLM (z.ai) must be in AGENT_FILES with the GLM.md filename."""
    assert AgentConfigSync.AGENT_FILES.get("glm") == "GLM.md"


def test_mistral_registered() -> None:
    """Mistral Vibe must be in AGENT_FILES with the MISTRAL.md filename."""
    assert AgentConfigSync.AGENT_FILES.get("mistral") == "MISTRAL.md"


def test_sync_glm_writes_managed_block(tmp_path: Path) -> None:
    sync = _make_sync(tmp_path)
    rc = sync.sync(agents=["glm"])
    assert rc == 0

    glm_md = tmp_path / "GLM.md"
    assert glm_md.exists()
    content = glm_md.read_text()
    assert AgentConfigSync.BLOCK_BEGIN in content
    assert AgentConfigSync.BLOCK_END in content


def test_sync_mistral_writes_managed_block(tmp_path: Path) -> None:
    sync = _make_sync(tmp_path)
    rc = sync.sync(agents=["mistral"])
    assert rc == 0

    mistral_md = tmp_path / "MISTRAL.md"
    assert mistral_md.exists()
    content = mistral_md.read_text()
    assert AgentConfigSync.BLOCK_BEGIN in content
    assert AgentConfigSync.BLOCK_END in content


def test_glm_overlay_applied(tmp_path: Path) -> None:
    """Overlay file src/atdd/coach/overlays/glm.md must be appended to GLM.md."""
    sync = _make_sync(tmp_path)
    sync.sync(agents=["glm"])
    content = (tmp_path / "GLM.md").read_text()
    assert "Agent-specific: glm" in content


def test_mistral_overlay_applied(tmp_path: Path) -> None:
    """Overlay file src/atdd/coach/overlays/mistral.md must be appended to MISTRAL.md."""
    sync = _make_sync(tmp_path)
    sync.sync(agents=["mistral"])
    content = (tmp_path / "MISTRAL.md").read_text()
    assert "Agent-specific: mistral" in content


def test_status_lists_all_six_agents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`atdd sync --status` must surface all 6 registered agents."""
    sync = _make_sync(tmp_path)
    rc = sync.status()
    assert rc == 0

    out = capsys.readouterr().out
    for agent in ("claude", "codex", "gemini", "qwen", "glm", "mistral"):
        assert agent in out, f"status output missing agent={agent}"


def test_unknown_agent_rejected(tmp_path: Path) -> None:
    """Unknown agent name must fail the sync call."""
    sync = _make_sync(tmp_path)
    rc = sync.sync(agents=["bogus"])
    assert rc == 1

from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync


K4_PERSONA_TEMPLATES = {
    "claude-code": "CLAUDE.md.tmpl",
    "codex": "AGENTS.md.tmpl",
    "gemini": "GEMINI.md.tmpl",
    "glm": "GLM.md.tmpl",
}

K4_OUTPUTS = {
    "claude": "CLAUDE.md",
    "codex": "AGENTS.md",
    "gemini": "GEMINI.md",
    "glm": "GLM.md",
}


@pytest.mark.parametrize(("llm", "template_name"), sorted(K4_PERSONA_TEMPLATES.items()))
def test_k4_persona_template_exists(tmp_path: Path, llm: str, template_name: str) -> None:
    sync = AgentConfigSync(target_dir=tmp_path)
    template = sync.templates_dir / "persona" / llm / template_name

    assert template.exists()


@pytest.mark.parametrize(("agent", "filename"), sorted(K4_OUTPUTS.items()))
def test_k4_sync_writes_persona_convention_file(tmp_path: Path, agent: str, filename: str) -> None:
    sync = AgentConfigSync(target_dir=tmp_path)

    assert sync.sync(agents=[agent]) == 0

    content = (tmp_path / filename).read_text()
    assert "<archetype>.<convention_short_name>.<rule_name>" in content
    assert "coder.dead-code.reachability" in content
    assert 'bind_rule("<canonical_id>")' in content
    assert "validators MUST call `bind_rule` at module-import time" in content
    assert "named rule MUST exist in a convention's `rules:` block" in content
    assert "SPEC-COACH-RULEID-0007" in content

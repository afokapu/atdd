from pathlib import Path

import pytest

from atdd.coach.commands.sync import AgentConfigSync


K4_PERSONA_TEMPLATES = {
    "claude-code": "CLAUDE.md.tmpl",
    "codex": "CONDUCTOR.md.tmpl",
    "gemini": "GEMINI.md.tmpl",
    "glm": "GLM.md.tmpl",
}

K4_OUTPUTS = {
    "claude": "CLAUDE.md",
    "codex": "CONDUCTOR.md",
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


# --- P001-UNIT-002: idempotent rerun (zero diff) ---


@pytest.mark.parametrize("agent", sorted(K4_OUTPUTS.keys()))
def test_k4_sync_idempotent_rerun_no_diff(tmp_path: Path, agent: str) -> None:
    """Second sync against unchanged templates produces zero file changes."""
    sync = AgentConfigSync(target_dir=tmp_path)
    filename = K4_OUTPUTS[agent]

    sync.sync(agents=[agent])
    first_content = (tmp_path / filename).read_text()

    sync2 = AgentConfigSync(target_dir=tmp_path)
    sync2.sync(agents=[agent])
    second_content = (tmp_path / filename).read_text()

    assert first_content == second_content


def test_k4_sync_stable_ordering_across_runs(tmp_path: Path) -> None:
    """Rule-ids, conventions, and sections appear in stable order across runs."""
    agents = sorted(K4_OUTPUTS.keys())
    sync = AgentConfigSync(target_dir=tmp_path)

    sync.sync(agents=agents)

    first_contents = {a: (tmp_path / K4_OUTPUTS[a]).read_text() for a in agents}

    sync2 = AgentConfigSync(target_dir=tmp_path)
    sync2.sync(agents=agents)

    for agent in agents:
        assert (tmp_path / K4_OUTPUTS[agent]).read_text() == first_contents[agent]


# --- P001-UNIT-001: hand-edit preservation ---


def test_k4_sync_preserves_hand_edits_outside_managed_region(tmp_path: Path) -> None:
    """Content outside ATDD:BEGIN/END managed region is preserved verbatim."""
    sync = AgentConfigSync(target_dir=tmp_path)

    # First sync creates the file
    sync.sync(agents=["claude"])

    # Add hand-edited content before and after the managed block
    file_path = tmp_path / "CLAUDE.md"
    original = file_path.read_text()
    hand_edit_prefix = "# My custom keybindings\nbind ctrl+s save\n\n"
    hand_edit_suffix = "\n# End of my custom notes\n"
    modified = hand_edit_prefix + original + hand_edit_suffix
    file_path.write_text(modified)

    # Re-sync
    sync2 = AgentConfigSync(target_dir=tmp_path)
    sync2.sync(agents=["claude"])

    result = file_path.read_text()
    assert result.startswith(hand_edit_prefix)
    assert result.endswith(hand_edit_suffix)


def test_k4_sync_preserves_hand_edits_for_all_agents(tmp_path: Path) -> None:
    """Hand-edit preservation works for all four LLM targets."""
    for agent, filename in K4_OUTPUTS.items():
        sync = AgentConfigSync(target_dir=tmp_path)
        sync.sync(agents=[agent])

        file_path = tmp_path / filename
        original = file_path.read_text()
        note = f"\n# Custom note for {agent}\n"
        file_path.write_text(original + note)

        sync2 = AgentConfigSync(target_dir=tmp_path)
        sync2.sync(agents=[agent])

        assert file_path.read_text().endswith(note)


# --- P001-UNIT-001: template-change propagation ---


def test_k4_sync_propagates_template_change(tmp_path: Path) -> None:
    """When a template changes, sync regenerates the file to reflect it."""
    sync = AgentConfigSync(target_dir=tmp_path)

    sync.sync(agents=["claude"])
    original = (tmp_path / "CLAUDE.md").read_text()

    # Modify the claude-code persona template
    template_path = sync.templates_dir / "persona" / "claude-code" / "CLAUDE.md.tmpl"
    original_template = template_path.read_text()
    modified_template = original_template + "\n## New Section\nAdded by test.\n"

    try:
        template_path.write_text(modified_template)

        sync2 = AgentConfigSync(target_dir=tmp_path)
        sync2.sync(agents=["claude"])
        updated = (tmp_path / "CLAUDE.md").read_text()

        assert "## New Section" in updated
        assert "Added by test." in updated
        assert updated != original
    finally:
        template_path.write_text(original_template)


def test_k4_sync_first_run_creates_all_four_files(tmp_path: Path) -> None:
    """First sync creates all four per-LLM files from templates."""
    sync = AgentConfigSync(target_dir=tmp_path)

    agents = sorted(K4_OUTPUTS.keys())
    sync.sync(agents=agents)

    for agent, filename in K4_OUTPUTS.items():
        assert (tmp_path / filename).exists(), f"{filename} not created"
        content = (tmp_path / filename).read_text()
        assert "# --- ATDD:BEGIN" in content
        assert "# --- ATDD:END" in content
        assert "Per-LLM convention context" in content

# URN: test:integration-hardening:coach-single-command-driver:pretooluse-settings-wiring
# Issue: #1454 (wire the PreToolUse prohibition guard)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""The PreToolUse guard must actually be WIRED, and single-sourced (#1454).

CLAUDE.md declares a prohibition list (``gh issue create``, ``gh pr create``)
because those bypass the store-first authoring path and the label-scoped
validators.  The classifier and the ``claude-pre-tool-use.sh`` hook that
enforce it have existed since #668 and work correctly — but ``PreToolUse``
appeared in **no** settings file, so Claude Code never invoked the hook.  The
guard was dead code; an agent violated the prohibition in this repo on
2026-07-11 and nothing stopped it (#1430).

These tests pin the two properties that were missing:

  1. **Wiring** — ``atdd init`` / ``atdd sync`` install the hook into the
     *project's* ``.claude/settings.json`` (project-scoped, so it travels with
     the repo and binds every agent working in it), idempotently and without
     destroying operator-authored settings.

  2. **Single source of truth** — the prohibition list lives in exactly one
     place, ``forbidden_commands.convention.yaml``.  Adding a prohibition must
     not require editing two files, so the agent-facing CONDUCTOR.md template
     must point at that registry rather than carry a hand-copied second copy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.initializer import ProjectInitializer
from atdd.coach.commands.sync import AgentConfigSync


pytestmark = [pytest.mark.coach]

_PACKAGE_ROOT = Path(ProjectInitializer(Path.cwd()).package_root)
_CONDUCTOR_MD = _PACKAGE_ROOT / "templates" / "CONDUCTOR.md"
_REGISTRY = _PACKAGE_ROOT / "conventions" / "forbidden_commands.convention.yaml"

_HOOK_BASENAME = "claude-pre-tool-use.sh"


def _project(tmp_path: Path) -> Path:
    """Create a minimal initialised project directory."""
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _pretooluse_commands(settings: dict) -> list:
    """Return every PreToolUse hook command string in *settings*."""
    groups = settings.get("hooks", {}).get("PreToolUse", [])
    return [
        hook.get("command", "")
        for group in groups
        for hook in group.get("hooks", [])
    ]


# ---------------------------------------------------------------------------
# 1. Wiring
# ---------------------------------------------------------------------------


def test_installer_wires_pretooluse_into_project_settings(tmp_path: Path) -> None:
    """The installer creates .claude/settings.json with a PreToolUse entry."""
    project = _project(tmp_path)

    ProjectInitializer(project).install_claude_pretooluse_hook()

    settings_path = project / ".claude" / "settings.json"
    assert settings_path.is_file(), "no .claude/settings.json was written"

    commands = _pretooluse_commands(json.loads(settings_path.read_text()))
    assert any(_HOOK_BASENAME in c for c in commands), (
        f"PreToolUse does not invoke {_HOOK_BASENAME}: {commands!r}"
    )


def test_installer_also_installs_the_hook_script_it_points_at(tmp_path: Path) -> None:
    """The wiring must not point at a file that does not exist."""
    project = _project(tmp_path)

    ProjectInitializer(project).install_claude_pretooluse_hook()

    hook = project / ".atdd" / "hooks" / _HOOK_BASENAME
    assert hook.is_file(), f"settings.json points at a missing hook: {hook}"
    assert hook.stat().st_mode & 0o111, "installed hook is not executable"


def test_wiring_is_idempotent_and_preserves_operator_settings(tmp_path: Path) -> None:
    """Re-running never duplicates the entry, and operator keys survive."""
    project = _project(tmp_path)
    settings_path = project / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"model": "opus", "hooks": {}}))

    initializer = ProjectInitializer(project)
    initializer.install_claude_pretooluse_hook()
    initializer.install_claude_pretooluse_hook()

    settings = json.loads(settings_path.read_text())

    assert settings.get("model") == "opus", "operator settings were clobbered"

    guard_commands = [c for c in _pretooluse_commands(settings) if _HOOK_BASENAME in c]
    assert len(guard_commands) == 1, (
        f"expected exactly one guard entry after two installs, got {guard_commands!r}"
    )


def test_sync_installs_the_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`atdd sync` must wire the guard (not just `atdd init`)."""
    project = _project(tmp_path)
    calls: list = []
    monkeypatch.setattr(
        ProjectInitializer,
        "install_claude_pretooluse_hook",
        lambda self: calls.append(self.target_dir),
    )

    AgentConfigSync(project).sync(agents=["claude"])

    assert calls, "atdd sync did not install the PreToolUse guard"


# ---------------------------------------------------------------------------
# 2. Single source of truth
# ---------------------------------------------------------------------------


def _conductor_frontmatter() -> dict:
    """Parse the YAML frontmatter block out of CONDUCTOR.md."""
    text = _CONDUCTOR_MD.read_text()
    _, _, rest = text.partition("---\n")
    body, _, _ = rest.partition("\n---")
    return yaml.safe_load(body)


def test_adding_a_prohibition_requires_only_the_registry(tmp_path: Path) -> None:
    """The classifier holds no hard-coded copy — the registry alone drives it.

    This is the load-bearing single-source proof: a prohibition that exists
    *only* in a registry is enforced, with no code change anywhere.  If the
    classifier carried its own list, a novel rule would not block.
    """
    from atdd.coach.utils.forbidden_command_classifier import classify

    registry = tmp_path / "forbidden_commands.convention.yaml"
    registry.write_text(yaml.safe_dump({
        "patterns": [{
            "id": "ATDD-FORBID-NOVEL-RULE",
            "match_type": "hard_block",
            "match": {"contains": "terraform destroy"},
            "reason": "invented for this test; exists in no source file",
            "alternative": "atdd infra teardown <env>",
        }],
    }))

    decision = classify(
        "terraform destroy -auto-approve",
        repo_root=tmp_path,
        convention_path=registry,
    )

    assert decision.action == "block", (
        "a registry-only prohibition was not enforced — the classifier is not "
        "registry-driven, so the prohibition list is duplicated in code"
    )
    assert decision.alternative == "atdd infra teardown <env>", (
        "the block message must name the replacement from the registry"
    )


def test_conductor_md_points_at_the_registry_instead_of_copying_it() -> None:
    """The agent-facing template must not hand-copy the prohibition list.

    The registry drives enforcement.  A second, hand-maintained copy in
    CONDUCTOR.md means adding a prohibition takes two edits — and the copies
    drift silently.  The template carries a pointer instead.
    """
    conductor = _CONDUCTOR_MD.read_text()
    assert "forbidden_commands.convention.yaml" in conductor, (
        "CONDUCTOR.md does not point at the canonical prohibition registry"
    )

    prohibited = _conductor_frontmatter()["issues"].get("prohibited_commands")
    assert not isinstance(prohibited, list), (
        "CONDUCTOR.md still carries a hand-maintained prohibited_commands LIST "
        f"({prohibited!r}). That is the second copy. Adding a prohibition must "
        f"require editing ONE file ({_REGISTRY.name}). Leave a pointer here."
    )


def test_registry_is_the_one_place_the_prohibitions_live() -> None:
    """The prohibitions the issue names are actually IN the canonical registry.

    Asserted against the *trigger phrase* rather than a specific match form, so
    the registry stays free to express a rule as an argv run (#1454) or as a
    substring without this test having to be rewritten.
    """
    registry = yaml.safe_load(_REGISTRY.read_text())
    triggers = set()
    for pattern in registry["patterns"]:
        if pattern.get("match_type") != "hard_block":
            continue
        match = pattern.get("match", {})
        if "argv" in match:
            triggers.add(" ".join(match["argv"]))
        elif "contains" in match:
            triggers.add(match["contains"])

    assert {"gh issue create", "gh pr create"} <= triggers, (
        f"the prohibitions CLAUDE.md declares are missing from {_REGISTRY.name}: "
        f"{triggers!r}"
    )

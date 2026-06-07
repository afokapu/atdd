# URN: test:govern-lifecycle:registry-build-honors-declared-code-roots:E044-UNIT-001-toolkit-only-config-creates-no-game-template-stub-dirs
# Acceptance: acc:govern-lifecycle:E044-UNIT-001-toolkit-only-config-creates-no-game-template-stub-dirs
# WMBT: wmbt:govern-lifecycle:E044
# Phase: GREEN
"""acc:govern-lifecycle:E044-UNIT-001 — a repo declaring only a non-default code
root (``code.toolkit: src/atdd``) gets NO python/, supabase/ or telemetry/ stub
dirs from a registry build.

RED state: RegistryBuilder.build_all always calls build_coder / build_supabase /
build_telemetry, each of which mkdir()s its mirror dir even when the repo ships
no sources and declares no such root — so python/, supabase/ and telemetry/ are
materialized as stray stubs. This test fails until build_all gates code-root
mirror materialization on the repo's explicitly-declared ``code:`` block (#984).
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path

import yaml

from atdd.coach.commands.registry import RegistryBuilder


def _make_repo(root: Path, code_block: dict) -> Path:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text(
        yaml.safe_dump({"version": "1.0", "code": code_block}, sort_keys=False),
        encoding="utf-8",
    )
    return root


def test_toolkit_only_config_creates_no_game_template_stub_dirs(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"toolkit": "src/atdd"})
    builder = RegistryBuilder(repo)

    with contextlib.redirect_stdout(io.StringIO()):
        builder.build_all(mode="apply")

    assert not (repo / "python").exists(), (
        "build_all stubbed a python/ dir into a repo that declares only "
        "code.toolkit — the game-template DEFAULT_CODE_ROOTS must not be forced."
    )
    assert not (repo / "supabase").exists(), (
        "build_all stubbed a supabase/ dir into a repo that declares only "
        "code.toolkit — the game-template DEFAULT_CODE_ROOTS must not be forced."
    )
    assert not (repo / "telemetry").exists(), (
        "build_all stubbed a telemetry/ dir into a repo with no telemetry "
        "sources and no telemetry declaration."
    )


def test_e044_rule_binds_via_repo_walker() -> None:
    """The WMBT acceptance derives a registry-walkable rule resolvable by bind_rule."""
    from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

    rule_id = "repo.govern-lifecycle.E044-acc-unit-001"
    try:
        meta = bind_rule(rule_id)
    except RuleNotInRegistryError as exc:  # pragma: no cover - failure path
        raise AssertionError(
            f"bind_rule({rule_id!r}) did not resolve: {exc}. The E044 WMBT "
            "acceptance must derive this rule via the repo-rule walker."
        )
    assert meta.rule_id == rule_id

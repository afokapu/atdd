# URN: test:govern-providers:D001-UNIT-006-per-repo-interlocking-layout-emitted-to-provider
# Acceptance: acc:govern-providers:D001-UNIT-006-per-repo-interlocking-layout-emitted-to-provider
# WMBT: wmbt:govern-providers:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""Unit proof that a repo's declared interlocking layout reaches the detector (#1595).

The train-interlocking detector resolves its scan surfaces with precedence:
(1) env ``ATDD_INTERLOCKING_LAYOUT`` = JSON ``{selector_id: [globs]}`` →
(2) the extension's scope selectors → (3) hardcoded defaults. Core owns ONLY
step (1): when a repo declares an ``interlocking_layout`` block on the existing
``.atdd/config.yaml`` surface, the runner sets that env var on the provider
subprocess for a ``coder.train.interlocking-*`` rule — and NOTHING otherwise, so
the detector falls back on its own.

We capture ``subprocess.run`` to inspect the exact env the runner would pass,
without executing the provider (mirrors the D001-UNIT-003 subprocess proof).
"""
from __future__ import annotations

import json
from pathlib import Path

from atdd.enforce import runner as runner_mod
from atdd.enforce.conventions import resolve_interlocking_layout
from atdd.enforce.resolution import ResolvedProvider


class _FakeCompleted:
    returncode = 0
    stdout = "[]"
    stderr = ""


def _provider(tmp_path: Path) -> ResolvedProvider:
    cli_path = tmp_path / "cli" / "scan.py"
    cli_path.parent.mkdir(parents=True, exist_ok=True)
    cli_path.write_text("", encoding="utf-8")
    return ResolvedProvider(
        workspace_id="atdd.workspace.python-pytest",
        provider_cli_path=cli_path,
        contract_version="1.1.0",
    )


_LAYOUT = {
    "interlocking_yaml": ["plan/_trains/_interlockings/*.yaml"],
    "e2e_tests": ["e2e/**/*.py"],
}


def _capture_env(monkeypatch) -> dict:
    captured: dict = {}

    def _fake_run(argv, **kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        return _FakeCompleted()

    monkeypatch.setattr(runner_mod.subprocess, "run", _fake_run)
    return captured


def test_declared_layout_is_emitted_for_an_interlocking_rule(monkeypatch, tmp_path: Path) -> None:
    """WITH an ``interlocking_layout`` block → the env carries the exact JSON."""
    captured = _capture_env(monkeypatch)

    layout = resolve_interlocking_layout({"interlocking_layout": _LAYOUT})
    runner_mod._invoke_provider(
        _provider(tmp_path),
        "coder.train.interlocking-runner-exists",
        scan_roots=[str(tmp_path)],
        scan_excludes=[],
        interlocking_layout=layout,
    )

    env = captured["env"]
    assert "ATDD_INTERLOCKING_LAYOUT" in env
    assert json.loads(env["ATDD_INTERLOCKING_LAYOUT"]) == _LAYOUT


def test_no_layout_declared_means_env_var_is_absent(monkeypatch, tmp_path: Path) -> None:
    """WITHOUT a block → the env var is never set (detector falls back)."""
    captured = _capture_env(monkeypatch)

    layout = resolve_interlocking_layout({})  # no interlocking_layout key
    assert layout is None
    runner_mod._invoke_provider(
        _provider(tmp_path),
        "coder.train.interlocking-runner-exists",
        scan_roots=[str(tmp_path)],
        scan_excludes=[],
        interlocking_layout=layout,
    )

    assert "ATDD_INTERLOCKING_LAYOUT" not in captured["env"]


def test_layout_is_scoped_to_interlocking_rules_only(monkeypatch, tmp_path: Path) -> None:
    """The env must never leak onto an unrelated (non-interlocking) rule subprocess.

    ``enforce`` only resolves the layout for a ``coder.train.interlocking-*`` rule;
    a non-interlocking rule is invoked with ``interlocking_layout=None`` and so its
    subprocess carries no such env, even in a repo that declares the block.
    """
    captured = _capture_env(monkeypatch)

    runner_mod._invoke_provider(
        _provider(tmp_path),
        "coder.logging.print",
        scan_roots=[str(tmp_path)],
        scan_excludes=[],
        interlocking_layout=None,
    )

    assert "ATDD_INTERLOCKING_LAYOUT" not in captured["env"]


def test_resolver_reads_the_existing_config_surface_and_normalizes(tmp_path: Path) -> None:
    """The reader consumes the top-level ``interlocking_layout`` key of the config
    ``load_config`` already parses; unknown selector ids are dropped."""
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        "interlocking_layout:\n"
        "  interlocking_yaml: ['plan/_trains/_interlockings/*.yaml']\n"
        "  not_a_selector: ['nope/**']\n",
        encoding="utf-8",
    )
    config = runner_mod.load_config(tmp_path)
    layout = resolve_interlocking_layout(config)

    assert layout == {"interlocking_yaml": ["plan/_trains/_interlockings/*.yaml"]}

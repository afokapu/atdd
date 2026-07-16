# URN: test:govern-providers:D001-UNIT-003-runner-invokes-provider-by-subprocess-never-imports
# Acceptance: acc:govern-providers:D001-UNIT-003-runner-invokes-provider-by-subprocess-never-imports
# WMBT: wmbt:govern-providers:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:D001-UNIT-003-runner-invokes-provider-by-subprocess-never-imports.

The runner reaches the resolved provider only by launching it as a subprocess
(``python <cli/scan.py>``), never by importing provider code — the V5 boundary.
Capturing ``subprocess.run`` lets us inspect the exact argv the runner launches
without executing it, and prove it is a script invocation, not an import.
"""
from __future__ import annotations

import sys
from pathlib import Path

from atdd.enforce import runner as runner_mod
from atdd.enforce.resolution import ResolvedProvider


class _FakeCompleted:
    returncode = 0
    stdout = "[]"
    stderr = ""


def test_runner_invokes_provider_by_subprocess_never_imports(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        return _FakeCompleted()

    monkeypatch.setattr(runner_mod.subprocess, "run", _fake_run)

    cli_path = tmp_path / "cli" / "scan.py"
    cli_path.parent.mkdir(parents=True)
    cli_path.write_text("", encoding="utf-8")
    provider = ResolvedProvider(
        workspace_id="atdd.workspace.python-pytest",
        provider_cli_path=cli_path,
        contract_version="1.1.0",
    )

    runner_mod._invoke_provider(
        provider,
        "coder.demo.rule",
        scan_roots=[str(tmp_path)],
        scan_excludes=[],
    )

    argv = captured["argv"]
    # The provider is SPAWNED as a subprocess: python <cli/scan.py>, not imported.
    assert argv[0] == sys.executable
    assert argv[1] == str(cli_path)

    # No vendored provider module was imported into the process by reaching the
    # provider — the only modules loaded from a substrate tree would live under a
    # ``.atdd`` path, and reaching a provider never adds one.
    assert not any(
        getattr(m, "__file__", None) and f"{Path('.atdd')}" in str(m.__file__)
        for m in list(sys.modules.values())
    )

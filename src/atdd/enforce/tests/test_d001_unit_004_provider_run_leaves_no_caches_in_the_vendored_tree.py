# URN: test:govern-providers:D001-UNIT-004-provider-run-leaves-no-caches-in-the-vendored-tree
# Acceptance: acc:govern-providers:D001-UNIT-004-provider-run-leaves-no-caches-in-the-vendored-tree
# WMBT: wmbt:govern-providers:D001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:D001-UNIT-004-provider-run-leaves-no-caches-in-the-vendored-tree.

Reaching a provider must leave the vendored tree byte-identical. The real
python-pytest provider CLI imports its sibling adapter modules and then
subprocesses ``python -m pytest`` over a test file INSIDE the vendored tree —
both writes land in that tree (``__pycache__/`` beside every imported module,
``.pytest_cache/`` at the resolved rootdir), mutating a digest-locked substrate
core is only supposed to read. That is what turned a plain ``atdd enforce`` run
into a false ``[TAMPERED]`` from ``--verify-substrate`` (#1603).

The stand-in provider CLI below reproduces exactly that shape, so the pollution
is REAL rather than asserted about. The control run — the same tree with the
runner's cache-suppressing env removed — proves the harness can see the
pollution, so the passing assertion is not vacuous.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from atdd.enforce import runner as runner_mod
from atdd.enforce.resolution import ResolvedProvider

# A provider CLI with the real adapter's write surface: it IMPORTS a sibling
# module from the vendored tree (→ __pycache__/) and SUBPROCESSES pytest over a
# test file in that tree, rooted there (→ .pytest_cache/).
_POLLUTING_PROVIDER_CLI = '''\
import json, subprocess, sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WS / "adapter"))
import sibling  # noqa: F401  — the import that deposits adapter/__pycache__/

subprocess.run(
    [sys.executable, "-m", "pytest", "-q", str(_WS / "tests" / "test_probe.py")],
    cwd=str(_WS),
    capture_output=True,
    text=True,
)
json.dump([], sys.stdout)
'''


def _vendor_provider(tmp_path: Path) -> ResolvedProvider:
    """Vendor a workspace tree whose provider CLI writes caches the way the real one does."""
    ws = tmp_path / ".atdd" / "workspaces" / "atdd.workspace.python-pytest" / "0.1.0"
    (ws / "cli").mkdir(parents=True)
    (ws / "adapter").mkdir(parents=True)
    (ws / "tests").mkdir(parents=True)

    (ws / "cli" / "scan.py").write_text(_POLLUTING_PROVIDER_CLI, encoding="utf-8")
    (ws / "adapter" / "sibling.py").write_text("VALUE = 1\n", encoding="utf-8")
    (ws / "tests" / "test_probe.py").write_text(
        "def test_probe():\n    assert True\n", encoding="utf-8"
    )
    # Roots pytest INSIDE the vendored tree, so its cache dir would land there —
    # the case a repo-root rootdir would otherwise hide.
    (ws / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

    return ResolvedProvider(
        workspace_id="atdd.workspace.python-pytest",
        provider_cli_path=ws / "cli" / "scan.py",
        contract_version="1.1.0",
    )


def _generated_caches(ws: Path) -> set[str]:
    return {
        str(p.relative_to(ws))
        for p in ws.rglob("*")
        if p.name in ("__pycache__", ".pytest_cache") or p.suffix in (".pyc", ".pyo")
    }


def _drive(provider: ResolvedProvider, consumer: Path) -> None:
    runner_mod._invoke_provider(
        provider,
        "acme.rule.owned",
        scan_roots=[str(consumer)],
        scan_excludes=[],
    )


def test_provider_run_leaves_no_caches_in_the_vendored_tree(tmp_path, monkeypatch) -> None:
    provider = _vendor_provider(tmp_path)
    ws = provider.provider_cli_path.parent.parent
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "app.py").write_text("x = 1\n", encoding="utf-8")

    pristine = {str(p.relative_to(ws)) for p in ws.rglob("*")}

    # CONTROL — the same run WITHOUT the runner's cache-suppressing env. If this
    # tree stays clean the assertion below proves nothing, so fail loudly here.
    monkeypatch.setattr(runner_mod, "_cache_suppressing_env", dict)
    _drive(provider, consumer)
    polluted = _generated_caches(ws)
    assert polluted, (
        "control run deposited no caches — the harness cannot observe the pollution "
        "this test exists to rule out"
    )
    assert any(name.endswith("__pycache__") for name in polluted)
    assert any(".pytest_cache" in name for name in polluted)

    # Reset the tree to pristine before the real run.
    for name in ("adapter/__pycache__", ".pytest_cache", "tests/__pycache__"):
        shutil.rmtree(ws / name, ignore_errors=True)
    assert not _generated_caches(ws)

    # SHIPPED — the runner's env keeps every one of those writes out of the tree.
    monkeypatch.undo()
    _drive(provider, consumer)

    assert _generated_caches(ws) == set()
    assert {str(p.relative_to(ws)) for p in ws.rglob("*")} == pristine

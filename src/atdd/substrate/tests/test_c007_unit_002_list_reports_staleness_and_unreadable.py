# URN: test:admit-substrate:substrate-admission:C007-UNIT-002-list-reports-staleness-and-unreadable
# Acceptance: acc:admit-substrate:C007-UNIT-002-list-reports-staleness-and-unreadable
# WMBT: wmbt:admit-substrate:C007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C007-UNIT-002 — `atdd substrate list` reports staleness, and never reports a
configured-but-unreadable registry as clean (#1878).

Placed on `substrate list` rather than `atdd doctor`: doctor diagnoses the local
Python ENVIRONMENT (interpreter, import paths, git-hook python), already prints
two unrelated FAILs on a clean worktree, and exits 0 regardless. Substrate
currency is not an environment fact. `list` already reads the lock and the same
module already reads registries, so both halves of the comparison were here.

The load-bearing case is the third: a registry that is CONFIGURED but cannot be
read must not look like a registry that publishes nothing. `_load_registry_entries`
returns `[]` for both, which is the silent-pass shape this repo hit three times in
one day (#1818, #1867, #1876).
"""
from __future__ import annotations

import pathlib

import yaml

from atdd.substrate import commands


def _repo(tmp_path: pathlib.Path, *, installed_version: str, registry_index: object) -> pathlib.Path:
    """A repo with one admitted package and, optionally, a configured registry.

    ``registry_index`` is the index payload, ``"missing"`` for a configured
    registry whose file is absent, or ``None`` for no registry at all.
    """
    root = tmp_path / "repo"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "substrate.lock.yaml").write_text(yaml.safe_dump({
        "schema_version": "1.0.0",
        "artifacts": [{
            "id": "demo.ext", "kind": "extension", "version": installed_version,
            "digest": "sha256:" + "0" * 64,
            "installed_path": ".atdd/extensions/demo.ext/" + installed_version,
            "enabled": True, "workspaces": [],
        }]
    }, sort_keys=False), encoding="utf-8")
    intent: dict = {}
    if registry_index is not None:
        reg_dir = tmp_path / "reg"
        reg_dir.mkdir(exist_ok=True)
        if registry_index != "missing":
            (reg_dir / "index.yaml").write_text(yaml.safe_dump(registry_index), encoding="utf-8")
        intent["registries"] = [
            {"name": "hub", "type": "path", "source": str(reg_dir), "path": "index.yaml"}
        ]
    (root / ".atdd" / "substrate.yaml").write_text(yaml.safe_dump(intent), encoding="utf-8")
    return root


def _index(latest: str) -> dict:
    return {"schema_version": "1.0.0", "entries": [
        {"id": "demo.ext", "kind": "extension", "latest_version": latest}
    ]}


def test_a_stale_package_is_marked_and_the_remedy_named(tmp_path, capsys):
    root = _repo(tmp_path, installed_version="0.1.0", registry_index=_index("0.4.0"))
    commands.run_list(project_root=root)
    out = capsys.readouterr().out
    assert "[stale -> 0.4.0]" in out
    assert "atdd substrate add" in out, "a report naming no remedy is not actionable"


def test_a_current_package_adds_no_noise(tmp_path, capsys):
    root = _repo(tmp_path, installed_version="0.4.0", registry_index=_index("0.4.0"))
    commands.run_list(project_root=root)
    out = capsys.readouterr().out
    assert "stale" not in out
    assert "COULD_NOT_CHECK" not in out


def test_a_configured_but_unreadable_registry_is_could_not_check(tmp_path, capsys):
    """THE POINT. Configured-and-unreadable must not read as clean."""
    root = _repo(tmp_path, installed_version="0.1.0", registry_index="missing")
    commands.run_list(project_root=root)
    out = capsys.readouterr().out
    assert "COULD_NOT_CHECK" in out
    assert "not 'up to date'" in out
    assert "registry unreadable" in out


def test_no_registry_configured_is_silent(tmp_path, capsys):
    """A repo that vendors locally is owed nothing by a staleness check."""
    root = _repo(tmp_path, installed_version="0.1.0", registry_index=None)
    commands.run_list(project_root=root)
    out = capsys.readouterr().out
    assert "COULD_NOT_CHECK" not in out
    assert "stale" not in out


def test_an_unreadable_registry_is_not_reported_as_up_to_date(tmp_path, capsys):
    """The inverse assertion, stated separately because it is the whole point:
    silence here would be indistinguishable from a verified-current substrate."""
    root = _repo(tmp_path, installed_version="0.1.0", registry_index="missing")
    commands.run_list(project_root=root)
    out = capsys.readouterr().out
    assert "up to date" not in out.replace("not 'up to date'", "")

# URN: test:admit-substrate:substrate-admission:C007-SMOKE-001-list-cli-reports-staleness
# Acceptance: acc:admit-substrate:C007-SMOKE-001-list-cli-reports-staleness
# WMBT: wmbt:admit-substrate:C007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C007-SMOKE-001 — `atdd substrate list` as a real subprocess reports a package the
registry has moved past, and never renders an unreadable registry as a clean
substrate (#1878).

The unit tests call ``run_list`` in-process. This one goes through the CLI the way
an operator does, because the failure being guarded is one an operator reads off a
terminal: a substrate that LOOKS current. An in-process test cannot catch a wiring
break between the `substrate list` subcommand and the staleness report.
"""
from __future__ import annotations

import pathlib

import yaml


def _project(tmp_path: pathlib.Path, *, installed: str, publishes: str | None) -> pathlib.Path:
    """One admitted package plus a path registry.

    ``publishes`` is the version the registry advertises, or ``None`` for a
    configured registry whose index file is absent.
    """
    root = tmp_path / "proj"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "substrate.lock.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "artifacts": [
                    {
                        "id": "demo.ext",
                        "kind": "extension",
                        "version": installed,
                        "digest": "sha256:" + "0" * 64,
                        "installed_path": f".atdd/extensions/demo.ext/{installed}",
                        "enabled": True,
                        "workspaces": [],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    reg_dir = tmp_path / "reg"
    reg_dir.mkdir()
    if publishes is not None:
        (reg_dir / "index.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0.0",
                    "entries": [
                        {"id": "demo.ext", "kind": "extension", "latest_version": publishes}
                    ],
                }
            ),
            encoding="utf-8",
        )
    (root / ".atdd" / "substrate.yaml").write_text(
        yaml.safe_dump(
            {
                "registries": [
                    {"name": "hub", "type": "path", "source": str(reg_dir), "path": "index.yaml"}
                ]
            }
        ),
        encoding="utf-8",
    )
    return root


def test_list_cli_names_the_published_version_and_the_remedy(tmp_path, run_atdd) -> None:
    root = _project(tmp_path, installed="0.1.0", publishes="0.4.0")
    lock = root / ".atdd" / "substrate.lock.yaml"
    before = lock.read_text(encoding="utf-8")

    result = run_atdd(["substrate", "list"], root)

    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout + result.stderr
    assert "0.1.0" in out and "0.4.0" in out, "a staleness report must name both versions"
    assert "atdd substrate add" in out, "a report naming no remedy is not actionable"
    assert lock.read_text(encoding="utf-8") == before, "list reports staleness, never applies it"


def test_list_cli_refuses_to_call_an_unreadable_registry_clean(tmp_path, run_atdd) -> None:
    """THE POINT: configured-and-unreadable must not render as a verified substrate."""
    root = _project(tmp_path, installed="0.1.0", publishes=None)
    lock = root / ".atdd" / "substrate.lock.yaml"
    before = lock.read_text(encoding="utf-8")

    result = run_atdd(["substrate", "list"], root)

    out = result.stdout + result.stderr
    assert "COULD_NOT_CHECK" in out
    assert "not 'up to date'" in out
    assert lock.read_text(encoding="utf-8") == before

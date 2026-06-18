# URN: test:admit-substrate:substrate-admission:C004-SMOKE-001-remove-cli
# Acceptance: acc:admit-substrate:C004-SMOKE-001-remove-cli
# WMBT: wmbt:admit-substrate:C004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C004-SMOKE-001 — `atdd remove <id>` refuses on a dependent and succeeds on a leaf,
updating the lockfile."""
from __future__ import annotations

import textwrap


def _seed_lock(tmp_path) -> None:
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    (atdd_dir / "substrate.lock.yaml").write_text(
        textwrap.dedent(
            """\
            schema_version: "1.0.0"
            artifacts:
              - id: acme.workspace.ws
                kind: workspace
                version: "1.0.0"
                digest: "sha256:%s"
                installed_path: ".atdd/workspaces/acme.workspace.ws/1.0.0"
              - id: acme.extension.dep
                kind: extension
                version: "0.1.0"
                digest: "sha256:%s"
                installed_path: ".atdd/extensions/acme.extension.dep/0.1.0"
                workspaces:
                  - id: acme.workspace.ws
              - id: acme.extension.leaf
                kind: extension
                version: "0.1.0"
                digest: "sha256:%s"
                installed_path: ".atdd/extensions/acme.extension.leaf/0.1.0"
            """
            % ("a" * 64, "b" * 64, "c" * 64)
        ),
        encoding="utf-8",
    )


def test_remove_refuses_dependent_succeeds_leaf(tmp_path, run_atdd) -> None:
    _seed_lock(tmp_path)

    refused = run_atdd(["remove", "acme.workspace.ws"], tmp_path)
    assert refused.returncode != 0
    assert "acme.workspace.ws" in (tmp_path / ".atdd" / "substrate.lock.yaml").read_text()

    ok = run_atdd(["remove", "acme.extension.leaf"], tmp_path)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "acme.extension.leaf" not in (tmp_path / ".atdd" / "substrate.lock.yaml").read_text()

# URN: test:admit-substrate:substrate-admission:D001-SMOKE-001-schemas-shipped
# Acceptance: acc:admit-substrate:D001-SMOKE-001-schemas-shipped
# WMBT: wmbt:admit-substrate:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D001-SMOKE-001 — the substrate schemas ship as package data and load from the
installed toolkit (resolved package-relatively), so a real lockfile validates via
the public substrate-loading path with no repo checkout and no runtime executed."""
from __future__ import annotations

import subprocess
import sys
import textwrap


def test_lockfile_validates_against_installed_schema(tmp_path) -> None:
    lock = tmp_path / "substrate.lock.yaml"
    lock.write_text(
        textwrap.dedent(
            """\
            schema_version: "1.0.0"
            artifacts:
              - id: acme.extension.demo
                kind: extension
                version: "0.1.0"
                source: registry:atdd.official
                digest: "sha256:%s"
                installed_path: ".atdd/extensions/acme.extension.demo/0.1.0"
                enabled: true
                workspaces: []
            """
            % ("a" * 64)
        ),
        encoding="utf-8",
    )
    # Resolve the schema package-relatively from the INSTALLED atdd package and
    # validate the real lockfile through the public path — in a subprocess so the
    # schema must genuinely ship as package data (not be read from the repo).
    script = textwrap.dedent(
        f"""
        import sys, yaml
        from atdd.substrate import schemas
        data = yaml.safe_load(open(r"{lock}"))
        schemas.validate_lock(data)          # must resolve schema package-relatively
        print("VALID")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert proc.returncode == 0, f"lockfile failed to validate: {proc.stdout}\n{proc.stderr}"
    assert "VALID" in proc.stdout

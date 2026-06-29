# URN: test:admit-substrate:substrate-cli-grouping:C005-SMOKE-001-flat-verb-deprecation-warns
# Acceptance: acc:admit-substrate:C005-SMOKE-001-flat-verb-deprecation-warns
# WMBT: wmbt:admit-substrate:C005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C005-SMOKE-001 (V2) — the deprecated flat `atdd add` still installs
successfully and emits a deprecation notice to stderr naming `atdd substrate
add`; the notice never pollutes stdout."""
from __future__ import annotations

import pathlib

VALID = pathlib.Path(__file__).parent / "fixtures" / "valid_extension"


def test_flat_add_warns_on_stderr_but_works(tmp_path, run_atdd) -> None:
    proc = run_atdd(["add", "--path", str(VALID)], tmp_path)

    # still works: exit zero + installs to the versioned home exactly as before
    assert proc.returncode == 0, proc.stdout + proc.stderr
    home = tmp_path / ".atdd" / "extensions" / "acme.extension.demo" / "0.1.0"
    assert home.is_dir()

    # deprecation notice on stderr, naming the grouped replacement
    assert "substrate add" in proc.stderr
    assert "deprecated" in proc.stderr.lower()

    # ...and NOT on stdout (routed to stderr per the issue's V2 measure)
    assert "deprecated" not in proc.stdout.lower()

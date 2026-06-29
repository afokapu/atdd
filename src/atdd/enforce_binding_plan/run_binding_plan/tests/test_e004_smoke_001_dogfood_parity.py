# URN: test:enforce-binding-plan:run-binding-plan:E004-SMOKE-001-dogfood-parity
# Acceptance: acc:enforce-binding-plan:E004-SMOKE-001-dogfood-parity
# WMBT: wmbt:enforce-binding-plan:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-001 — dogfood parity on src/atdd, incl. the print exemption (V4).

Running the runner over ATDD's own ``src/atdd/`` must produce the same pass/fail
set as the legacy in-core validators for the bound rules, and must preserve the
``coder.logging.print`` exemption of ``src/atdd`` (ATDD is itself a CLI tool —
its own ``print``s do not trip the rule). This is the exact evidence #1207 needs
before it can retire each legacy in-core validator.

RED reason: the ``atdd enforce`` verb is absent, so the dogfood scan cannot run
(argparse exits 2). When the runner + scan policy ship, scanning ``src/atdd``
exits 0 (parity holds) with no ``coder.logging.print`` finding against the
exempt toolkit source.
"""
from __future__ import annotations

import pytest

from .conftest import VERB_ABSENT, repo_src

pytestmark = pytest.mark.smoke


def test_e004_smoke_001_runner_matches_legacy_over_src_atdd(run_enforce) -> None:
    repo_root = repo_src().parent  # parent of src/ == repo checkout root

    # Scan ATDD's own source with the bound rule set (dogfood / parity mode).
    proc = run_enforce(["--paths", "src/atdd"], cwd=repo_root)
    combined = proc.stdout + proc.stderr

    assert VERB_ABSENT not in combined, "atdd enforce is not wired as a command"

    # Parity: src/atdd is clean under the legacy in-core validators for the bound
    # set, so the runner's aggregate verdict over src/atdd must also be clean.
    assert proc.returncode == 0, (
        f"dogfood scan of src/atdd exited {proc.returncode}, expected parity-clean 0:\n{combined}"
    )

    # The coder.logging.print exemption of src/atdd must be preserved — the
    # toolkit's own CLI prints must not be reported as violations.
    assert "coder.logging.print" not in combined, (
        "the coder.logging.print exemption of src/atdd was not preserved — "
        "toolkit CLI prints tripped the rule:\n" + combined
    )

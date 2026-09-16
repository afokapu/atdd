# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-SMOKE-002-shipped-cli-offers-no-manifest-verb
# Acceptance: acc:migrate-projection-authority:Y002-SMOKE-002-shipped-cli-offers-no-manifest-verb
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state` CLI, in a real checkout, rejects `mint-uids` and `migrate-manifest` as unknown verbs, still offers `migrate-store`, and the doc-integrity checks that pinned the dead verbs in place now pass over the reduced surface. Refs #2023.
"""SMOKE — the shipped CLI offers no manifest verb (Y002-SMOKE-002).

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:Y002

The unit acceptance reads ``OPS``, the parser and the dispatch map in-process. This one asks the
question an operator asks: *what happens when I type the command the runbook told me to type?*
Before #2023 the answer was ``ERROR: no legacy manifest to migrate`` — a shipped command failing on
an input that cannot exist. After it, the verb is simply not a verb.

It also drives the two checks that kept the corpses warm. ``runbook-check`` reconciles
``MIGRATION_STEPS`` against the runbook's sections and never against the verbs the CLI registers, so
it certified two steps whose command could not run while omitting ``migrate-store``, the live
migration. Both directions are fixed here, and both checks must pass through the real command for
that to mean anything. Refs #2023 / #1400.
"""
from __future__ import annotations

import pytest

from ._live import atdd_state, make_checkout

#: Removed in #2023: both resolved their input through `manifest_path(root)`.
RETIRED = ("mint-uids", "migrate-manifest")


@pytest.mark.smoke
def test_y002_smoke_002_retired_verbs_are_not_verbs(tmp_path) -> None:
    """The shipped CLI does not know the manifest-era verbs at all."""
    repo = make_checkout(tmp_path / "repo")
    for verb in RETIRED:
        result = atdd_state(repo, verb)
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"`atdd state {verb}` still runs:\n{combined}"
        assert "invalid choice" in combined, (
            f"`atdd state {verb}` failed, but not as an unknown verb — it is still registered and "
            f"failing on its missing input, which is the 'deprecated in place' state "
            f"decommission-manifest forbids:\n{combined}"
        )
        assert "no legacy manifest to migrate" not in combined


@pytest.mark.smoke
def test_y002_smoke_002_the_live_migration_is_still_offered(tmp_path) -> None:
    """Removing the predecessors must not remove the successor."""
    repo = make_checkout(tmp_path / "repo")
    result = atdd_state(repo, "migrate-store", "--dry-run")
    combined = result.stdout + result.stderr
    assert "invalid choice" not in combined, (
        f"`atdd state migrate-store` is gone — the live migration went out with the dead ones:\n"
        f"{combined}"
    )


@pytest.mark.smoke
def test_y002_smoke_002_doc_integrity_checks_pass_over_the_reduced_surface(tmp_path) -> None:
    """The checks that certified the dead verbs now pass against what the code actually ships."""
    from ._live import REPO_ROOT

    for verb in ("runbook-check", "rollout-check"):
        result = atdd_state(REPO_ROOT, verb)
        assert result.returncode == 0, (
            f"`atdd state {verb}` fails against this checkout:\n{result.stdout}{result.stderr}"
        )

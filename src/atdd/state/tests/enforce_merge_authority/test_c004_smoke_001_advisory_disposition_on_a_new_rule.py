# URN: test:enforce-merge-authority:enforce-rule-disposition:C004-SMOKE-001-advisory-disposition-on-a-new-rule
# Acceptance: acc:enforce-merge-authority:C004-SMOKE-001-advisory-disposition-on-a-new-rule
# WMBT: wmbt:enforce-merge-authority:C004
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state disposition-check` CLI over a real checkout, a convention node authored by train train:object-conflict-resolution:project-state that ships advisory with no precondition is refused non-zero naming the rule and the unpaid-advisory clause; the same node shipping strict, or advisory with a precondition and a discharging issue, exits zero; and this working copy's own conventions pass. Refs #1400.
"""advisory-disposition-on-a-new-rule holds end-to-end (C004-SMOKE-001).

wagon: enforce-merge-authority | feature: enforce-rule-disposition | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:C004

The gate driven as an author would meet it: a convention file on disk, the real
``atdd state disposition-check`` command, a real exit code.

It runs over this working copy too. Today that scan is *vacuous* — this train has authored
no convention node yet — and that is precisely the moment to land the gate. Advisory is
debt against an empty corpus; the only way it never accumulates is for the check to be in
place before the first node, not after the first backlog. Refs #1400.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.dispositions import TRAIN_ID

from ._helpers import repo_root
from ._live import atdd_state, repo_on_bare_remote

RULE_ID = "coder.projection.no-host-paths"


def _convention(root, rule) -> None:
    path = root / "src" / "atdd" / "coder" / "conventions" / "projection.convention.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "convention_id": "coder.projection",
                "name": "Projection Convention",
                "authored_by_train": TRAIN_ID,
                "rules": [rule],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.smoke
def test_c004_smoke_001_advisory_disposition_on_a_new_rule(tmp_path) -> None:
    """The real CLI refuses the unpaid advisory and admits strict and the paid-for one."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    # A convention node this train authored, shipping advisory with no stated precondition.
    _convention(repo, {"id": RULE_ID, "disposition": "advisory"})

    result = atdd_state(repo, "disposition-check")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "advisory disposition refused" in result.stdout
    assert RULE_ID in result.stdout
    assert "unpaid_advisory" in result.stdout
    assert "projection.convention.yaml" in result.stdout

    # The same node shipping strict exits zero.
    _convention(repo, {"id": RULE_ID, "disposition": "strict"})
    strict = atdd_state(repo, "disposition-check")
    assert strict.returncode == 0, strict.stdout + strict.stderr
    assert "ships strict" in strict.stdout

    # And so does a PAID-FOR advisory: a written precondition, and an issue on the hook.
    _convention(repo, {
        "id": RULE_ID,
        "disposition": "advisory",
        "advisory_precondition": "the manifest mirror still carries absolute paths in 3 bodies",
        "advisory_discharged_by": "#1400 migrate-projection-authority",
    })
    paid = atdd_state(repo, "disposition-check")
    assert paid.returncode == 0, paid.stdout + paid.stderr

    # A foreign convention — advisory, unpaid, and NOT this train's — is left alone: the
    # gate governs what its author is responsible for, and a gate that reaches further
    # than that gets switched off.
    foreign = repo / "src" / "atdd" / "coach" / "conventions" / "legacy.convention.yaml"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text(
        yaml.safe_dump({
            "convention_id": "coach.legacy",
            "rules": [{"id": "coach.legacy.whatever", "disposition": "advisory"}],
        }, sort_keys=False),
        encoding="utf-8",
    )
    scoped = atdd_state(repo, "disposition-check")
    assert scoped.returncode == 0, scoped.stdout + scoped.stderr
    assert "coach.legacy.whatever" not in scoped.stdout

    # And this working copy's own convention tree passes — vacuously today, because the
    # train has authored no node yet. That is exactly the moment to land the gate: advisory
    # is debt against an empty corpus, so the check must precede the first node.
    from atdd.state.dispositions import scan_conventions

    assert scan_conventions(repo_root()).ok

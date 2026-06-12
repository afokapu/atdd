# URN: test:mediate-worker-decisions:verify-producer-gate:C010-UNIT-001-expectation-partition-derived-from-freedom-layer
# Acceptance: acc:mediate-worker-decisions:C010-UNIT-001-expectation-partition-derived-from-freedom-layer
# WMBT: wmbt:mediate-worker-decisions:C010
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C010-UNIT-001 — the surfacing-expectation partition is derived from the freedom layer.

A command whose tool is pre-authorized by the post-#1062 scoped Bash allow-list
(``pytest --version`` vs the ``"pytest:*"`` pattern) is classified expected-auto-run
(no Feed item); a command outside it (``git push --dry-run``) is classified
expected-surfaced as a ``permissionRequest``. The partition tracks the allow-list
passed in — drop ``pytest:*`` and the same safe command now surfaces — proving it is
derived from the freedom layer, not a hardcoded second copy.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.verify_producer_gate.src.domain.surfacing_expectation import (
    KIND_AUTO_RUN,
    KIND_PERMISSION_REQUEST,
    classify_command,
)
from atdd.mediate_worker_decisions.verify_producer_gate.tests._helpers import (
    FREEDOM_LAYER_BASH_ALLOW,
)


def test_safe_command_auto_runs_gated_command_surfaces():
    safe = classify_command("pytest --version", bash_allow=FREEDOM_LAYER_BASH_ALLOW)
    gated = classify_command("git push --dry-run", bash_allow=FREEDOM_LAYER_BASH_ALLOW)

    # A freedom-layer command auto-runs — it never reaches the Feed.
    assert safe.surfaces is False
    assert safe.kind == KIND_AUTO_RUN
    # A gated command surfaces a permissionRequest the daemon can mediate.
    assert gated.surfaces is True
    assert gated.kind == KIND_PERMISSION_REQUEST


def test_partition_is_derived_from_the_allow_list_not_hardcoded():
    # Narrow the allow-list so pytest is no longer pre-authorized.
    narrow = ("grep:*",)
    now_gated = classify_command("pytest --version", bash_allow=narrow)

    # Classification tracks the allow-list passed in — so it is derived, not hardcoded.
    assert now_gated.surfaces is True
    assert now_gated.kind == KIND_PERMISSION_REQUEST

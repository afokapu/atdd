# URN: test:migrate-projection-authority:remove-github-reads:Y001-UNIT-002-lifecycle-decides-with-provider-absent
# Acceptance: acc:migrate-projection-authority:Y001-UNIT-002-lifecycle-decides-with-provider-absent
# WMBT: wmbt:migrate-projection-authority:Y001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: With ZERO SyncProviders registered and no GitHub reachable, every lifecycle decision — the phase a gate is handed, transition legality, gate evaluation — resolves from the projection and git alone: no provider call is attempted, and no provider-absent error is raised. Refs #1434.
"""Every lifecycle decision resolves with the provider absent (Y001-UNIT-002).

wagon: migrate-projection-authority | feature: remove-github-reads | phase: GREEN
WMBT: wmbt:migrate-projection-authority:GREEN

Two failure modes, and the acceptance names both because they are opposite mistakes:

- *a provider call is attempted* — the mirror is being consulted, and I7 is broken;
- *a provider-absent error is raised* — the mirror is being **required**, which is I7 broken the
  other way round. "GitHub is optional" is not satisfied by failing politely when it is missing.

So the store's phase must be the one the gate is handed, the GitHub adapter must never be reached
(proven by making the import itself explode), and nothing may raise. Refs #1434 / #1400.
"""
from __future__ import annotations

import builtins

import pytest

from atdd.coach.core.types import CiState
from atdd.state import providers
from atdd.state.evidence import check_transition
from atdd.train.persistence import _ProviderAbsentSource

#: The evidence a legal PLANNED -> RED carries (spec §6).
_RED_EVIDENCE = {"operator_token_digest", "gate_id", "failing_test_evidence"}


@pytest.fixture
def github_is_a_landmine(monkeypatch):
    """Make ANY import of the GitHub adapter explode.

    The strongest available statement of "no provider call is attempted": if a lifecycle decision
    so much as reaches for the adapter, the test dies. A mock that returned ``None`` would let a
    reaching implementation pass while looking innocent.
    """
    real_import = builtins.__import__

    def _exploding(name, *args, **kwargs):
        if name.startswith("atdd.integrations.github") or name in ("github", "ghapi"):
            raise AssertionError(f"a lifecycle decision reached for the provider: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _exploding)


def test_y001_unit_002_lifecycle_decides_with_provider_absent(github_is_a_landmine) -> None:
    """Zero providers registered: the phase is the store's, nothing calls out, nothing raises."""
    # ZERO providers. This is the default, and it is the state core ships in.
    assert providers.discover_providers() == {}

    # The default evidence source — the one `materialize_evidence` uses when nobody injects — has
    # NO opinion about the phase. That is the fix: it used to return the live GitHub label, which
    # then overruled the store.
    source = _ProviderAbsentSource()
    assert source.read_phase(1400) is None, (
        "the provider must have no opinion about the phase — the store decides (I7)"
    )
    # ...and it degrades honestly on the data a provider genuinely owns, rather than raising.
    assert source.read_pr_state(1400) is None
    assert source.read_ci_state(1400) == CiState.NONE.value

    # Transition legality — the load-bearing lifecycle decision — resolves from the evidence the
    # commit carries, and from nothing else. No provider is consulted, and the verdict is the same
    # one it would give with GitHub up.
    legal = check_transition("wi_01HF7YAT00M78607F000000001", "PLANNED", "RED", _RED_EVIDENCE)
    assert legal == [], f"a fully evidenced PLANNED->RED must be legal with no provider: {legal}"

    # ...and an illegal one is still refused. The decision did not merely stop consulting GitHub;
    # it kept deciding.
    backwards = check_transition("wi_01HF7YAT00M78607F000000001", "GREEN", "RED", _RED_EVIDENCE)
    assert backwards, "GREEN->RED is non-monotonic and must be refused, provider or no provider"

    # Nothing raised a provider-absent error along the way. "GitHub is optional" is not satisfied
    # by failing politely when it is missing — it is satisfied by not needing it.

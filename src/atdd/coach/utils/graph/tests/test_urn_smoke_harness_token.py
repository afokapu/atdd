# URN: test:coach:urn:smoke_harness_token
"""
Issue #959 — SMOKE is missing from the acceptance-URN family enum.

``planner.wmbt.must-have-smoke-acceptance`` REQUIRES the ``-SMOKE-NNN`` token
on every SMOKE acceptance, yet the acceptance-URN family pattern enumerated
``UNIT|HTTP|EVENT|…|INTEGRATION|…|STORAGE`` but NOT ``SMOKE``. The result: every
SMOKE acceptance was simultaneously required and flagged as a broken URN — the
broken-URN scanner (``atdd repo broken``) resolves ``acc:`` URNs through
``URNGrammar.PATTERNS['acc']`` (see resolver.py::_validate_format) and reported
~500 ``acc:*-SMOKE-*`` URNs as broken.

These tests pin that ``SMOKE`` is a first-class harness token in the
acceptance-URN grammar so ``-SMOKE-NNN`` URNs validate as well-formed, and stay
coherent with ``_SMOKE_URN_RE`` in
``src/atdd/planner/validators/_smoke_urn.py``.
"""

from __future__ import annotations

import re

import pytest

from atdd.coach.utils.graph.urn import URNGrammar

# Mirror of _SMOKE_URN_RE in
# src/atdd/planner/validators/_smoke_urn.py — the two MUST
# stay coherent: anything the SMOKE-acceptance validator demands must validate
# as a well-formed acc URN.
_SMOKE_URN_RE = re.compile(
    r"^acc:[a-z][a-z0-9-]*:[DLPCEMYRK]\d{3}-SMOKE-\d{3}(?:-[a-z0-9-]+)?$"
)


# ---------------------------------------------------------------------------
# Family enum includes SMOKE
# ---------------------------------------------------------------------------


class TestSmokeHarnessCode:
    def test_harness_codes_maps_smoke(self):
        """URNGrammar.HARNESS_CODES exposes the canonical SMOKE token."""
        assert URNGrammar.HARNESS_CODES.get("smoke") == "SMOKE"

    def test_acceptance_builder_emits_smoke_urn(self):
        """The builder accepts SMOKE and produces a well-formed acc URN."""
        urn = URNGrammar.acceptance(
            "mediate-worker-decisions", "E007", "SMOKE", "001", "live-all-answered"
        )
        assert urn == (
            "acc:mediate-worker-decisions:E007-SMOKE-001-live-all-answered"
        )


# ---------------------------------------------------------------------------
# -SMOKE-NNN URNs validate as well-formed (not broken)
# ---------------------------------------------------------------------------


class TestSmokeUrnValidates:
    @pytest.mark.parametrize(
        "good_urn",
        [
            "acc:mediate-worker-decisions:E007-SMOKE-001-live-multi-question-all-answered",
            "acc:integration-hardening:E001-SMOKE-002",
            "acc:auth:C004-SMOKE-019-session-management",
            "acc:a:D001-SMOKE-999",
        ],
    )
    def test_smoke_acc_urn_passes_validate_urn(self, good_urn):
        # validate_urn(...,"acc") is exactly the path resolver.py::_validate_format
        # uses (URNGrammar.PATTERNS['acc']) to decide is_broken for the scanner.
        assert URNGrammar.validate_urn(good_urn, "acc") is True

    def test_smoke_acc_urn_passes_validate_grammar(self):
        """The auto-detect public entry point accepts SMOKE acc URNs."""
        assert URNGrammar.validate_grammar(
            "acc:integration-hardening:E001-SMOKE-002-self-compliance"
        ) is True


# ---------------------------------------------------------------------------
# Regression: the ~500 false-broken SMOKE URNs are no longer reported
# ---------------------------------------------------------------------------


class TestSmokeBrokenRegression:
    def test_representative_real_smoke_urn_not_broken(self):
        """A representative live URN from plan/ resolves as well-formed."""
        urn = "acc:mediate-worker-decisions:E007-SMOKE-001-live-multi-question-all-answered"
        assert URNGrammar.validate_urn(urn, "acc") is True

    def test_coherent_with_smoke_acceptance_validator_regex(self):
        """Anything _SMOKE_URN_RE accepts must validate as an acc URN."""
        sample = "acc:integration-hardening:E001-SMOKE-001-some-live-check"
        assert _SMOKE_URN_RE.match(sample), "fixture must match the validator regex"
        assert URNGrammar.validate_urn(sample, "acc") is True

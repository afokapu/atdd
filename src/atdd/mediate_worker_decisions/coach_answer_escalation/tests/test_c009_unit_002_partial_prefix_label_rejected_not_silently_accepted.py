# URN: test:mediate-worker-decisions:coach-answer-escalation:C009-UNIT-002-partial-prefix-label-rejected-not-silently-accepted
# Acceptance: acc:mediate-worker-decisions:C009-UNIT-002-partial-prefix-label-rejected-not-silently-accepted
# WMBT: wmbt:mediate-worker-decisions:C009
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C009-UNIT-002 — a partial/prefix of a real option is rejected, not accepted.

``Larg`` is a prefix of both ``Large`` and ``Larger`` but matches neither
exactly; resolution must reject it loudly rather than silently pick one. An exact
label still resolves, proving the rejection is about inexactness, not a blanket failure.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.coach_answer_escalation.src.domain.label_resolver import (
    LabelResolutionError,
    resolve_exact_label,
)


def test_partial_prefix_is_rejected():
    with pytest.raises(LabelResolutionError):
        resolve_exact_label("Larg", ["Large", "Larger"])


def test_exact_label_still_resolves():
    assert resolve_exact_label("Large", ["Large", "Larger"]) == "Large"

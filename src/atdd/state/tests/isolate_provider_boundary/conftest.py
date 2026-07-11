# URN: component:isolate-provider-boundary:test-support:registry_hygiene:backend:tests
# Runtime: python
# Purpose: Guarantee every isolate-provider-boundary acceptance starts from the state core actually ships in — ZERO registered providers — and leaves no registration behind for the next test.

"""Registry hygiene for the isolate-provider-boundary acceptances (#1400).

The provider registry is process-global, which is correct — a process has one set of installed
extensions — and which makes it exactly the kind of state a test suite corrupts for itself. Every
acceptance here starts from **zero providers**, because zero providers is not merely a convenient
fixture: it is the claim the whole wagon is making (spec §8.1). A test that inherited a
registration from the test before it would be asserting the M5 exit criterion against a runtime
that does not satisfy it.

Cleared *after* as well as before, so a failing acceptance cannot take the next one down with it.
"""
from __future__ import annotations

import pytest

from atdd.state import provider_seam


@pytest.fixture(autouse=True)
def empty_registry():
    """Zero providers registered — core's default, and its resting state."""
    provider_seam.clear_providers()
    yield
    provider_seam.clear_providers()

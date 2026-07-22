# URN: test:drive-state-machine:record-agent-session-identity:D003-UNIT-004-capture-is-enrolled-in-the-provider-boundary
# Acceptance: acc:drive-state-machine:D003-UNIT-004-capture-is-enrolled-in-the-provider-boundary
# WMBT: wmbt:drive-state-machine:D003
# Phase: RED
# Harness: unit
# Layer: integration
"""D003-UNIT-004 — session capture is enrolled in the repo's provider boundary.

Issue #1540. Core must reach no agent runtime and no multiplexer to learn who
is acting. That rule already exists, is already generic, and is already
blocking: ``core-no-provider`` (merge_authority, spec §8.1 — *provider code
imports core; core never imports provider code*), a REQUIRED CI check.

So this test does NOT re-implement that boundary. It asserts the capture module
is IN SCOPE of it. A bespoke per-module guard would duplicate a blocking gate,
cover one module instead of the hot path, and — if written as a blocklist of
one named multiplexer — pass any other one while claiming otherwise.

The enrollment is the load-bearing part: without it the module is simply not
scanned, and the real gate stays green while the property goes unchecked.
"""
from __future__ import annotations

import pytest

from atdd.state.merge_authority import FORBIDDEN_IMPORT_RE, HOT_PATH_MODULES

pytestmark = [pytest.mark.platform]

CAPTURE_MODULES = ("agent_session",)


@pytest.mark.parametrize("module", CAPTURE_MODULES)
def test_d003_unit_004_capture_is_enrolled_in_the_provider_boundary(module):
    assert module in HOT_PATH_MODULES, (
        f"{module} is not scanned by core-no-provider; the boundary is unenforced for it"
    )


def test_d003_unit_004_the_boundary_actually_rejects_a_provider_import():
    """Enrollment is only worth asserting if the gate it enrols into can fail."""
    assert FORBIDDEN_IMPORT_RE.search("import github\n")
    assert FORBIDDEN_IMPORT_RE.search("from atdd.integrations import client\n")
    assert FORBIDDEN_IMPORT_RE.search("import requests\n")
    # and it must not fire on what capture legitimately needs
    assert not FORBIDDEN_IMPORT_RE.search("import os\n")
    assert not FORBIDDEN_IMPORT_RE.search("import yaml\n")
    assert not FORBIDDEN_IMPORT_RE.search("from .store import StateStore\n")

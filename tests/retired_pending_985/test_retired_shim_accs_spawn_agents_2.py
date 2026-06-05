# Placeholder anchors — shim launch transport decommissioned in #979.
#
# These acceptances pinned the deleted shim behaviour; their tests were retired.
# Pruning the acceptance rows + now-empty WMBTs cascades into wmbt-total +
# planner.wmbt.must-have-smoke-acceptance, so it is deferred to #985. Until then
# these labelled anchors keep the bidirectional acceptance-binding gate green.
# Remove this file in #985 when the acceptances + WMBTs are retired.
# Acceptance: acc:spawn-agents:L002-SMOKE-001-relative-runtime-root-output-log-at-absolute-path

import pytest

pytestmark = pytest.mark.skip(
    reason="shim decommissioned in #979; acceptance + WMBT retirement tracked in #985"
)


def test_retired_shim_acceptances_pending_985():
    """Placeholder anchor; the shim acceptances above are retired in #985."""
    pytest.skip("retired shim acceptances (#979 -> #985)")

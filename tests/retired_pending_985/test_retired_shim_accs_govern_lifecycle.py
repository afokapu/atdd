# Placeholder anchors — shim launch transport decommissioned in #979.
#
# These acceptances pinned the deleted shim behaviour; their tests were retired.
# Pruning the acceptance rows + now-empty WMBTs cascades into wmbt-total +
# planner.wmbt.must-have-smoke-acceptance, so it is deferred to #985. Until then
# these labelled anchors keep the bidirectional acceptance-binding gate green.
# Remove this file in #985 when the acceptances + WMBTs are retired.
# Acceptance: acc:govern-lifecycle:E014-SMOKE-002-runtime-shim-entry-refuses-forbidden-flag
# Acceptance: acc:govern-lifecycle:E014-UNIT-004-runtime-default-command-derives-permission-policy-from-spec
# Acceptance: acc:govern-lifecycle:E014-UNIT-006-runtime-shim-entry-rejects-forbidden-flag
# Acceptance: acc:govern-lifecycle:E029-INTEGRATION-001-retrofitted-smoke-tests-pass
# Acceptance: acc:govern-lifecycle:E029-SMOKE-001-retrofitted-smokes-pass-in-ci-without-bypasses
# Acceptance: acc:govern-lifecycle:E029-UNIT-001-e003-smoke-001-has-no-fakemultiplexer
# Acceptance: acc:govern-lifecycle:E029-UNIT-002-e003-smoke-002-asserts-on-stdout-not-only-log
# Acceptance: acc:govern-lifecycle:E029-UNIT-003-e003-smoke-001-uses-real-spawn-entrypoint
# Acceptance: acc:govern-lifecycle:E039-SMOKE-001-real-shim-deliver-and-interrupt
# Acceptance: acc:govern-lifecycle:E039-UNIT-002-deliver-prompt-injects-and-submits
# Acceptance: acc:govern-lifecycle:E039-UNIT-003-signal-interrupt-terminates
# Acceptance: acc:govern-lifecycle:E039-UNIT-004-cli-return-default-legacy-kill-switch
# Acceptance: acc:govern-lifecycle:E039-UNIT-005-shim-gates-and-strips-boot-stdin

import pytest

pytestmark = pytest.mark.skip(
    reason="shim decommissioned in #979; acceptance + WMBT retirement tracked in #985"
)


def test_retired_shim_acceptances_pending_985():
    """Placeholder anchor; the shim acceptances above are retired in #985."""
    pytest.skip("retired shim acceptances (#979 -> #985)")

# Placeholder anchors — shim launch transport decommissioned in #979.
#
# These acceptances pinned the deleted shim behaviour; their tests were retired.
# Pruning the acceptance rows + now-empty WMBTs cascades into wmbt-total +
# planner.wmbt.must-have-smoke-acceptance, so it is deferred to #985. Until then
# these labelled anchors keep the bidirectional acceptance-binding gate green.
# Remove this file in #985 when the acceptances + WMBTs are retired.
# Acceptance: acc:spawn-agents:E016-SMOKE-001-no-popen-exec-failure-with-cli-return-env
# Acceptance: acc:spawn-agents:E016-UNIT-002-build-shim-command-emits-env-flags
# Acceptance: acc:spawn-agents:E017-SMOKE-001-shim-invoked-via-same-python-as-coach
# Acceptance: acc:spawn-agents:E017-UNIT-001-build-shim-command-uses-module-invocation
# Acceptance: acc:spawn-agents:E017-UNIT-002-no-bare-atdd-shim-token-in-command
# Acceptance: acc:spawn-agents:E017-UNIT-003-module-invocation-passes-all-existing-args
# Acceptance: acc:spawn-agents:E018-INTEGRATION-001-immediately-failing-shim-triggers-escalation
# Acceptance: acc:spawn-agents:E018-SMOKE-001-live-spawn-pipeline-detects-dead-shim
# Acceptance: acc:spawn-agents:E018-UNIT-001-process-not-alive-exception
# Acceptance: acc:spawn-agents:E018-UNIT-002-cli-return-output-log-heartbeat-check
# Acceptance: acc:spawn-agents:E018-UNIT-003-process-alive-stage-sequenced-after-surface-created
# Acceptance: acc:spawn-agents:E019-INTEGRATION-001-path-bleed-regression
# Acceptance: acc:spawn-agents:E019-SMOKE-001-shim-command-runtime-dir-is-absolute-in-live-spawn
# Acceptance: acc:spawn-agents:E019-UNIT-001-build-shim-command-resolves-relative-runtime-dir-to-absolute
# Acceptance: acc:spawn-agents:E019-UNIT-002-build-shim-command-absolute-path-unchanged
# Acceptance: acc:spawn-agents:E019-UNIT-003-cmd-spawn-materializes-absolute-runtime-root
# Acceptance: acc:spawn-agents:E020-SMOKE-001-deployed-shim-resolves-relative-runtime-dir
# Acceptance: acc:spawn-agents:E020-UNIT-001-shim-main-resolves-relative-runtime-dir-to-absolute
# Acceptance: acc:spawn-agents:E020-UNIT-002-shim-main-absolute-runtime-dir-unchanged
# Acceptance: acc:spawn-agents:E021-SMOKE-001-live-process-alive-message-names-polled-path
# Acceptance: acc:spawn-agents:E021-UNIT-001-timeout-message-names-polled-path-and-scan-outcome
# Acceptance: acc:spawn-agents:E021-UNIT-002-timeout-names-bleed-path-when-candidate-found

import pytest

pytestmark = pytest.mark.skip(
    reason="shim decommissioned in #979; acceptance + WMBT retirement tracked in #985"
)


def test_retired_shim_acceptances_pending_985():
    """Placeholder anchor; the shim acceptances above are retired in #985."""
    pytest.skip("retired shim acceptances (#979 -> #985)")

# Placeholder anchors — shim launch transport decommissioned in #979.
#
# These acceptances pinned the deleted shim behaviour; their tests were retired.
# Pruning the acceptance rows + now-empty WMBTs cascades into wmbt-total +
# planner.wmbt.must-have-smoke-acceptance, so it is deferred to #985. Until then
# these labelled anchors keep the bidirectional acceptance-binding gate green.
# Remove this file in #985 when the acceptances + WMBTs are retired.
# Acceptance: acc:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end
# Acceptance: acc:observe-and-correct:E003-SMOKE-002-operator-stdout-visible
# Acceptance: acc:observe-and-correct:E003-UNIT-001-shim-spawns-agent-in-pty
# Acceptance: acc:observe-and-correct:E003-UNIT-002-shim-drains-cli-return
# Acceptance: acc:observe-and-correct:E003-UNIT-003-bootstrap-inbox-priming
# Acceptance: acc:observe-and-correct:E003-UNIT-007-cli-return-consumed-end-to-end
# Acceptance: acc:observe-and-correct:E003-UNIT-009-operator-keystrokes-forwarded
# Acceptance: acc:observe-and-correct:E003-UNIT-010-shim-fault-isolation
# Acceptance: acc:observe-and-correct:E003-UNIT-011-pty-output-forwarded-to-operator-stdout
# Acceptance: acc:observe-and-correct:E003-UNIT-012-stdout-write-fault-isolation
# Acceptance: acc:observe-and-correct:E004-SMOKE-001-real-spawn-uses-shim-process-tree
# Acceptance: acc:observe-and-correct:E004-UNIT-001-cmd-spawn-uses-shim-as-surface-command
# Acceptance: acc:observe-and-correct:E004-UNIT-002-inbox-priming-before-shim-starts
# Acceptance: acc:observe-and-correct:E005-SMOKE-001-full-shim-spawn-with-env-override
# Acceptance: acc:observe-and-correct:E005-UNIT-001-shim-main-parses-env-flag
# Acceptance: acc:observe-and-correct:E005-UNIT-002-persona-shim-applies-env-overrides-to-popen
# Acceptance: acc:observe-and-correct:E005-UNIT-003-regression-argv-leading-key-value-fails-without-fix
# Acceptance: acc:observe-and-correct:E006-SMOKE-001-stdin-bytes-reach-wrapped-subprocess
# Acceptance: acc:observe-and-correct:E006-UNIT-001-run-loop-includes-stdin-in-select-when-isatty
# Acceptance: acc:observe-and-correct:E006-UNIT-002-stdin-not-added-when-not-isatty
# Acceptance: acc:observe-and-correct:E007-SMOKE-001-sentinel-enables-tui-submission
# Acceptance: acc:observe-and-correct:E007-UNIT-001-sentinel-appended-to-correction

import pytest

pytestmark = pytest.mark.skip(
    reason="shim decommissioned in #979; acceptance + WMBT retirement tracked in #985"
)


def test_retired_shim_acceptances_pending_985():
    """Placeholder anchor; the shim acceptances above are retired in #985."""
    pytest.skip("retired shim acceptances (#979 -> #985)")

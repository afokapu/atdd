# URN: test:spawn-agents:spawn-time-non-interactive-convention:M001-UNIT-003-verify-after-send-no-longer-checks-rename-accepted
# Acceptance: acc:spawn-agents:M001-UNIT-003-verify-after-send-no-longer-checks-rename-accepted
"""M001-UNIT-003 — verify_after_send=True does NOT call _verify_stage('rename-accepted').

RED: when verify_after_send=True, apply_canonical_name_and_layout calls
_verify_stage(stage_name='rename-accepted', ...) because /rename was injected.
GREEN: no /rename injection → no rename-accepted gate; verify_after_send is a no-op
for the rename path (or the param is ignored since there's nothing to verify).
"""
import pytest
from unittest.mock import patch, call
from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout


class FakeMux:
    def rename(self, ref, name):
        pass

    def paste_text(self, ref, text):
        pass

    def send_key(self, ref, key):
        pass

    def capture_pane_text(self, ref):
        return "Session renamed to: ATDD829"


def test_verify_after_send_true_does_not_call_rename_accepted_gate():
    """_verify_stage must NOT be called with stage_name='rename-accepted' after M001."""
    backend = FakeMux()
    with patch("atdd.coach.commands.spawn._verify_stage") as mock_verify:
        apply_canonical_name_and_layout(
            backend, "surface:1", "ATDD829", surface_count=1,
            verify_after_send=True, verify_timeout_s=0.1, verify_poll_s=0.05,
        )
    rename_accepted_calls = [
        c for c in mock_verify.call_args_list
        if c.args and c.args[0] == "rename-accepted"
    ]
    assert not rename_accepted_calls, (
        f"_verify_stage was called with stage_name='rename-accepted' after M001 — "
        f"the rename-accepted gate must be removed along with the /rename injection. "
        f"Calls: {rename_accepted_calls}"
    )

# URN: test:mediate-worker-decisions:bridge-cmux-feed:E009-INTEGRATION-001-resolved-decision-is-the-oracle
# Acceptance: acc:mediate-worker-decisions:E009-INTEGRATION-001-resolved-decision-is-the-oracle
# WMBT: wmbt:mediate-worker-decisions:E009
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E009-INTEGRATION-001 — resolved+decision is the advance oracle; nudge send-keys.

The cmux advance adapter reads ``feed.list`` for the item:
  * ``status == "resolved"`` with a populated ``decision`` => advanced (True);
  * ``status == "expired"`` with no decision => NOT advanced (False) — the false
    "no longer pending" signal must never be read as advanced (#986);
and ``nudge`` issues a ``cmux send-key ... Enter`` targeting the worker workspace.
A fake cmux runner stands in for the real subprocess so the test stays hermetic.
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_advance_verifier import (
    CmuxWorkerAdvance,
)


class FakeCmux:
    """Records cmux calls and replies feed.list/tree from canned state."""

    def __init__(self, *, status, decision):
        self._status = status
        self._decision = decision
        self.calls = []  # list[tuple[args]]

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("rpc", "feed.list"):
            return json.dumps(
                {
                    "items": [
                        {
                            "request_id": "req-x",
                            "kind": "question",
                            "status": self._status,
                            "decision": self._decision,
                        }
                    ]
                }
            )
        if args[0] == "tree":
            return json.dumps(
                {
                    "windows": [
                        {
                            "workspaces": [
                                {
                                    "ref": "workspace:42",
                                    "panes": [
                                        {
                                            "selected_surface_ref": "surface:99",
                                            "surfaces": [
                                                {"ref": "surface:99", "type": "terminal"}
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            )
        return ""  # send-key etc.


def _item() -> FeedItem:
    return FeedItem(id="i", request_id="req-x", kind=QUESTION, question_prompt="?")


def test_resolved_with_decision_confirms_advanced():
    cmux = FakeCmux(status="resolved", decision={"kind": "question", "selections": ["Tabs"]})
    advance = CmuxWorkerAdvance(
        workspace_id="workspace:42", runner=cmux, sleeper=lambda *_: None, clock=lambda: 0.0
    )

    assert advance.confirm_advanced(_item()) is True


def test_expired_without_decision_is_not_advanced():
    # "expired" is non-pending but the worker is still parked — must read False.
    cmux = FakeCmux(status="expired", decision=None)
    advance = CmuxWorkerAdvance(
        workspace_id="workspace:42", runner=cmux, sleeper=lambda *_: None, clock=lambda: 0.0
    )

    assert advance.confirm_advanced(_item()) is False


def test_nudge_issues_send_key_enter_to_workspace():
    cmux = FakeCmux(status="expired", decision=None)
    advance = CmuxWorkerAdvance(
        workspace_id="workspace:42", runner=cmux, sleeper=lambda *_: None, clock=lambda: 0.0
    )

    advance.nudge(_item())

    send_keys = [c for c in cmux.calls if c[0] == "send-key"]
    assert len(send_keys) == 1
    call = send_keys[0]
    assert "--workspace" in call
    assert call[call.index("--workspace") + 1] == "workspace:42"
    assert call[-1] == "Enter"

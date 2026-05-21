# URN: test:spawn-agents:spawn-time-non-interactive-convention:E014-UNIT-001-bash-auto-approve-no-multiplexer-send-reference
# Acceptance: acc:spawn-agents:E014-UNIT-001-bash-auto-approve-no-multiplexer-send-reference
"""E014-UNIT-001 — bash_auto_approve.py contains no stale modal-typing reference.

RED: the docstring says 'the multiplexer separately sends "1\\n" to accept' which is
stale documentation of archived babysit behavior.
GREEN: that sentence is removed and the docstring accurately describes cli-return.
"""
import inspect
import pytest


def test_bash_auto_approve_has_no_multiplexer_separately_sends_reference():
    import atdd.coach.observer_rules.bash_auto_approve as module

    source = inspect.getsource(module)
    assert "multiplexer separately sends" not in source, (
        "bash_auto_approve.py still contains 'multiplexer separately sends' — "
        "this is stale documentation of the archived babysit modal-typing path. "
        "E014: remove this reference (the current rule uses cli-return, not multiplexer.send)."
    )


def test_bash_auto_approve_has_no_one_backslash_n_modal_typing():
    import atdd.coach.observer_rules.bash_auto_approve as module

    source = inspect.getsource(module)
    assert '"1\\\\n"' not in source and '"1\\n"' not in source, (
        "bash_auto_approve.py references '\"1\\n\"' modal typing sequence — "
        "stale reference to archived babysit.py behavior. E014: remove it."
    )


def test_bash_auto_approve_module_still_importable_and_has_build_rule():
    from atdd.coach.observer_rules.bash_auto_approve import build_rule
    rule = build_rule()
    assert rule is not None, "build_rule() must still return an ObserverRule after E014 changes."

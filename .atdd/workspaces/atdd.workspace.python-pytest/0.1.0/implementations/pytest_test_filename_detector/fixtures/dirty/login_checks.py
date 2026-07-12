# URN: test:maintain-ux:login:C001-UNIT-003-login-validates-credentials
# Acceptance: acc:maintain-ux:C001-UNIT-003-login-validates-credentials
# Phase: RED
# Layer: application
"""RED fixture: an intended test (it carries a `# URN: test:` identity header)
whose filename is NOT pytest-collectable (`login_checks.py` — no `test_` prefix,
no `_test.py` suffix). pytest silently never collects it -> it would pass CI by
never running. Detector emits ONE raw violation, reported at the URN header line."""


def test_login_validates_credentials():
    assert True

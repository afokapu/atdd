# URN: test:maintain-ux:user-connection:C004-E2E-019-user-connection
# Acceptance: acc:maintain-ux:C004-E2E-019-user-connection
# WMBT: wmbt:maintain-ux:C004
# Phase: RED
# Layer: integration
"""GREEN fixture: a correctly named python test. Filename starts with `test_` and
is derived from the acceptance URN -> pytest collects it -> RAW = []."""


def test_user_connection_is_established():
    assert 1 + 1 == 2

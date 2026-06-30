"""RED fixture: an intended test (it defines a top-level `def test_*`) under a
non-collectable name (`verify_signup.py`) and WITHOUT a URN header. Detector still
recognizes it as a test via the `def test_signup_*` function and emits ONE raw
violation, reported at the `def test_` line."""


def helper():
    return 7


def test_signup_creates_account():
    assert helper() == 7

"""Minimal passing test for the pytest invocation form smoke fixture (issue #341).

This file exists so the smoke test can invoke pytest against a real test file
and observe a process actually start. The test itself is trivial; what matters
is that pytest collects and runs it without the runner raising
``FileNotFoundError`` when atdd is installed in an isolated venv.
"""


def test_passes() -> None:
    assert 1 + 1 == 2

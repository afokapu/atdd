"""A real implementation test that PASSES — a bound gate finding no violation.
The provider runs this under pytest; a zero exit yields no violations."""


def test_gate_clean():
    offending = []
    assert not offending

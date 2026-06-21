"""A real implementation test that FAILS — standing in for a bound gate that
detects a violation. The provider runs this under pytest; a non-zero exit becomes
one violation over the provider's violation-output contract."""


def test_gate_detects_violation():
    # The "repository state" violates the gated rule.
    offending = ["pre-smoke close"]
    assert not offending, f"gate violated by: {offending}"

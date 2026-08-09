"""Self-tests for the policy-free self-skip kernel.

Two jobs:

  1. **The kernel is policy-free, and this says so.** A future second caller must
     not be able to inherit live-smoke policy by accident, so the kernel is
     asserted to expose no rule id, severity, disposition or selector. This is
     the guard that keeps it a kernel rather than a second copy of the rule.

  2. **The two selection rules in use are both reproducible from it**, and they
     genuinely differ. Pinning the divergence stops a later "tidy-up" from
     collapsing them and silently changing one caller's reported mechanism.

No core (``atdd.*``) imports; the kernel is imported by path, as the detector is.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import self_skip_kernel as kernel  # noqa: E402


# ── 1. the kernel is policy-free ──────────────────────────────────────────────

_POLICY_TOKENS = (
    "rule_id",
    "severity",
    "disposition",
    "selector",
    "fix_hint",
    "violation",
)


def test_kernel_exposes_no_policy():
    """No public name on the kernel carries rule/severity/selector policy."""
    public = [n for n in dir(kernel) if not n.startswith("_")]
    offenders = [
        name
        for name in public
        for token in _POLICY_TOKENS
        if token in name.lower()
    ]
    assert offenders == [], (
        f"kernel must expose facts only, but these public names look like policy: "
        f"{offenders}. A caller supplies rule_id/severity/disposition."
    )


def test_kernel_source_names_no_rule_id():
    """The kernel source contains no convention rule id.

    Stronger than the name check: a rule id embedded in a docstring default or a
    constant would make the kernel a second home for the rule.
    """
    source = (Path(__file__).resolve().parent / "self_skip_kernel.py").read_text(
        encoding="utf-8"
    )
    for marker in ("tester.acceptance-violation.", "coder.", "coach.", "planner."):
        assert marker not in source, (
            f"kernel source names a convention rule namespace ({marker!r}); the "
            f"rule belongs to the caller, not the kernel"
        )


def test_kernel_findings_carry_no_verdict():
    """A finding is a fact: line, col, mechanism, matcher index — nothing more."""
    findings = kernel.find_self_skips('def t():\n    pytest.skip("x")\n')
    assert len(findings) == 1
    assert set(vars(findings[0])) == {"line", "col", "mechanism", "matcher_index"}


# ── 2. both selection rules are reproducible, and they differ ─────────────────

_MULTI = '@pytest.mark.skipif(True)\ndef t():\n    pytest.skip("x")\n'


def test_all_findings_are_returned_not_just_one():
    findings = kernel.find_self_skips(_MULTI)
    assert len(findings) >= 2, "kernel must report every site, so callers can select"
    assert [f.line for f in findings] == sorted(f.line for f in findings)


def test_the_two_selection_rules_differ_and_are_both_available():
    """Pins the divergence the extraction preserves rather than resolves."""
    findings = kernel.find_self_skips(_MULTI)
    by_table = kernel.first_by_matcher_order(findings)
    by_source = kernel.first_by_source_position(findings)
    assert by_table.mechanism == "pytest.skip(...)", "core's rule: matcher-table order"
    assert by_source.mechanism == "@pytest.mark.skipif", "workspace's rule: source position"
    assert by_table.mechanism != by_source.mechanism, (
        "if these ever agree on this input the divergence fixture has rotted and "
        "the parity guarantees below are no longer being exercised"
    )


def test_no_findings_yields_none_from_both_selectors():
    findings = kernel.find_self_skips("def t():\n    assert True\n")
    assert findings == ()
    assert kernel.first_by_matcher_order(findings) is None
    assert kernel.first_by_source_position(findings) is None


# ── 3. could-not-look stays distinguishable from looked-and-found-nothing ─────


def test_unparseable_source_is_flagged_not_silently_clean():
    facts = kernel.analyze_source("def t(:\n  broken\n")
    assert facts.parseable is False
    assert facts.has_explicit_failure is False


def test_parseable_source_reports_explicit_failure():
    assert kernel.analyze_source("def t():\n    assert 1\n").has_explicit_failure
    assert kernel.analyze_source("def t():\n    raise ValueError\n").has_explicit_failure
    assert not kernel.analyze_source("def t():\n    pass\n").has_explicit_failure


def test_other_failure_constructs_are_reported_as_facts():
    """``pytest.raises``/``pytest.fail`` are reported, not judged.

    A caller treating "no assert/raise" as "cannot fail" would misread these 14
    legitimate cases; the kernel surfaces them and takes no position.
    """
    facts = kernel.analyze_source(
        "import pytest\ndef t():\n    with pytest.raises(ValueError):\n        go()\n"
    )
    assert "pytest.raises" in facts.other_failure_constructs
    assert facts.has_explicit_failure is False


def test_function_scoped_failure_distinguishes_absent_from_none():
    src = "def a():\n    assert 1\ndef b():\n    pass\n"
    assert kernel.function_has_explicit_failure(src, "a") is True
    assert kernel.function_has_explicit_failure(src, "b") is False
    assert kernel.function_has_explicit_failure(src, "missing") is None
    assert kernel.function_has_explicit_failure("def t(:\n", "t") is None

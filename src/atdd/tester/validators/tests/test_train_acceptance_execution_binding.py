"""#1548 — train acceptances bind to executable journey tests.

Three defects made a harness-backed train acceptance impossible to satisfy, and
each is pinned here with a test that FAILS if the defect returns:

1. ``_acceptance_walker`` globbed ``plan/_trains/*.yaml`` (top level only), but
   typed trains (#1421) live nested at ``plan/_trains/<subject>/<slug>.yaml`` —
   so no train acceptance was discoverable at all.
2. A journey test MUST omit ``Acceptance:`` (SPEC-V3-002), so a train acceptance
   declaring ``harness.type`` demanded a header no journey test was allowed to
   carry. ``Train-Acceptance:`` is the distinct journey-tier spelling.
3. The bidirectional binding validator scanned only ``Acceptance:``, so the new
   header would have bound nothing.

The clean-baseline direction is deliberately paired with a fault-injected twin
everywhere: a "no violations" assertion on a walker that cannot see the file
would pass forever.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from atdd.tester.validators._acceptance_walker import iter_repo_acceptances
from atdd.tester.validators.test_repo_validator_binding import collect_violations


TRAIN_ACC = "acc:train:self-compliance:validate-lifecycle:idempotent-on-retry"


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _typed_train(root: Path, *, harness: bool = True) -> Path:
    """A typed train at its canonical NESTED home, carrying one acceptance.

    Written as FLAT (already-dedented) YAML on purpose: the harness block is
    conditional, and composing it into an indented triple-quoted literal makes
    the file's validity depend on invisible whitespace agreeing across a
    concatenation. `harness:` must land as a sibling of `identity:` inside
    acceptances[0]; here that is simply what the string says.
    """
    harness_block = (
        "    harness:\n"
        "      type: smoke\n"
        "      category: integration\n"
        if harness
        else ""
    )
    return _write(
        root / "plan" / "_trains" / "self-compliance" / "validate-lifecycle.yaml",
        'train_id: "train:self-compliance:validate-lifecycle"\n'
        'title: "Validate lifecycle"\n'
        'description: "a typed train used as an execution-binding fixture"\n'
        'themes: ["commons"]\n'
        'participants: ["wagon:self-compliance"]\n'
        "sequence:\n"
        "  - step: 1\n"
        '    intent: "run the lifecycle"\n'
        '    from: "wagon:self-compliance"\n'
        '    to: "system:atdd-cli"\n'
        '    artifact: "commons:manifest"\n'
        "acceptances:\n"
        "  - identity:\n"
        f'      urn: "{TRAIN_ACC}"\n'
        '      purpose: "the lifecycle is idempotent on retry"\n'
        "      phase: SMOKE\n" + harness_block,
    )


def _journey_test(root: Path, header_key: str) -> Path:
    return _write(
        root / "e2e" / "self-compliance" / "test_lifecycle_smoke.py",
        f"""\
        # URN: test:train:self-compliance:validate-lifecycle:SMOKE-001-idempotent
        # Train: train:self-compliance:validate-lifecycle
        # {header_key}: {TRAIN_ACC}
        # Phase: SMOKE
        # Layer: assembly
        # Assertion: behavioral

        def test_idempotent_on_retry():
            assert True
        """,
    )


# ---------------------------------------------------------------------------
# Defect 1 — the walker must SEE a subject-nested typed train
# ---------------------------------------------------------------------------


def test_walker_discovers_acceptance_in_a_subject_nested_train(tmp_path: Path):
    _typed_train(tmp_path)
    found = [r for r in iter_repo_acceptances(tmp_path) if r.kind == "train"]
    assert len(found) == 1, "subject-nested typed train was not walked"
    assert (found[0].body["identity"] or {})["urn"] == TRAIN_ACC


def test_fixture_harness_block_is_really_nested_under_the_acceptance(tmp_path: Path):
    """Guards the fixture itself.

    Both `_typed_train` shapes are shared by the clean-baseline assertions
    below. If the harness block ever skewed out of acceptances[0], the
    harness=True fixture would silently become harness-less and every "no
    violations" assertion would pass for the wrong reason.
    """
    from atdd.tester.validators._acceptance_walker import has_harness_type

    backed = _typed_train(tmp_path / "backed")
    unbacked = _typed_train(tmp_path / "unbacked", harness=False)

    (acc_backed,) = [r for r in iter_repo_acceptances(tmp_path / "backed")]
    (acc_unbacked,) = [r for r in iter_repo_acceptances(tmp_path / "unbacked")]

    assert has_harness_type(acc_backed.body), f"{backed} lost its harness block"
    assert not has_harness_type(acc_unbacked.body), f"{unbacked} grew a harness block"


def test_walker_skips_underscore_prefixed_control_artifacts(tmp_path: Path):
    """`_interlockings/` and the `_trains.yaml` registry are not trains."""
    _write(
        tmp_path / "plan" / "_trains" / "_interlockings" / "some-interlocking.yaml",
        """\
        interlocking_id: "interlocking:some-interlocking"
        acceptances:
          - identity: {urn: "acc:train:x:y:should-not-be-walked", phase: SMOKE, purpose: "no"}
        """,
    )
    found = [r for r in iter_repo_acceptances(tmp_path) if r.kind == "train"]
    assert found == [], "control artifacts under _trains/ must not be walked as trains"


# ---------------------------------------------------------------------------
# Defect 2+3 — Train-Acceptance: closes the bidirectional binding
# ---------------------------------------------------------------------------


def test_train_acceptance_header_satisfies_the_forward_pass(tmp_path: Path):
    """harness-backed train acceptance + journey test carrying Train-Acceptance: → clean."""
    _typed_train(tmp_path)
    _journey_test(tmp_path, "Train-Acceptance")

    violations = collect_violations(tmp_path)
    assert violations == [], [v.detail for v in violations]


def test_missing_journey_test_is_caught(tmp_path: Path):
    """FAULT INJECTION: the same acceptance with NO test at all must fail.

    This is the positive control for the test above — without it, that clean
    assertion would pass for any reason the acceptance went unseen.
    """
    _typed_train(tmp_path)

    violations = collect_violations(tmp_path)
    assert len(violations) == 1, [v.detail for v in violations]
    assert TRAIN_ACC in violations[0].detail
    assert "binding is one-way" in violations[0].detail


def test_plain_acceptance_header_does_not_bind_a_train_acceptance(tmp_path: Path):
    """A journey test may not use `Acceptance:` — it is forbidden by SPEC-V3-002.

    Pins that the two keys are genuinely distinct: this file DOES satisfy the
    binding (the scan accepts either spelling), which is exactly why the
    mutual-exclusion rule, not the binding rule, is what forbids it. Asserted
    here so a future reader does not "simplify" the two keys back into one.
    """
    from atdd.coach.utils.graph.resolver import TestResolver

    content = (
        "# URN: test:train:self-compliance:validate-lifecycle:SMOKE-001-x\n"
        "# Train: train:self-compliance:validate-lifecycle\n"
        f"# Train-Acceptance: {TRAIN_ACC}\n"
    )
    header = TestResolver.parse_test_header(content)

    assert header["train_acceptance"] == TRAIN_ACC
    # The journey-tier key must NOT leak into the acceptance-tier fields, or the
    # SPEC-V3-002 mutual-exclusion check would flag every bound journey test.
    assert header["acceptance"] is None
    assert header["train"] == "train:self-compliance:validate-lifecycle"
    assert header["format"] == "journey"


def test_orphaned_train_acceptance_header_is_caught(tmp_path: Path):
    """FAULT INJECTION (reverse pass): a journey test anchored to a train
    acceptance that does not exist in plan/ must fail."""
    _journey_test(tmp_path, "Train-Acceptance")

    violations = collect_violations(tmp_path)
    assert len(violations) == 1, [v.detail for v in violations]
    assert TRAIN_ACC in violations[0].detail
    assert "no acceptance with that URN exists" in violations[0].detail


def test_acceptance_without_harness_type_needs_no_test(tmp_path: Path):
    """The forward pass keys off harness.type; an unbacked acceptance is exempt."""
    _typed_train(tmp_path, harness=False)

    violations = collect_violations(tmp_path)
    assert violations == [], [v.detail for v in violations]

# URN: component:govern-lifecycle:enforcement-substrate:harness-plugin-integration:backend:tests
# Runtime: python
# Purpose: Spec-§7.2 acceptance-criteria coverage for the substrate harness-mode plugin via pytester (issue #411).

"""Integration tests for the substrate harness-mode plugin (issue #411).

Each test stands up a synthetic consumer repo under ``pytester.path`` —
``plan/<wagon>/D003.yaml`` describing one acceptance, ``tests/test_foo.py``
holding the anchored test(s), ``.atdd/manifest.yaml`` to make
``find_repo_root`` deterministic — then runs an inner pytest session via
``pytester.runpytest`` with the plugin loaded explicitly.

Acceptance criteria covered (from issue #411 body):

1. Anchored failing test produces a Violation with the derived rule_id,
   routes through the gate, and names ``<module>::<function>`` as
   validator_id.
2. Three tests anchored to the same acceptance, one fails / two pass:
   the failing test surfaces a Violation; the passing tests do not.
3. ``# atdd:suppress(...)`` on a failing anchored test does NOT silence
   the failure (strict-disposition repo rules per spec §2).
4. Failure block carries ``description:`` and ``fix_hint:`` lines above
   the violation entries (spec §6 sample format).
5. Two tests anchored to the same acceptance, both failing: each
   produces its own gate call with its own validator_id.
6. A test without anchor headers does not produce substrate violations.
8. Three acceptances + three anchored tests: all three runs are observed.

Acceptance criterion 7 (unit demonstrating hook integration) is covered
in ``test_plugin_unit.py``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Iterable, Optional

import pytest

from atdd.coach.utils import rule_binding
from atdd.coach.utils.repo import find_repo_root


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
_WMBT_YAML_TEMPLATE = """\
urn: "wmbt:foo:D003"
acceptances:
{acceptances}
"""

_ACCEPTANCE_TEMPLATE = """\
  - identity:
      urn: "{acc_urn}"
      purpose: "{purpose}"
      phase: "GREEN"
    harness:
      type: "unit"
      category: "backend"
    given:
      abstract:
        - "given a precondition"
    when:
      abstract: "the system is exercised"
    then:
      abstract:
        - "{then_first}"
        - "and another expectation"
"""


def _write_repo_skeleton(repo: Path) -> None:
    (repo / ".atdd").mkdir(exist_ok=True)
    (repo / ".atdd" / "manifest.yaml").write_text(
        "version: '2.0'\nsessions: []\n", encoding="utf-8",
    )
    # Per spec v12 §9.3 (issue #415), the substrate plugin is auto-loaded
    # via a pytest11 entry-point and gated at runtime on the `repo:` block.
    # Integration fixtures simulate a consumer-repo `atdd init --consumer-repo`
    # by writing the same block the initializer would produce.
    (repo / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        "release:\n"
        "  version_file: pyproject.toml\n"
        "repo:\n"
        "  test_root: tests/\n"
        "  plan_root: plan/\n"
        "  substrate:\n"
        "    enabled: true\n"
        "    plugin: atdd.tester.substrate.plugin\n"
        "    mode: consumer-repo\n",
        encoding="utf-8",
    )
    (repo / "plan").mkdir(exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)


def _write_wmbt(repo: Path, wagon: str, acceptances: Iterable[dict]) -> Path:
    wagon_dir = repo / "plan" / wagon
    wagon_dir.mkdir(parents=True, exist_ok=True)
    f = wagon_dir / "D003.yaml"
    f.write_text(
        _WMBT_YAML_TEMPLATE.format(
            acceptances="".join(
                _ACCEPTANCE_TEMPLATE.format(**acc) for acc in acceptances
            ),
        ),
        encoding="utf-8",
    )
    return f


def _make_test_module(
    *,
    body: str,
    acc_urn: Optional[str] = "acc:foo:D003-UNIT-001-thing",
    wmbt_urn: str = "wmbt:foo:D003",
) -> str:
    if acc_urn is None:
        return body
    header = (
        "# URN: test:foo:D003-acc-unit-001\n"
        f"# Acceptance: {acc_urn}\n"
        f"# WMBT: {wmbt_urn}\n"
        "# Phase: GREEN\n"
        "# Layer: domain\n"
        "\n"
    )
    return header + body


@pytest.fixture(autouse=True)
def _isolate_caches() -> Iterable[None]:
    """Clear module-level caches that would otherwise leak between tests."""
    rule_binding.clear_cache()
    find_repo_root.cache_clear()
    yield
    rule_binding.clear_cache()
    find_repo_root.cache_clear()


@pytest.fixture
def consumer_repo(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a minimal consumer repo under ``pytester.path`` and pin caches at it."""
    repo = pytester.path
    _write_repo_skeleton(repo)
    # Pin find_repo_root deterministically to this fixture repo.
    monkeypatch.setenv("ATDD_REPO_ROOT", str(repo))
    find_repo_root.cache_clear()
    # Pin rule_binding's repo-rule walker to the fixture repo so bind_rule
    # picks up the synthetic plan/ tree (and only that tree).
    rule_binding.clear_cache(override_repo_root=repo)
    return repo


def _run_inner_pytest(pytester: pytest.Pytester, *args: str):
    """Invoke pytester with the substrate plugin explicitly loaded."""
    return pytester.runpytest("-p", "atdd.tester.substrate.plugin", "-p", "no:cacheprovider", *args)


# ---------------------------------------------------------------------------
# Acceptance criterion 1 — anchored failing test produces a Violation routed
# through the gate as ``test_foo::test_thing``.
# ---------------------------------------------------------------------------
def test_anchored_failing_test_produces_violation(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    _write_wmbt(consumer_repo, "foo", [{
        "acc_urn": "acc:foo:D003-UNIT-001-thing",
        "purpose": "thing must hold",
        "then_first": "thing holds in code",
    }])
    test_path = consumer_repo / "tests" / "test_foo.py"
    test_path.write_text(
        _make_test_module(body="def test_thing():\n    assert False, 'boom'\n"),
        encoding="utf-8",
    )

    result = _run_inner_pytest(pytester, str(test_path))

    result.assert_outcomes(failed=1)
    text = "\n".join(result.outlines)
    assert "rule_id=repo.foo.D003-acc-unit-001" in text
    assert "validator=test_foo::test_thing" in text
    assert "[repo.foo.D003-acc-unit-001 sev=4" in text


# ---------------------------------------------------------------------------
# Acceptance criterion 2 — three sibling tests, one fails: only one Violation.
# ---------------------------------------------------------------------------
def test_n_to_one_one_fail_two_pass(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    _write_wmbt(consumer_repo, "foo", [{
        "acc_urn": "acc:foo:D003-UNIT-001-thing",
        "purpose": "thing must hold",
        "then_first": "thing holds in code",
    }])
    test_path = consumer_repo / "tests" / "test_foo.py"
    test_path.write_text(
        _make_test_module(body=(
            "def test_one():\n    assert True\n"
            "def test_two():\n    assert False, 'boom'\n"
            "def test_three():\n    assert True\n"
        )),
        encoding="utf-8",
    )

    result = _run_inner_pytest(pytester, str(test_path))

    result.assert_outcomes(passed=2, failed=1)
    text = "\n".join(result.outlines)
    # Exactly one substrate failure block — only the failing item names a validator.
    assert text.count("validator=test_foo::test_two") >= 1
    assert "validator=test_foo::test_one" not in text
    assert "validator=test_foo::test_three" not in text


# ---------------------------------------------------------------------------
# Acceptance criterion 3 — # atdd:suppress on the assertion does not silence
# a strict-disposition repo rule.
# ---------------------------------------------------------------------------
def test_suppress_marker_does_not_silence_repo_rule(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    _write_wmbt(consumer_repo, "foo", [{
        "acc_urn": "acc:foo:D003-UNIT-001-thing",
        "purpose": "thing must hold",
        "then_first": "thing holds in code",
    }])
    test_path = consumer_repo / "tests" / "test_foo.py"
    test_path.write_text(
        _make_test_module(body=(
            "def test_thing():\n"
            "    assert False  # atdd:suppress(repo.foo.D003-acc-unit-001) UNTIL=2027-01-01\n"
        )),
        encoding="utf-8",
    )

    result = _run_inner_pytest(pytester, str(test_path))

    # Repo rules are STRICT regardless of suppression markers.
    result.assert_outcomes(failed=1)
    text = "\n".join(result.outlines)
    assert "rule_id=repo.foo.D003-acc-unit-001" in text
    assert "disposition=strict" in text


# ---------------------------------------------------------------------------
# Acceptance criterion 4 — failure block carries description: + fix_hint:.
# ---------------------------------------------------------------------------
def test_failure_block_includes_description_and_fix_hint(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    _write_wmbt(consumer_repo, "foo", [{
        "acc_urn": "acc:foo:D003-UNIT-001-thing",
        "purpose": "thing must hold in production",
        "then_first": "thing holds in code",
    }])
    test_path = consumer_repo / "tests" / "test_foo.py"
    test_path.write_text(
        _make_test_module(body="def test_thing():\n    assert False, 'boom'\n"),
        encoding="utf-8",
    )

    result = _run_inner_pytest(pytester, str(test_path))

    result.assert_outcomes(failed=1)
    text = "\n".join(result.outlines)
    assert "description: thing must hold in production" in text
    assert "fix_hint:" in text
    assert "thing holds in code" in text


# ---------------------------------------------------------------------------
# Acceptance criterion 5 — two anchored failures get distinct gate calls.
# ---------------------------------------------------------------------------
def test_two_anchored_failures_get_distinct_gate_calls(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    _write_wmbt(consumer_repo, "foo", [{
        "acc_urn": "acc:foo:D003-UNIT-001-thing",
        "purpose": "thing must hold",
        "then_first": "thing holds in code",
    }])
    test_path = consumer_repo / "tests" / "test_foo.py"
    test_path.write_text(
        _make_test_module(body=(
            "def test_one():\n    assert False, 'one boom'\n"
            "def test_two():\n    assert False, 'two boom'\n"
        )),
        encoding="utf-8",
    )

    result = _run_inner_pytest(pytester, str(test_path))

    result.assert_outcomes(failed=2)
    text = "\n".join(result.outlines)
    assert "validator=test_foo::test_one" in text
    assert "validator=test_foo::test_two" in text


# ---------------------------------------------------------------------------
# Acceptance criterion 6 — test without anchor headers behaves normally.
# ---------------------------------------------------------------------------
def test_unanchored_test_no_substrate_violation(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    test_path = consumer_repo / "tests" / "test_plain.py"
    test_path.write_text(
        "def test_plain():\n    assert False, 'boom'\n",
        encoding="utf-8",
    )

    result = _run_inner_pytest(pytester, str(test_path))

    result.assert_outcomes(failed=1)
    text = "\n".join(result.outlines)
    # No substrate enrichment: no rule_id=repo.* line, no disposition=strict
    # block from the gate.
    assert "rule_id=repo." not in text
    assert "[disposition gate]" not in text


# ---------------------------------------------------------------------------
# Acceptance criterion 8 — three acceptances + three anchored tests, all run.
# ---------------------------------------------------------------------------
def test_three_acceptances_three_anchored_tests_all_run(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    _write_wmbt(consumer_repo, "foo", [
        {
            "acc_urn": "acc:foo:D003-UNIT-001-one",
            "purpose": "one must hold",
            "then_first": "one holds",
        },
        {
            "acc_urn": "acc:foo:D003-UNIT-002-two",
            "purpose": "two must hold",
            "then_first": "two holds",
        },
        {
            "acc_urn": "acc:foo:D003-UNIT-003-three",
            "purpose": "three must hold",
            "then_first": "three holds",
        },
    ])
    for i, acc in enumerate([
        ("acc:foo:D003-UNIT-001-one", "test_one"),
        ("acc:foo:D003-UNIT-002-two", "test_two"),
        ("acc:foo:D003-UNIT-003-three", "test_three"),
    ], start=1):
        urn, fn = acc
        path = consumer_repo / "tests" / f"test_acc_{i}.py"
        body = (
            f"def {fn}():\n    assert False, 'boom-{i}'\n"
        )
        path.write_text(
            _make_test_module(body=body, acc_urn=urn),
            encoding="utf-8",
        )

    result = _run_inner_pytest(pytester, str(consumer_repo / "tests"))

    result.assert_outcomes(failed=3)
    text = "\n".join(result.outlines)
    assert "rule_id=repo.foo.D003-acc-unit-001" in text
    assert "rule_id=repo.foo.D003-acc-unit-002" in text
    assert "rule_id=repo.foo.D003-acc-unit-003" in text
    assert "validator=test_acc_1::test_one" in text
    assert "validator=test_acc_2::test_two" in text
    assert "validator=test_acc_3::test_three" in text

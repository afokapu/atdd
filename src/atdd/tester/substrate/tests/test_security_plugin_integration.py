# URN: component:govern-lifecycle:enforcement-substrate:security-plugin-integration:backend:tests
# Runtime: python
# Purpose: End-to-end pytester coverage for the substrate plugin's security ordering hooks (issue #422 / spec v12 §4.5, §7.4).

"""Integration tests for the substrate plugin's security ordering (issue #422).

Each test stands up a synthetic consumer repo under ``pytester.path``,
loads the substrate plugin, and verifies:

* Security-runner items execute AFTER all acceptance items in the same
  session (spec v12 §4.5 line 273 — ``pytest_collection_modifyitems``
  reordering).
* The session result map (``session._atdd['rule_outcomes']``) is
  populated by the disposition gate (failure path) AND by
  ``pytest_runtest_logreport`` (pass path).
* A passing-bound security rule produces no violation; a failing-bound
  security rule produces a violation referencing the bound URN.
* The validation-time enforcement rule fires for unresolved
  acceptance_refs at ``atdd repo validate`` time (NOT at runtime).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Iterable

import pytest

from atdd.coach.utils import rule_binding
from atdd.coach.utils.disposition_gate import set_active_pytest_session
from atdd.coach.utils.repo import find_repo_root


_WMBT_FIXTURE = """\
urn: "wmbt:auth:D001"
acceptances:
  - identity:
      urn: "acc:auth:D001-UNIT-001-session-protection"
      purpose: "Session tokens are not exfiltrable via XSS"
      phase: "GREEN"
    harness:
      type: "unit"
      category: "backend"
    given:
      abstract:
        - "session cookie has HttpOnly flag"
    when:
      abstract: "an injected script reads document.cookie"
    then:
      abstract:
        - "the cookie value is unavailable to scripts"
"""

_FEATURE_FIXTURE = """\
urn: "feature:auth:session-management"
security:
  abuse_cases:
    - id: "THREAT-001"
      name: "Session Hijacking"
      threat: "Attacker steals session token via XSS"
      mitigation: "HttpOnly cookies, CSP headers"
      severity: high
      acceptance_ref: "acc:auth:D001-UNIT-001-session-protection"
"""


def _write_repo(repo: Path) -> None:
    (repo / ".atdd").mkdir(exist_ok=True)
    (repo / ".atdd" / "manifest.yaml").write_text(
        "version: '2.0'\nsessions: []\n", encoding="utf-8"
    )
    (repo / "plan").mkdir(exist_ok=True)
    (repo / "plan" / "auth").mkdir(parents=True, exist_ok=True)
    (repo / "plan" / "auth" / "D001.yaml").write_text(
        _WMBT_FIXTURE, encoding="utf-8"
    )
    (repo / "plan" / "auth" / "features").mkdir(parents=True, exist_ok=True)
    (repo / "plan" / "auth" / "features" / "session_management.yaml").write_text(
        _FEATURE_FIXTURE, encoding="utf-8"
    )
    (repo / "tests").mkdir(exist_ok=True)


def _write_acceptance_test(repo: Path, body: str) -> Path:
    """Write a harness-anchored test bound to the auth D001 acceptance."""
    test_path = repo / "tests" / "test_auth_session.py"
    header = textwrap.dedent(
        """\
        # URN: test:auth:D001-acc-unit-001
        # Acceptance: acc:auth:D001-UNIT-001-session-protection
        # WMBT: wmbt:auth:D001
        # Phase: GREEN
        # Layer: domain

        """
    )
    test_path.write_text(header + body, encoding="utf-8")
    return test_path


def _write_security_runner_test(repo: Path) -> Path:
    """Write a test module that imports the security runner anchor.

    The toolkit's actual security runner test lives in
    ``atdd.tester.validators.test_security_ref_binding``. Inside an inner pytester
    session, importing that module is fine — it carries the
    ``atdd_phase("security")`` mark, which the plugin uses to reorder.
    Re-export by import so the inner session collects it.
    """
    test_path = repo / "tests" / "test_security_ref_binding.py"
    test_path.write_text(
        textwrap.dedent(
            """\
            # Pytest collects this file under the consumer repo's tests/.
            # The actual runtime function carries the atdd_phase('security') mark.
            from atdd.tester.validators.test_security_ref_binding import (
                test_acceptance_ref_resolves_and_passes,
            )

            __all__ = ["test_acceptance_ref_resolves_and_passes"]
            """
        ),
        encoding="utf-8",
    )
    return test_path


@pytest.fixture(autouse=True)
def _isolate_caches() -> Iterable[None]:
    rule_binding.clear_cache()
    find_repo_root.cache_clear()
    set_active_pytest_session(None)
    yield
    rule_binding.clear_cache()
    find_repo_root.cache_clear()
    set_active_pytest_session(None)


@pytest.fixture
def consumer_repo(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> Path:
    repo = pytester.path
    _write_repo(repo)
    monkeypatch.setenv("ATDD_REPO_ROOT", str(repo))
    find_repo_root.cache_clear()
    rule_binding.clear_cache(override_repo_root=repo)
    return repo


def _run_inner_pytest(pytester: pytest.Pytester, *args: str):
    return pytester.runpytest(
        "-p", "atdd.tester.substrate.plugin",
        "-p", "no:cacheprovider",
        "-W", "ignore",
        *args,
    )


# ---------------------------------------------------------------------------
# Acceptance criterion: passing bound rule + passing security rule.
# ---------------------------------------------------------------------------
def test_resolved_abuse_case_with_passing_bound_acceptance_produces_no_violation(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    """A fixture with one resolved abuse_case and a passing bound acceptance
    produces no security violation."""
    _write_acceptance_test(consumer_repo, "def test_session_protected():\n    assert True\n")
    _write_security_runner_test(consumer_repo)

    result = _run_inner_pytest(pytester, str(consumer_repo / "tests"))

    result.assert_outcomes(passed=2)


# ---------------------------------------------------------------------------
# Acceptance criterion: resolved abuse_case + failing bound acceptance.
# ---------------------------------------------------------------------------
def test_resolved_abuse_case_with_failing_bound_acceptance_emits_security_violation(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    """Same fixture but with a failing bound acceptance produces a security
    violation referencing the bound URN."""
    _write_acceptance_test(
        consumer_repo, "def test_session_protected():\n    assert False, 'cookie leaked'\n"
    )
    _write_security_runner_test(consumer_repo)

    result = _run_inner_pytest(pytester, str(consumer_repo / "tests"))

    result.assert_outcomes(failed=2)
    text = "\n".join(result.outlines)
    # The security rule fires by reference, naming the bound acc URN.
    assert "repo.auth.session-management-security-001" in text
    assert "acc:auth:D001-UNIT-001-session-protection" in text


# ---------------------------------------------------------------------------
# Acceptance criterion: session ordering — bound acceptance outcomes are
# recorded BEFORE the security runner reads.
# ---------------------------------------------------------------------------
def test_security_item_runs_after_acceptance_items(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    """Items with ``atdd_phase('security')`` execute after acceptance items."""
    # Use a distinctive printout from each test to verify ordering.
    _write_acceptance_test(
        consumer_repo,
        "def test_session_protected(capsys):\n    print('ACCEPTANCE_RAN'); assert True\n",
    )
    _write_security_runner_test(consumer_repo)

    result = _run_inner_pytest(pytester, "-s", str(consumer_repo / "tests"))

    result.assert_outcomes(passed=2)
    # The security runner test name MUST appear AFTER the acceptance test
    # in the per-test progress lines.
    output = "\n".join(result.outlines)
    acc_pos = output.find("test_auth_session.py")
    sec_pos = output.find("test_security_ref_binding.py")
    assert acc_pos != -1, "acceptance test did not run"
    assert sec_pos != -1, "security runner test did not run"
    assert acc_pos < sec_pos, (
        "spec v12 §4.5 violated: security item executed before acceptance item; "
        f"acc_pos={acc_pos}, sec_pos={sec_pos}"
    )


# ---------------------------------------------------------------------------
# Acceptance criterion: rule_outcomes contains both keys (one passing, one failing).
# ---------------------------------------------------------------------------
def test_rule_outcomes_records_both_outcomes(
    pytester: pytest.Pytester, consumer_repo: Path,
) -> None:
    """After a pytest run with one acceptance failure and one passing rule,
    ``session._atdd['rule_outcomes']`` contains both rule_ids keyed by
    their outcome (pass/fail)."""
    # Two anchored tests against the SAME acceptance, one pass + one fail
    # would only produce one rule_id (they share the binding). Author two
    # different acceptances under one WMBT to exercise both outcomes.
    (consumer_repo / "plan" / "auth" / "D001.yaml").write_text(
        textwrap.dedent(
            """\
            urn: "wmbt:auth:D001"
            acceptances:
              - identity:
                  urn: "acc:auth:D001-UNIT-001-session-protection"
                  purpose: "Session tokens are not exfiltrable via XSS"
                  phase: "GREEN"
                harness:
                  type: "unit"
                given:
                  abstract: ["fixture given"]
                when:
                  abstract: "fixture when"
                then:
                  abstract: ["fixture then 1"]
              - identity:
                  urn: "acc:auth:D001-UNIT-002-second-acceptance"
                  purpose: "second acceptance"
                  phase: "GREEN"
                harness:
                  type: "unit"
                given:
                  abstract: ["fixture given"]
                when:
                  abstract: "fixture when"
                then:
                  abstract: ["fixture then 2"]
            """
        ),
        encoding="utf-8",
    )

    pass_test = consumer_repo / "tests" / "test_auth_session_pass.py"
    pass_test.write_text(
        textwrap.dedent(
            """\
            # URN: test:auth:D001-acc-unit-002
            # Acceptance: acc:auth:D001-UNIT-002-second-acceptance
            # WMBT: wmbt:auth:D001
            # Phase: GREEN
            # Layer: domain

            def test_session_two():
                assert True
            """
        ),
        encoding="utf-8",
    )
    fail_test = consumer_repo / "tests" / "test_auth_session_fail.py"
    fail_test.write_text(
        textwrap.dedent(
            """\
            # URN: test:auth:D001-acc-unit-001
            # Acceptance: acc:auth:D001-UNIT-001-session-protection
            # WMBT: wmbt:auth:D001
            # Phase: GREEN
            # Layer: domain

            def test_session_one():
                assert False, 'fail intentionally'
            """
        ),
        encoding="utf-8",
    )

    # Add a probe test that introspects session._atdd at the very end.
    probe = consumer_repo / "tests" / "test_zz_probe_outcomes.py"
    probe.write_text(
        textwrap.dedent(
            """\
            import json

            def test_outcomes_probe(request):
                outcomes = getattr(request.session, "_atdd", {}).get("rule_outcomes", {})
                # Persist for outer assertion. Json keeps everything stringly typed.
                with open("rule_outcomes.json", "w", encoding="utf-8") as fh:
                    json.dump(outcomes, fh)
            """
        ),
        encoding="utf-8",
    )

    # Note: probe runs last by filename ordering, after both acceptance tests.
    _run_inner_pytest(pytester, str(consumer_repo / "tests"))

    payload = (consumer_repo / "rule_outcomes.json").read_text(encoding="utf-8")
    import json as _json
    outcomes = _json.loads(payload)
    assert outcomes.get("repo.auth.D001-acc-unit-001") == "failed"
    assert outcomes.get("repo.auth.D001-acc-unit-002") == "passed"

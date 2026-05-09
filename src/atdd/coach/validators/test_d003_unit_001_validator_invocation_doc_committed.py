# URN: test:freeze-runtime-contracts:runtime-schema-freeze:D003-UNIT-001-validator-invocation-doc-committed
# Acceptance: acc:freeze-runtime-contracts:D003-UNIT-001-validator-invocation-doc-committed
# WMBT: wmbt:freeze-runtime-contracts:D003
# Phase: RED
# Layer: backend.integration
# Assertion: structural

"""
D003-UNIT-001 — ``src/atdd/coach/schemas/validator-invocation.md``
specifies the full subprocess contract: pytest CLI flags,
``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` policy, per-phase timeout defaults,
retry-on-subprocess-crash distinguished from retry-on-test-failure, and
the env vars passed through to validator subprocesses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
DOC = ATDD_PKG_DIR / "coach" / "schemas" / "validator-invocation.md"


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert DOC.exists(), (
        f"Missing {DOC}. Acceptance D003-UNIT-001 requires "
        f"validator-invocation.md committed at "
        f"src/atdd/coach/schemas/validator-invocation.md."
    )
    return DOC.read_text(encoding="utf-8")


def test_doc_specifies_pytest_cli_flags(doc_text: str) -> None:
    """Pytest CLI flag set used to invoke validators is enumerated."""
    # Coach invokes validators with these representative flags. The doc
    # must enumerate enough of them that downstream tracks can quote the
    # contract verbatim.
    for flag in ("-p ", "--tb=", "-q", "--strict-markers"):
        assert flag in doc_text, (
            f"validator-invocation.md does not mention pytest flag "
            f"{flag!r}. WMBT D003-UNIT-001 requires the pytest CLI "
            f"flag set to be enumerated."
        )


def test_doc_states_plugin_autoload_policy(doc_text: str) -> None:
    """``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` policy is stated with rationale."""
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" in doc_text, (
        "validator-invocation.md must declare the "
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 policy."
    )
    # Rationale: any of these markers indicates the doc explains the
    # 'why', not just the value.
    rationale_signals = ("rationale", "Rationale", "because", "to prevent")
    assert any(s in doc_text for s in rationale_signals), (
        "validator-invocation.md must explain the rationale for "
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 (why, not just what)."
    )


def test_doc_states_per_phase_timeout_defaults(doc_text: str) -> None:
    """Per-phase timeout defaults and override mechanism are stated."""
    assert "timeout" in doc_text.lower(), (
        "validator-invocation.md must specify per-phase timeout defaults."
    )
    # Each ATDD phase that runs validators must appear so per-phase
    # tunability is unambiguous.
    for phase in ("RED", "GREEN", "SMOKE", "REFACTOR"):
        assert phase in doc_text, (
            f"validator-invocation.md must enumerate phase {phase!r} "
            f"in its per-phase timeout section."
        )
    assert "override" in doc_text.lower(), (
        "validator-invocation.md must describe the timeout override "
        "mechanism (env var, config key, or CLI flag)."
    )


def test_doc_distinguishes_subprocess_crash_from_test_failure(doc_text: str) -> None:
    """Retry-on-subprocess-crash is explicitly distinguished from retry-on-test-failure."""
    assert "subprocess crash" in doc_text.lower() or "subprocess-crash" in doc_text.lower(), (
        "validator-invocation.md must mention subprocess-crash retry policy."
    )
    assert "test failure" in doc_text.lower() or "test-failure" in doc_text.lower(), (
        "validator-invocation.md must mention test-failure retry policy."
    )
    # The two must be distinguished — "different signal handling" or
    # similar wording must appear.
    assert "signal" in doc_text.lower() or "distinct" in doc_text.lower() or "different" in doc_text.lower(), (
        "validator-invocation.md must distinguish the two retry "
        "policies (different signal handling)."
    )


def test_doc_enumerates_env_passthrough(doc_text: str) -> None:
    """Env vars passed through to validator subprocesses are enumerated."""
    # Section header and at least the universally-passed env vars.
    assert "env" in doc_text.lower(), (
        "validator-invocation.md must enumerate env-var passthrough."
    )
    for var in ("PATH", "HOME", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"):
        assert var in doc_text, (
            f"validator-invocation.md must list {var!r} in its env "
            f"passthrough enumeration."
        )

# URN: component:govern-lifecycle:enforcement-substrate:disposition_gate:backend:tests
# Runtime: python
# Purpose: Cover the three disposition modes + suppression-marker matching for issue #395.

"""
Unit tests for ``atdd.coach.utils.disposition_gate.assert_disposition_satisfied``.

These tests build a minimal fake registry in-memory (no convention I/O) and
synthesize ``Violation`` records pointing into a ``tmp_path`` workspace —
the gate reads those files when matching ``# atdd:suppress(...)`` markers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.coach.validators._violation import Violation


def _meta(
    rule_id: str,
    disposition: str,
    description: str = "fixture rule",
    fix_hint: str | None = None,
) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        convention_path=Path("/dev/null"),
        severity=3,
        description=description,
        disposition=disposition,
        fix_hint=fix_hint,
    )


def _registry(*pairs: tuple[str, str]) -> Dict[str, RuleMetadata]:
    return {rid: _meta(rid, disp) for rid, disp in pairs}


def _write(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Empty list — pass silently
# ---------------------------------------------------------------------------

def test_empty_violations_passes():
    assert_disposition_satisfied(
        validator_id="vid",
        violations=[],
        registry={},
    )


# ---------------------------------------------------------------------------
# strict — any violation fails
# ---------------------------------------------------------------------------

def test_strict_fails_on_any_violation(tmp_path):
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="print_in_production",
            violations=[v],
            registry=_registry(("LOG-PRINT-001", "strict")),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "LOG-PRINT-001" in msg
    assert "disposition=strict" in msg
    assert "code.py:1" in msg


def test_unknown_rule_id_defaults_to_strict(tmp_path):
    target = _write(tmp_path / "x.py", "noop\n")
    v = Violation(
        rule_id="UNREGISTERED-001",
        severity=2,
        location=f"{target.name}:1",
        detail="who knows",
    )
    with pytest.raises(pytest.fail.Exception):
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry={},  # empty registry
            repo_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# suppress-and-clean — markers absorb pre-existing violations
# ---------------------------------------------------------------------------

def test_suppress_and_clean_with_marker_passes(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('x')  # atdd:suppress(LOG-PRINT-001)\n",
    )
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    # Should pass silently — marker absorbs the violation.
    assert_disposition_satisfied(
        validator_id="print_in_production",
        violations=[v],
        registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
        repo_root=tmp_path,
    )


def test_suppress_and_clean_without_marker_fails(tmp_path):
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="print_in_production",
            violations=[v],
            registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "LOG-PRINT-001" in msg
    assert "atdd:suppress(LOG-PRINT-001)" in msg
    assert "UNTIL=" in msg


def test_suppress_and_clean_marker_with_until_passes(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('x')  # atdd:suppress(LOG-PRINT-001) UNTIL=2099-01-01\n",
    )
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    assert_disposition_satisfied(
        validator_id="print_in_production",
        violations=[v],
        registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
        repo_root=tmp_path,
    )


def test_suppress_and_clean_partial_suppression(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('a')  # atdd:suppress(LOG-PRINT-001)\n"
        "print('b')\n",
    )
    suppressed = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    fresh = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:2",
        detail="print() in production code",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="print_in_production",
            violations=[suppressed, fresh],
            registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "1 unsuppressed" in msg
    assert "1 suppressed" in msg
    # The suppressed line:1 should NOT be in the punch list; line:2 should.
    assert "code.py:2" in msg


# ---------------------------------------------------------------------------
# advisory — warns and passes
# ---------------------------------------------------------------------------

def test_advisory_warns_and_passes(tmp_path, recwarn):
    target = _write(tmp_path / "code.py", "x\n")
    v = Violation(
        rule_id="STYLE-NIT-001",
        severity=1,
        location=f"{target.name}:1",
        detail="trailing whitespace",
    )
    assert_disposition_satisfied(
        validator_id="style_nits",
        violations=[v],
        registry=_registry(("STYLE-NIT-001", "advisory")),
        repo_root=tmp_path,
    )
    assert any("STYLE-NIT-001" in str(w.message) for w in recwarn.list)


# ---------------------------------------------------------------------------
# Mixed dispositions in one call
# ---------------------------------------------------------------------------

def test_mixed_dispositions_routed_independently(tmp_path):
    target = _write(
        tmp_path / "code.py",
        "print('a')\n"  # strict bucket — line 1
        "print('b')  # atdd:suppress(LOG-CLEAN-001)\n"  # suppress-and-clean — line 2
        "print('c')\n",  # advisory bucket — line 3
    )
    strict_v = Violation(
        rule_id="LOG-STRICT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="strict",
    )
    suppressed_v = Violation(
        rule_id="LOG-CLEAN-001",
        severity=3,
        location=f"{target.name}:2",
        detail="suppressed",
    )
    advisory_v = Violation(
        rule_id="LOG-ADVISE-001",
        severity=1,
        location=f"{target.name}:3",
        detail="advisory",
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="mixed",
            violations=[strict_v, suppressed_v, advisory_v],
            registry=_registry(
                ("LOG-STRICT-001", "strict"),
                ("LOG-CLEAN-001", "suppress-and-clean"),
                ("LOG-ADVISE-001", "advisory"),
            ),
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "LOG-STRICT-001" in msg
    # Suppressed and advisory entries must NOT show up in the failure body
    assert "LOG-CLEAN-001" not in msg
    assert "LOG-ADVISE-001" not in msg


# ---------------------------------------------------------------------------
# Opaque legacy callers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Enriched output: description + fix_hint surfaced from registry (issue #402)
# ---------------------------------------------------------------------------

def test_failure_includes_description_when_set(tmp_path):
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() at line 1",
    )
    registry = {
        "LOG-PRINT-001": _meta(
            "LOG-PRINT-001",
            "strict",
            description="print() in production code is not allowed",
        )
    }
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry=registry,
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "description: print() in production code is not allowed" in msg


def test_failure_includes_fix_hint_when_set(tmp_path):
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() at line 1",
    )
    registry = {
        "LOG-PRINT-001": _meta(
            "LOG-PRINT-001",
            "suppress-and-clean",
            description="prefer logging",
            fix_hint="Use logging.info() instead of print().",
        )
    }
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry=registry,
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "fix_hint:    Use logging.info() instead of print()." in msg
    # Suppress-marker template still appears under suppress-and-clean
    assert "atdd:suppress(LOG-PRINT-001)" in msg


def test_failure_omits_fields_when_not_set(tmp_path):
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() at line 1",
    )
    # description="" + fix_hint=None — neither line should appear.
    registry = {
        "LOG-PRINT-001": _meta(
            "LOG-PRINT-001",
            "strict",
            description="",
            fix_hint=None,
        )
    }
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry=registry,
            repo_root=tmp_path,
        )
    msg = str(excinfo.value)
    assert "description:" not in msg
    assert "fix_hint:" not in msg


def test_advisory_block_includes_description_and_fix_hint(tmp_path, recwarn):
    target = _write(tmp_path / "code.py", "x\n")
    v = Violation(
        rule_id="STYLE-NIT-001",
        severity=1,
        location=f"{target.name}:1",
        detail="trailing whitespace",
    )
    registry = {
        "STYLE-NIT-001": _meta(
            "STYLE-NIT-001",
            "advisory",
            description="trailing whitespace is discouraged",
            fix_hint="Run `ruff format` to clean up.",
        )
    }
    assert_disposition_satisfied(
        validator_id="style_nits",
        violations=[v],
        registry=registry,
        repo_root=tmp_path,
    )
    messages = [str(w.message) for w in recwarn.list]
    assert any(
        "description: trailing whitespace is discouraged" in m for m in messages
    )
    assert any("fix_hint:    Run `ruff format` to clean up." in m for m in messages)


def test_opaque_violations_default_strict():
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_disposition_satisfied(
            validator_id="legacy",
            violations=["bare string violation"],
            registry={},
        )
    assert "legacy" in str(excinfo.value)
    assert "bare string violation" in str(excinfo.value)


# ---------------------------------------------------------------------------
# GitHub Actions annotations (issue #404)
# ---------------------------------------------------------------------------

def test_emits_github_annotation_on_failure(tmp_path, monkeypatch, capsys):
    """Strict failure under GITHUB_ACTIONS=true must emit a ::error:: directive."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() at line 1",
    )
    registry = {
        "LOG-PRINT-001": _meta(
            "LOG-PRINT-001",
            "strict",
            description="print() in production code is not allowed",
            fix_hint="Use logging.info() instead.",
        )
    }
    with pytest.raises(pytest.fail.Exception):
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry=registry,
            repo_root=tmp_path,
        )
    captured = capsys.readouterr().out
    # Directive shape: file= + line= + title= + delimited message.
    assert "::error " in captured
    assert "file=code.py" in captured
    assert "line=1" in captured
    assert "title=LOG-PRINT-001" in captured
    assert "print() in production code is not allowed" in captured
    assert "fix: Use logging.info() instead." in captured
    assert "site: print() at line 1" in captured


def test_emits_github_warning_for_advisory(tmp_path, monkeypatch, capsys):
    """Advisory disposition under GITHUB_ACTIONS=true emits ::warning::, not ::error::."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    target = _write(tmp_path / "code.py", "x\n")
    v = Violation(
        rule_id="STYLE-NIT-001",
        severity=1,
        location=f"{target.name}:1",
        detail="trailing whitespace",
    )
    registry = {
        "STYLE-NIT-001": _meta(
            "STYLE-NIT-001",
            "advisory",
            description="trailing whitespace is discouraged",
            fix_hint="Run `ruff format` to clean up.",
        )
    }
    assert_disposition_satisfied(
        validator_id="style_nits",
        violations=[v],
        registry=registry,
        repo_root=tmp_path,
    )
    captured = capsys.readouterr().out
    assert "::warning " in captured
    assert "::error " not in captured
    assert "title=STYLE-NIT-001" in captured
    assert "fix: Run `ruff format` to clean up." in captured


def test_no_annotations_outside_github_actions(tmp_path, monkeypatch, capsys):
    """Helper is a no-op when GITHUB_ACTIONS != 'true' — local runs stay clean."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() at line 1",
    )
    with pytest.raises(pytest.fail.Exception):
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry=_registry(("LOG-PRINT-001", "strict")),
            repo_root=tmp_path,
        )
    captured = capsys.readouterr().out
    assert "::error" not in captured
    assert "::warning" not in captured


def test_annotation_uses_see_convention_when_fix_hint_missing(
    tmp_path, monkeypatch, capsys
):
    """When the rule has no fix_hint, the annotation falls back to 'see convention'."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() at line 1",
    )
    registry = {
        "LOG-PRINT-001": _meta(
            "LOG-PRINT-001",
            "strict",
            description="rule with no fix_hint",
            fix_hint=None,
        )
    }
    with pytest.raises(pytest.fail.Exception):
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry=registry,
            repo_root=tmp_path,
        )
    captured = capsys.readouterr().out
    assert "fix: see convention" in captured


def test_suppressed_violations_do_not_annotate(tmp_path, monkeypatch, capsys):
    """A line carrying an inline suppress marker must NOT emit an annotation."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    target = _write(
        tmp_path / "code.py",
        "print('x')  # atdd:suppress(LOG-PRINT-001)\n",
    )
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="print() in production code",
    )
    assert_disposition_satisfied(
        validator_id="vid",
        violations=[v],
        registry=_registry(("LOG-PRINT-001", "suppress-and-clean")),
        repo_root=tmp_path,
    )
    captured = capsys.readouterr().out
    assert "::error" not in captured
    assert "::warning" not in captured


def test_annotation_message_strips_newlines_and_double_colons(
    tmp_path, monkeypatch, capsys
):
    """``::`` and newlines in registry text would break the directive — sanitize."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    target = _write(tmp_path / "code.py", "print('x')\n")
    v = Violation(
        rule_id="LOG-PRINT-001",
        severity=3,
        location=f"{target.name}:1",
        detail="multiline\ndetail with :: inside",
    )
    registry = {
        "LOG-PRINT-001": _meta(
            "LOG-PRINT-001",
            "strict",
            description="first line\nsecond line",
            fix_hint="hint :: with marker",
        )
    }
    with pytest.raises(pytest.fail.Exception):
        assert_disposition_satisfied(
            validator_id="vid",
            violations=[v],
            registry=registry,
            repo_root=tmp_path,
        )
    captured = capsys.readouterr().out
    # Exactly one annotation line emitted (no newline broke it apart).
    annotation_lines = [
        ln for ln in captured.splitlines() if ln.startswith("::error ")
    ]
    assert len(annotation_lines) == 1
    line = annotation_lines[0]
    # The header `::error ...::` is the only `::` we keep — message has none.
    head, _, message = line.partition("::")
    head, _, message = (head + "::" + message).partition(line[:7])  # noqa: F841
    assert "\n" not in line
    # First-line truncation: "second line" must NOT appear in annotation.
    assert "second line" not in line
    # Message portion (after the second `::`) must not contain `::`.
    body = line.split("::", 2)[2]
    assert "::" not in body

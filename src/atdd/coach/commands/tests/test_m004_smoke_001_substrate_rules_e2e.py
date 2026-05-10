# URN: test:observe-and-correct:observer-runtime-and-rules:M004-SMOKE-001-substrate-rules-e2e
# Acceptance: acc:observe-and-correct:M004-UNIT-001-rule-10-stale-suppression
# WMBT: wmbt:observe-and-correct:M004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M004-SMOKE-001 — End-to-end verification that the four substrate-aware
observer rules ship under the toolkit, load via the live RuleRegistry,
fire against a real worktree on disk, and persist schema-valid
corrections to ``.atdd/runtime/agents/<id>/corrections.jsonl``.

The unit tests at ``test_m004_unit_001..004`` build rules in isolation;
this smoke test exercises the full path via ``Observer.load_rules()``
+ ``Observer.scan_once()`` against a real fs-backed agent dir.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import atdd

pytestmark = [pytest.mark.platform]

PKG_DIR = Path(atdd.__file__).resolve().parent
RULES_DIR = PKG_DIR / "coach" / "observer" / "rules"
CORRECTION_SCHEMA_PATH = (
    PKG_DIR / "coach" / "schemas" / "correction.schema.json"
)


# Build the marker text at runtime so the literal `atdd:suppress(...)` token
# is not present in this test source — otherwise
# coach.rule-id.stale-suppression scans this fixture file itself.
_MARKER_PREFIX = "atdd:" + "suppress"


def _stale_marker(rule_id: str, until: str = "2025-01-01") -> str:
    return f"# {_MARKER_PREFIX}({rule_id}) UNTIL={until}"


def _correction_schema() -> dict:
    return json.loads(CORRECTION_SCHEMA_PATH.read_text())


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_all_four_substrate_rules_ship_and_load(tmp_path: Path):
    """The toolkit ships all four rules; ``Observer.load_rules()`` loads
    them with no load errors against a clean worktree."""
    from atdd.coach.commands import observer

    runtime = tmp_path / "runtime"
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    obs = observer.Observer(
        agent_id="smoke",
        runtime_dir=runtime,
        rules_dir=RULES_DIR,
        worktree=worktree,
    )
    obs.load_rules()

    rule_ids = {r.rule_id for r in obs.registry.rules}
    expected = {
        "coach.observer.stale-suppression-detected",
        "coach.observer.unbound-rule-id-in-validator",
        "coach.observer.rule-id-grammar-violation",
        "coach.observer.repo-rule-disposition-declared",
    }
    assert expected.issubset(rule_ids), (
        f"missing substrate-aware rules: {expected - rule_ids}"
    )
    assert obs.registry.load_errors == [], (
        f"unexpected load errors: {obs.registry.load_errors}"
    )


def test_e2e_rule_17_fires_and_persists_schema_valid_correction(tmp_path: Path):
    """Rule 17 fires when a real plan/ YAML carries a `disposition:`,
    and the persisted correction round-trips through correction.schema.json."""
    from atdd.coach.commands import observer

    runtime = tmp_path / "runtime"
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    obs = observer.Observer(
        agent_id="smoke",
        runtime_dir=runtime,
        rules_dir=RULES_DIR,
        worktree=worktree,
    )
    obs.load_rules()
    obs.scan_once()  # baseline — worktree empty

    bad_yaml = worktree / "plan" / "test_wagon" / "M001.yaml"
    bad_yaml.parent.mkdir(parents=True, exist_ok=True)
    bad_yaml.write_text(
        """acceptances:
  - identity:
      urn: "acc:test-wagon:M001-UNIT-001-x"
    disposition: "advisory"
""",
        encoding="utf-8",
    )

    obs.scan_once()  # observer sees the new YAML, fires rule 17

    cor_path = runtime / "agents" / "smoke" / "corrections.jsonl"
    records = _read_jsonl(cor_path)
    rule_17_records = [
        r for r in records
        if r.get("rule_id") == "coach.observer.repo-rule-disposition-declared"
    ]
    assert rule_17_records, (
        f"rule 17 must persist at least one correction; got records={records}"
    )

    schema = _correction_schema()
    for rec in rule_17_records:
        jsonschema.validate(rec, schema)

    text = rule_17_records[0]["correction_text"]
    assert "Repo contract rules cannot declare disposition" in text
    assert "substrate v12 §4.4" in text


def test_e2e_rule_10_fires_for_toolkit_marker_not_repo(tmp_path: Path):
    """Rule 10 fires for a toolkit `# atdd:suppress(...)` marker but does
    NOT fire for a `repo.*` marker (substrate v12 §2)."""
    from atdd.coach.commands import observer

    runtime = tmp_path / "runtime"
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    obs = observer.Observer(
        agent_id="smoke",
        runtime_dir=runtime,
        rules_dir=RULES_DIR,
        worktree=worktree,
    )
    obs.load_rules()
    obs.scan_once()  # baseline

    src = worktree / "src" / "x.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        _stale_marker("coder.green.completion-without-commit") + "\n",
        encoding="utf-8",
    )
    repo_marker = worktree / "src" / "y.py"
    repo_marker.write_text(
        _stale_marker("repo.test-wagon.M001-acc-unit-001") + "\n",
        encoding="utf-8",
    )

    obs.scan_once()  # sees both new files; rule 10 fires only on toolkit marker

    cor_path = runtime / "agents" / "smoke" / "corrections.jsonl"
    records = _read_jsonl(cor_path)
    rule_10 = [
        r for r in records
        if r.get("rule_id") == "coach.observer.stale-suppression-detected"
    ]
    assert rule_10, "rule 10 must fire on the toolkit marker"
    rule_10_text = rule_10[0]["correction_text"]
    assert "coder.green.completion-without-commit" in rule_10_text
    assert "repo.test-wagon.M001-acc-unit-001" not in rule_10_text, (
        "rule 10 must NOT report on repo.* markers (substrate v12 §2)"
    )

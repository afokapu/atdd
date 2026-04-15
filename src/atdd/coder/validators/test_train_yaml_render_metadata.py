"""
Test that train YAML files declare render metadata that matches the
configured JSON Schema.

Validates:
- SPEC-CODER-TRAIN-0003: Every train YAML under the configured glob must
  conform to the JSON Schema at schema_path. The schema is expected to
  declare optional ``template`` (string) and ``auth_required`` (bool) under
  the train spec so the FrontendTrainRunner resolves them without guessing.

Skips cleanly when .atdd/config.yaml has no train_yaml_render_metadata key,
but fails fast if the key is present and the schema file is missing — a
misconfigured opt-in is a config error, not an opt-out.

Convention: src/atdd/coder/conventions/frontend.convention.yaml → train_composition
Config: .atdd/config.yaml → train_yaml_render_metadata
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config


REPO_ROOT = find_repo_root()

_DEFAULT_TRAINS_GLOB = "plan/_trains/**/*.yaml"


def _load_schema(schema_path: Path) -> Dict:
    """Load a JSON Schema file. Raises OSError / json.JSONDecodeError on failure."""
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _find_train_yamls(trains_glob: str) -> List[Path]:
    """Return sorted list of train YAML files matching ``trains_glob``."""
    return sorted(p for p in REPO_ROOT.glob(trains_glob) if p.is_file())


def _validate_train_yaml(
    train_path: Path,
    schema: Dict,
) -> List[str]:
    """Validate one train YAML against ``schema``.

    Returns a list of SPEC-CODER-TRAIN-0003 error message strings — empty
    list means the file passes.
    """
    from jsonschema import Draft202012Validator, ValidationError  # type: ignore

    violations: List[str] = []

    try:
        data = yaml.safe_load(train_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        violations.append(
            f"  SPEC-CODER-TRAIN-0003 FAIL: train YAML unreadable\n"
            f"    Path:      {train_path}\n"
            f"    Error:     {exc}"
        )
        return violations

    if data is None:
        return violations

    validator = Draft202012Validator(schema)
    errors: List[ValidationError] = sorted(validator.iter_errors(data), key=lambda e: e.path)

    for error in errors:
        pointer = "/".join(str(p) for p in error.absolute_path) or "<root>"
        violations.append(
            f"  SPEC-CODER-TRAIN-0003 FAIL: train YAML violates render metadata schema\n"
            f"    Path:      {train_path}\n"
            f"    At:        {pointer}\n"
            f"    Error:     {error.message}\n"
            f"    Fix:       Update the train YAML or schema to match"
        )

    return violations


def _load_render_metadata_config() -> Dict:
    config = load_atdd_config(REPO_ROOT)
    return config.get("train_yaml_render_metadata", {}) or {}


@pytest.mark.coder
def test_train_yaml_render_metadata_matches_schema():
    """SPEC-CODER-TRAIN-0003: Every train YAML must conform to the configured
    render metadata JSON Schema.

    Given: .atdd/config.yaml contains a train_yaml_render_metadata block with
           a schema_path pointing at a JSON Schema file
    When:  The validator loads each train YAML under trains_glob and
           validates it against the schema
    Then:  Schema violations are hard failures; a missing schema file is a
           hard failure (config error, not opt-out); absent configuration is
           a clean skip.
    """
    cfg = _load_render_metadata_config()

    if not cfg or cfg.get("enabled") is False:
        pytest.skip(
            "train_yaml_render_metadata not configured in .atdd/config.yaml "
            "(opt-in per SPEC-CODER-TRAIN-0003)"
        )

    schema_path_value = cfg.get("schema_path")
    if not schema_path_value:
        pytest.fail(
            "SPEC-CODER-TRAIN-0003 FAIL: train_yaml_render_metadata missing "
            "required key schema_path"
        )

    schema_path = (REPO_ROOT / schema_path_value).resolve()
    if not schema_path.exists():
        pytest.fail(
            f"SPEC-CODER-TRAIN-0003 FAIL: schema file not found\n"
            f"    Configured: {schema_path_value}\n"
            f"    Resolved:   {schema_path}\n"
            f"    Fix:        Create the schema or correct schema_path"
        )

    try:
        schema = _load_schema(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        pytest.fail(
            f"SPEC-CODER-TRAIN-0003 FAIL: schema file unreadable\n"
            f"    Path:   {schema_path}\n"
            f"    Error:  {exc}"
        )
        return  # pragma: no cover — pytest.fail raises

    trains_glob = cfg.get("trains_glob", _DEFAULT_TRAINS_GLOB)
    train_files = _find_train_yamls(trains_glob)

    if not train_files:
        pytest.skip(
            f"No train YAML files matched trains_glob={trains_glob!r}"
        )

    violations: List[str] = []
    for train_file in train_files:
        violations.extend(_validate_train_yaml(train_file, schema))

    if violations:
        pytest.fail(
            f"\n\n{len(violations)} train YAML render metadata violation(s):\n\n"
            + "\n\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Unit tests for the pure helpers (run in every mode, no config required).
# ---------------------------------------------------------------------------


_RENDER_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "train_id": {"type": "string"},
        "template": {"type": "string"},
        "auth_required": {"type": "boolean"},
    },
    "required": ["train_id"],
    "additionalProperties": True,
}


def _write_yaml(path: Path, data: Dict) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_validate_train_yaml_passes_for_compliant_file(tmp_path):
    """A train YAML with valid template + auth_required passes."""
    train = _write_yaml(
        tmp_path / "good.yaml",
        {
            "train_id": "0001-demo",
            "template": "default",
            "auth_required": True,
        },
    )
    violations = _validate_train_yaml(train, _RENDER_SCHEMA)
    assert violations == []


def test_validate_train_yaml_reports_wrong_auth_required_type(tmp_path):
    """A train YAML with auth_required: 'yes' (string, not bool) fails."""
    train = _write_yaml(
        tmp_path / "bad.yaml",
        {
            "train_id": "0001-demo",
            "template": "default",
            "auth_required": "yes",
        },
    )
    violations = _validate_train_yaml(train, _RENDER_SCHEMA)
    assert len(violations) == 1
    assert "auth_required" in violations[0]


def test_validate_train_yaml_reports_missing_required_field(tmp_path):
    """A train YAML missing the required train_id field fails."""
    train = _write_yaml(
        tmp_path / "noid.yaml",
        {"template": "default"},
    )
    violations = _validate_train_yaml(train, _RENDER_SCHEMA)
    assert len(violations) == 1
    assert "train_id" in violations[0]


def test_validate_train_yaml_ignores_empty_file(tmp_path):
    """An empty YAML file yields no violations (no data to validate)."""
    train = tmp_path / "empty.yaml"
    train.write_text("", encoding="utf-8")
    violations = _validate_train_yaml(train, _RENDER_SCHEMA)
    assert violations == []


def test_load_schema_reads_json(tmp_path):
    """_load_schema returns the decoded JSON Schema dict."""
    schema_path = tmp_path / "render.schema.json"
    schema_path.write_text(json.dumps(_RENDER_SCHEMA), encoding="utf-8")
    loaded = _load_schema(schema_path)
    assert loaded["properties"]["template"]["type"] == "string"
    assert loaded["properties"]["auth_required"]["type"] == "boolean"

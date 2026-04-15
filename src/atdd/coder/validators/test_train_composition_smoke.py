"""
SMOKE integration tests for the train_composition validator trio.

Exercises the full config-loading + source-scanning + validation pipeline
against a fixture mini-repo built in ``tmp_path``. The pure unit tests in
``test_frontend_composition_root.py`` / ``test_wagon_trains_export_shape.py``
/ ``test_train_yaml_render_metadata.py`` already cover the helper logic;
this file proves the end-to-end path a real consumer repo would hit.

Each test:
  1. Builds a fake repo under tmp_path with ``.atdd/config.yaml`` and the
     referenced source artifacts.
  2. Monkeypatches ``REPO_ROOT`` on the validator module so
     ``_load_*_config()`` resolves against the fixture.
  3. Calls the validator's private ``_load_*_config()`` + ``_analyze_*()``
     helpers directly (the main ``@pytest.mark.coder`` functions wrap the
     same calls but use ``pytest.fail`` / ``pytest.skip`` which are awkward
     to assert against).

WMBTs covered under SMOKE:
- wmbt:implement-code:D006 — composition root identity
- wmbt:implement-code:D007 — wagon trains.ts export shape
- wmbt:implement-code:D008 — train YAML render metadata

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coder/validators/test_train_composition_smoke.py -v
"""
import json
from pathlib import Path
from typing import Dict

import pytest
import yaml


def _write_atdd_config(root: Path, config: Dict) -> None:
    atdd_dir = root / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    (atdd_dir / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


# ---------------------------------------------------------------------------
# D006 — frontend_composition_root SMOKE
# ---------------------------------------------------------------------------


def test_smoke_d006_passes_for_compliant_fixture(tmp_path, monkeypatch):
    """Compliant fixture: class present with all required methods → no violations."""
    from atdd.coder.validators import test_frontend_composition_root as mod

    runner_src = (
        "export class FrontendTrainRunner {\n"
        "  registerWagon(name: string) {}\n"
        "  runTrain = async (id: string) => {};\n"
        "  resolveTemplate(id: string) { return id; }\n"
        "}\n"
    )
    runner_path = tmp_path / "web" / "src" / "FrontendTrainRunner.ts"
    runner_path.parent.mkdir(parents=True)
    runner_path.write_text(runner_src, encoding="utf-8")

    _write_atdd_config(
        tmp_path,
        {
            "frontend_composition_root": {
                "enabled": True,
                "path": "web/src/FrontendTrainRunner.ts",
                "class_name": "FrontendTrainRunner",
                "required_methods": ["registerWagon", "runTrain", "resolveTemplate"],
            }
        },
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    cfg = mod._load_composition_root_config()
    assert cfg["class_name"] == "FrontendTrainRunner"

    resolved_path = (tmp_path / cfg["path"]).resolve()
    violations = mod._analyze_composition_root(
        resolved_path, cfg["class_name"], cfg["required_methods"]
    )
    assert violations == []


def test_smoke_d006_fails_for_renamed_class_fixture(tmp_path, monkeypatch):
    """Negative fixture: class is renamed → analyzer reports one violation."""
    from atdd.coder.validators import test_frontend_composition_root as mod

    runner_src = (
        "export class OldController {\n"
        "  registerWagon() {}\n"
        "  runTrain() {}\n"
        "  resolveTemplate() { return ''; }\n"
        "}\n"
    )
    runner_path = tmp_path / "web" / "src" / "FrontendTrainRunner.ts"
    runner_path.parent.mkdir(parents=True)
    runner_path.write_text(runner_src, encoding="utf-8")

    _write_atdd_config(
        tmp_path,
        {
            "frontend_composition_root": {
                "enabled": True,
                "path": "web/src/FrontendTrainRunner.ts",
                "class_name": "FrontendTrainRunner",
                "required_methods": ["registerWagon"],
            }
        },
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    cfg = mod._load_composition_root_config()
    resolved_path = (tmp_path / cfg["path"]).resolve()
    violations = mod._analyze_composition_root(
        resolved_path, cfg["class_name"], cfg["required_methods"]
    )
    assert len(violations) == 1
    assert "class not found" in violations[0]


# ---------------------------------------------------------------------------
# D007 — wagon_trains_export_shape SMOKE
# ---------------------------------------------------------------------------


def test_smoke_d007_passes_for_compliant_wagon_tree(tmp_path, monkeypatch):
    """Every wagon has trains.ts with all required exports."""
    from atdd.coder.validators import test_wagon_trains_export_shape as mod

    wagons_root = tmp_path / "web" / "src" / "wagons"
    for name in ("home", "profile"):
        wagon_dir = wagons_root / name
        wagon_dir.mkdir(parents=True)
        (wagon_dir / "trains.ts").write_text(
            f"export function runTrainStep(cargo: Cargo) {{ return cargo; }}\n"
            f"export const {name.capitalize()}TrainView = () => null;\n"
            f"export const HomeTrainView = () => null;\n",
            encoding="utf-8",
        )

    _write_atdd_config(
        tmp_path,
        {
            "wagon_trains_export_shape": {
                "enabled": True,
                "wagon_glob": "web/src/wagons/*",
                "required_exports": ["runTrainStep", "HomeTrainView"],
            }
        },
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    cfg = mod._load_export_shape_config()
    assert cfg["wagon_glob"] == "web/src/wagons/*"

    wagon_dirs = sorted(p for p in tmp_path.glob(cfg["wagon_glob"]) if p.is_dir())
    assert len(wagon_dirs) == 2

    violations = []
    for wagon_dir in wagon_dirs:
        violations.extend(mod._analyze_wagon_trains(wagon_dir, cfg["required_exports"]))
    assert violations == []


def test_smoke_d007_fails_when_one_wagon_is_missing_trains_ts(tmp_path, monkeypatch):
    """A wagon directory without trains.ts is reported."""
    from atdd.coder.validators import test_wagon_trains_export_shape as mod

    wagons_root = tmp_path / "web" / "src" / "wagons"
    (wagons_root / "home").mkdir(parents=True)
    (wagons_root / "home" / "trains.ts").write_text(
        "export function runTrainStep(cargo: Cargo) { return cargo; }\n"
        "export const HomeTrainView = () => null;\n",
        encoding="utf-8",
    )
    (wagons_root / "profile").mkdir(parents=True)  # no trains.ts

    _write_atdd_config(
        tmp_path,
        {
            "wagon_trains_export_shape": {
                "enabled": True,
                "wagon_glob": "web/src/wagons/*",
                "required_exports": ["runTrainStep", "HomeTrainView"],
            }
        },
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    cfg = mod._load_export_shape_config()
    wagon_dirs = sorted(p for p in tmp_path.glob(cfg["wagon_glob"]) if p.is_dir())

    violations = []
    for wagon_dir in wagon_dirs:
        violations.extend(mod._analyze_wagon_trains(wagon_dir, cfg["required_exports"]))

    assert len(violations) == 1
    assert "missing trains.ts" in violations[0]
    assert "profile" in violations[0]


# ---------------------------------------------------------------------------
# D008 — train_yaml_render_metadata SMOKE
# ---------------------------------------------------------------------------


_SMOKE_SCHEMA = {
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


def test_smoke_d008_passes_for_valid_train_yaml_tree(tmp_path, monkeypatch):
    """Every train YAML conforms to the configured schema."""
    from atdd.coder.validators import test_train_yaml_render_metadata as mod

    schema_path = tmp_path / "contracts" / "train-render-metadata.schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(json.dumps(_SMOKE_SCHEMA), encoding="utf-8")

    trains_dir = tmp_path / "plan" / "_trains"
    trains_dir.mkdir(parents=True)
    (trains_dir / "0001-demo.yaml").write_text(
        yaml.safe_dump({"train_id": "0001-demo", "template": "default", "auth_required": True}),
        encoding="utf-8",
    )
    (trains_dir / "0002-other.yaml").write_text(
        yaml.safe_dump({"train_id": "0002-other", "template": "full-screen", "auth_required": False}),
        encoding="utf-8",
    )

    _write_atdd_config(
        tmp_path,
        {
            "train_yaml_render_metadata": {
                "enabled": True,
                "schema_path": "contracts/train-render-metadata.schema.json",
                "trains_glob": "plan/_trains/**/*.yaml",
            }
        },
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    cfg = mod._load_render_metadata_config()
    resolved_schema_path = (tmp_path / cfg["schema_path"]).resolve()
    assert resolved_schema_path.exists()

    schema = mod._load_schema(resolved_schema_path)
    train_files = mod._find_train_yamls(cfg["trains_glob"])
    assert len(train_files) == 2

    violations = []
    for train_file in train_files:
        violations.extend(mod._validate_train_yaml(train_file, schema))
    assert violations == []


def test_smoke_d008_fails_for_wrong_auth_required_type(tmp_path, monkeypatch):
    """A train YAML with auth_required as a string is reported."""
    from atdd.coder.validators import test_train_yaml_render_metadata as mod

    schema_path = tmp_path / "contracts" / "train-render-metadata.schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(json.dumps(_SMOKE_SCHEMA), encoding="utf-8")

    trains_dir = tmp_path / "plan" / "_trains"
    trains_dir.mkdir(parents=True)
    (trains_dir / "0001-bad.yaml").write_text(
        yaml.safe_dump({"train_id": "0001-bad", "template": "default", "auth_required": "yes"}),
        encoding="utf-8",
    )

    _write_atdd_config(
        tmp_path,
        {
            "train_yaml_render_metadata": {
                "enabled": True,
                "schema_path": "contracts/train-render-metadata.schema.json",
                "trains_glob": "plan/_trains/**/*.yaml",
            }
        },
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    cfg = mod._load_render_metadata_config()
    schema = mod._load_schema((tmp_path / cfg["schema_path"]).resolve())
    train_files = mod._find_train_yamls(cfg["trains_glob"])

    violations = []
    for train_file in train_files:
        violations.extend(mod._validate_train_yaml(train_file, schema))
    assert len(violations) == 1
    assert "auth_required" in violations[0]

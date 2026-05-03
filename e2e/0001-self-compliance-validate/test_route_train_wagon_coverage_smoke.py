# URN: test:train:0001-self-compliance-validate:E2E-001-route-train-wagon-coverage-smoke
# Train: train:0001-self-compliance-validate
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end smoke for the route→train→wagon validator (#333) — real
#          tmp consumer repo, real plan YAML files, real analyzer pipeline.

"""
Smoke for src/atdd/coder/validators/route_train_wagon_analyzer.py.

Stands up a tmp consumer-repo layout (`web/src/`, `plan/_trains.yaml`,
`plan/_wagons.yaml`, `.atdd/config.yaml`) and runs the validator against
it without mocking any component. Three scenarios cover the three
rule_ids declared in Decision #5b:

* ghost_train       → BOUNDARIES-ROUTE-COVERAGE-001 (sev 3)
* unregistered_wagon → BOUNDARIES-ROUTE-COVERAGE-002 (sev 3)
* dynamic_unknown   → BOUNDARIES-ROUTE-COVERAGE-003 (sev 1)

Plus a clean baseline scenario that asserts a fully-resolved chain emits
zero Violations.

The smoke imports no mocking library (enforced by
`src/atdd/tester/validators/test_train_route_smoke_coverage.py::test_train_route_smoke_no_mocks`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coder.validators.route_train_wagon_analyzer import (
    RULE_DYNAMIC_TRAIN_ID,
    RULE_UNREGISTERED_TRAIN,
    RULE_UNREGISTERED_WAGON,
    SEVERITY_ADVISORY,
    SEVERITY_ARCHITECTURAL,
    RouteTrainWagonAnalyzer,
)


# ---------------------------------------------------------------------------
# Tmp repo factory
# ---------------------------------------------------------------------------
def _materialize_consumer_repo(
    root: Path,
    *,
    router_body: str,
    trains_yaml: str,
    wagons_yaml: str,
) -> Path:
    """Create a minimal consumer-repo layout under *root* and return its path.

    Layout:
      <root>/web/src/app/router.tsx
      <root>/plan/_trains.yaml
      <root>/plan/_wagons.yaml
    """
    web_dir = root / "web" / "src" / "app"
    web_dir.mkdir(parents=True)
    router_file = web_dir / "router.tsx"
    router_file.write_text(router_body, encoding="utf-8")

    plan_dir = root / "plan"
    plan_dir.mkdir(parents=True)
    (plan_dir / "_trains.yaml").write_text(trains_yaml, encoding="utf-8")
    (plan_dir / "_wagons.yaml").write_text(wagons_yaml, encoding="utf-8")

    return router_file


def _good_trains_yaml() -> str:
    return (
        "trains:\n"
        "  smoke-theme:\n"
        "    nominal:\n"
        "      - train_id: \"smoke-train\"\n"
        "        wagons:\n"
        "          - smoke-wagon\n"
    )


def _good_wagons_yaml() -> str:
    return (
        "wagons:\n"
        "  - wagon: smoke-wagon\n"
        "    description: \"Smoke fixture wagon\"\n"
    )


# ===========================================================================
# Smoke scenarios
# ===========================================================================

class TestRouteTrainWagonCoverageSmoke:
    """Real tmp consumer repo + real RouteTrainWagonAnalyzer."""

    def test_smoke_ghost_train_emits_unregistered_violation(self, tmp_path: Path):
        """A router whose `<TrainView trainId="..." />` references an unknown
        train id surfaces BOUNDARIES-ROUTE-COVERAGE-001 with severity 3.
        """
        router = _materialize_consumer_repo(
            tmp_path,
            router_body=(
                "import { TrainView } from \"@/runtime/TrainView\";\n"
                "export const Router = () => (\n"
                "  <TrainView trainId=\"ghost-train\" />\n"
                ");\n"
            ),
            trains_yaml=_good_trains_yaml(),
            wagons_yaml=_good_wagons_yaml(),
        )

        analyzer = RouteTrainWagonAnalyzer(
            trains_file=tmp_path / "plan" / "_trains.yaml",
            wagons_file=tmp_path / "plan" / "_wagons.yaml",
        )
        violations = analyzer.analyze(router, tmp_path)

        matches = [v for v in violations if v.rule_id == RULE_UNREGISTERED_TRAIN]
        assert matches, f"expected {RULE_UNREGISTERED_TRAIN}; got {violations!r}"
        v = matches[0]
        assert v.severity == SEVERITY_ARCHITECTURAL
        assert "ghost-train" in v.detail
        assert v.location.endswith("router.tsx:3"), (
            f"expected line 3, got location {v.location!r}"
        )

    def test_smoke_train_with_unregistered_wagon_emits_violation(self, tmp_path: Path):
        """A registered train whose `wagons:` list names an unknown wagon
        surfaces BOUNDARIES-ROUTE-COVERAGE-002 with severity 3 and the
        wagon name in the detail.
        """
        # Train is registered, but it lists `phantom-wagon` which the
        # wagons.yaml does not register.
        bad_trains_yaml = (
            "trains:\n"
            "  smoke-theme:\n"
            "    nominal:\n"
            "      - train_id: \"smoke-train\"\n"
            "        wagons:\n"
            "          - smoke-wagon\n"
            "          - phantom-wagon\n"
        )
        router = _materialize_consumer_repo(
            tmp_path,
            router_body=(
                "import { TrainView } from \"@/runtime/TrainView\";\n"
                "export const Router = () => <TrainView trainId=\"smoke-train\" />;\n"
            ),
            trains_yaml=bad_trains_yaml,
            wagons_yaml=_good_wagons_yaml(),
        )

        analyzer = RouteTrainWagonAnalyzer(
            trains_file=tmp_path / "plan" / "_trains.yaml",
            wagons_file=tmp_path / "plan" / "_wagons.yaml",
        )
        violations = analyzer.analyze(router, tmp_path)

        matches = [v for v in violations if v.rule_id == RULE_UNREGISTERED_WAGON]
        assert matches, f"expected {RULE_UNREGISTERED_WAGON}; got {violations!r}"
        v = matches[0]
        assert v.severity == SEVERITY_ARCHITECTURAL
        assert "phantom-wagon" in v.detail

    def test_smoke_dynamic_train_id_emits_advisory(self, tmp_path: Path):
        """A `<TrainView trainId={props.trainId} />` is not statically
        resolvable and surfaces BOUNDARIES-ROUTE-COVERAGE-003 with
        severity 1, never a hard failure (Decision #4).
        """
        router = _materialize_consumer_repo(
            tmp_path,
            router_body=(
                "import { TrainView } from \"@/runtime/TrainView\";\n"
                "interface RP { trainId: string; }\n"
                "export const Router = (props: RP) => (\n"
                "  <TrainView trainId={props.trainId} />\n"
                ");\n"
            ),
            trains_yaml=_good_trains_yaml(),
            wagons_yaml=_good_wagons_yaml(),
        )

        analyzer = RouteTrainWagonAnalyzer(
            trains_file=tmp_path / "plan" / "_trains.yaml",
            wagons_file=tmp_path / "plan" / "_wagons.yaml",
        )
        violations = analyzer.analyze(router, tmp_path)

        matches = [v for v in violations if v.rule_id == RULE_DYNAMIC_TRAIN_ID]
        assert matches, f"expected {RULE_DYNAMIC_TRAIN_ID}; got {violations!r}"
        assert matches[0].severity == SEVERITY_ADVISORY
        # No hard-failure rules should accompany an UNKNOWN binding.
        hard = [v for v in violations if v.rule_id != RULE_DYNAMIC_TRAIN_ID]
        assert not hard, (
            f"dynamic trainId must not surface hard-fail rules; got {hard!r}"
        )

    def test_smoke_resolved_chain_emits_no_violations(self, tmp_path: Path):
        """A fully-resolved route → train → wagon chain produces zero Violations.

        Negative scenario: validator must not false-positive when the plan
        and the router are consistent.
        """
        router = _materialize_consumer_repo(
            tmp_path,
            router_body=(
                "import { TrainView } from \"@/runtime/TrainView\";\n"
                "export const Router = () => <TrainView trainId=\"smoke-train\" />;\n"
            ),
            trains_yaml=_good_trains_yaml(),
            wagons_yaml=_good_wagons_yaml(),
        )

        analyzer = RouteTrainWagonAnalyzer(
            trains_file=tmp_path / "plan" / "_trains.yaml",
            wagons_file=tmp_path / "plan" / "_wagons.yaml",
        )
        violations = analyzer.analyze(router, tmp_path)
        assert violations == [], (
            f"expected clean chain to emit zero Violations; got {violations!r}"
        )

    def test_smoke_const_resolution_passes(self, tmp_path: Path):
        """Same-file `const X = "id"` declaration resolves an identifier
        binding so `<TrainView trainId={X} />` is treated as registered.
        """
        router = _materialize_consumer_repo(
            tmp_path,
            router_body=(
                "import { TrainView } from \"@/runtime/TrainView\";\n"
                "const SMOKE_TRAIN_ID: string = \"smoke-train\";\n"
                "export const Router = () => (\n"
                "  <TrainView trainId={SMOKE_TRAIN_ID} />\n"
                ");\n"
            ),
            trains_yaml=_good_trains_yaml(),
            wagons_yaml=_good_wagons_yaml(),
        )

        analyzer = RouteTrainWagonAnalyzer(
            trains_file=tmp_path / "plan" / "_trains.yaml",
            wagons_file=tmp_path / "plan" / "_wagons.yaml",
        )
        violations = analyzer.analyze(router, tmp_path)
        assert violations == [], (
            f"const-declared trainId must resolve; got {violations!r}"
        )

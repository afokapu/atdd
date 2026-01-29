#!/usr/bin/env python3
"""
Presentation Convention Validator

Validates presentation layer compliance per presentation.convention.yaml:
- FastAPI controller structure
- Pydantic models aligned with contracts
- Composition integration (CLI/HTTP modes)
- GREEN simplifications with TODO markers

Usage:
    python3 atdd/coder/test_presentation_convention.py
"""
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import re

# Project root constant (pytest pythonpath handles imports)
REPO_ROOT = Path(__file__).resolve().parents[4]


class PresentationValidator:
    """Validates presentation layer against convention."""

    def __init__(self, python_root: Path):
        self.python_root = python_root
        self.violations = []

    def validate_all_wagons(self) -> List[str]:
        """Validate all wagons in python/ directory."""
        print("=" * 70)
        print("PRESENTATION CONVENTION VALIDATION")
        print("=" * 70)
        print()

        wagons = [d for d in self.python_root.iterdir() if d.is_dir() and not d.name.startswith('_')]

        for wagon_dir in sorted(wagons):
            if wagon_dir.name in ['shared', 'contracts', 'tools']:
                continue

            self._validate_wagon(wagon_dir)

        return self.violations

    def _validate_wagon(self, wagon_dir: Path):
        """Validate a single wagon's presentation layer."""
        features = [d for d in wagon_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]

        for feature_dir in features:
            self._validate_feature(wagon_dir.name, feature_dir)

    def _validate_feature(self, wagon_name: str, feature_dir: Path):
        """Validate a single feature's presentation layer."""
        presentation_dir = feature_dir / "src" / "presentation"

        if not presentation_dir.exists():
            # No presentation layer is valid (domain-only features)
            return

        # Find controller files
        controllers_dir = presentation_dir / "controllers"
        if not controllers_dir.exists():
            return

        for controller_file in controllers_dir.glob("*.py"):
            if controller_file.name == "__init__.py":
                continue

            self._validate_controller(wagon_name, feature_dir.name, controller_file)

        # Validate composition.py integration
        composition_file = feature_dir / "composition.py"
        if composition_file.exists():
            self._validate_composition_integration(wagon_name, feature_dir.name, composition_file)

    def _validate_controller(self, wagon: str, feature: str, controller_file: Path):
        """Validate a FastAPI controller file."""
        content = controller_file.read_text()

        # Check for FastAPI usage
        if "from fastapi import" not in content and "import fastapi" not in content:
            # Not a FastAPI controller
            return

        print(f"Validating FastAPI controller: {wagon}/{feature}/{controller_file.name}")

        # Check URN marker
        urn_pattern = r"# urn: component:[a-z-]+:[a-z-]+\.[A-Za-z]+\.backend\.presentation"
        if not re.search(urn_pattern, content):
            self.violations.append(
                f"❌ {wagon}/{feature}: Missing URN marker in {controller_file.name}"
            )

        # Check Pydantic response model
        if "from pydantic import BaseModel" not in content and "from pydantic import" not in content:
            self.violations.append(
                f"❌ {wagon}/{feature}: FastAPI controller missing Pydantic imports in {controller_file.name}"
            )

        # Check for response model with artifact_name field
        if "artifact_name" not in content:
            self.violations.append(
                f"⚠️  {wagon}/{feature}: Response model should have artifact_name field in {controller_file.name}"
            )

        # Check for endpoint decorators
        if "@app.get" not in content and "@app.post" not in content and "@app.put" not in content:
            self.violations.append(
                f"❌ {wagon}/{feature}: No FastAPI endpoint decorators found in {controller_file.name}"
            )

        # Check for summary and tags in decorators
        has_endpoints = bool(re.search(r"@app\.(get|post|put|delete)", content))
        if has_endpoints:
            if "summary=" not in content:
                self.violations.append(
                    f"⚠️  {wagon}/{feature}: Endpoints should have summary parameter in {controller_file.name}"
                )
            if "tags=" not in content:
                self.violations.append(
                    f"⚠️  {wagon}/{feature}: Endpoints should have tags parameter in {controller_file.name}"
                )

        # Check for GREEN simplifications with TODO markers
        if re.search(r"^[^#]*global\s+\w+", content, re.MULTILINE):
            # Has global state
            if "TODO(REFACTOR)" not in content:
                self.violations.append(
                    f"⚠️  {wagon}/{feature}: Global state should have TODO(REFACTOR) marker in {controller_file.name}"
                )

        # Check Field usage for schema documentation
        if "BaseModel" in content and "Field(" not in content:
            self.violations.append(
                f"⚠️  {wagon}/{feature}: Pydantic models should use Field() for descriptions in {controller_file.name}"
            )

        print(f"  ✓ Controller structure validated")

    def _validate_composition_integration(self, wagon: str, feature: str, composition_file: Path):
        """Validate composition.py supports CLI and HTTP modes."""
        content = composition_file.read_text()

        # Check for mode parameter
        if 'mode' in content and ('cli' in content or 'http' in content):
            print(f"  ✓ Composition supports dual CLI/HTTP mode")

            # Check for uvicorn
            if 'http' in content and 'uvicorn' not in content:
                self.violations.append(
                    f"⚠️  {wagon}/{feature}: HTTP mode should use uvicorn.run() in composition.py"
                )

            # Check for controller import in HTTP mode
            if 'http' in content and 'from src.presentation.controllers' not in content:
                self.violations.append(
                    f"⚠️  {wagon}/{feature}: HTTP mode should import controller in composition.py"
                )

    def print_summary(self):
        """Print validation summary."""
        print()
        print("=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)

        if not self.violations:
            print("✅ All presentation layers comply with convention!")
            return 0
        else:
            print(f"Found {len(self.violations)} issue(s):\n")
            for violation in self.violations:
                print(f"  {violation}")
            print()
            return 1


    def validate_game_server_registration(self):
        """Validate python/game.py includes all wagons with presentation."""
        game_file = self.python_root / "game.py"

        if not game_file.exists():
            self.violations.append("❌ python/game.py not found - unified game server missing")
            return

        print(f"\nValidating unified game server: python/game.py")

        content = game_file.read_text()

        # Find all wagons with FastAPI controllers
        wagons_with_controllers = {}
        for wagon_dir in self.python_root.iterdir():
            if not wagon_dir.is_dir() or wagon_dir.name.startswith('_'):
                continue
            if wagon_dir.name in ['shared', 'contracts', 'tools', 'data']:
                continue

            for feature_dir in wagon_dir.iterdir():
                if not feature_dir.is_dir():
                    continue

                controller_dir = feature_dir / "src" / "presentation" / "controllers"
                if controller_dir.exists():
                    for controller_file in controller_dir.glob("*_controller.py"):
                        if "fastapi" in controller_file.read_text().lower():
                            wagons_with_controllers[f"{wagon_dir.name}/{feature_dir.name}"] = controller_file

        # Check if each controller is registered in game.py
        for wagon_feature, controller_file in wagons_with_controllers.items():
            wagon, feature = wagon_feature.split('/')

            # Check for import statement
            import_pattern = f"from {wagon}.{feature}.src.presentation.controllers"
            if import_pattern not in content:
                self.violations.append(
                    f"❌ game.py missing import for {wagon}/{feature} controller"
                )

            # Check for include_router
            if "include_router" in content and wagon not in content.lower():
                self.violations.append(
                    f"⚠️  game.py may not be registering {wagon}/{feature} routes"
                )

        if not self.violations:
            print(f"  ✓ All {len(wagons_with_controllers)} wagons registered in game.py")


def main():
    """Run presentation convention validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate presentation layer convention")
    parser.add_argument("--check-game-server", action="store_true",
                       help="Validate python/game.py is up to date")
    args = parser.parse_args()

    python_root = REPO_ROOT / "python"

    if not python_root.exists():
        print(f"❌ Python directory not found: {python_root}")
        sys.exit(1)

    validator = PresentationValidator(python_root)

    if args.check_game_server:
        validator.validate_game_server_registration()
    else:
        validator.validate_all_wagons()
        validator.validate_game_server_registration()

    exit_code = validator.print_summary()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

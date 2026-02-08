"""
URN Resolution Engine
=====================
Provides family-specific resolvers for mapping URNs to filesystem artifacts.

Each URN family has a dedicated resolver that:
- Validates URN format
- Resolves URN to artifact path(s)
- Reports resolution determinism
- Finds all URN declarations of that family

Architecture:
- URNResolution: Result dataclass with resolved paths and metadata
- URNResolver: Protocol for family-specific resolvers
- ResolverRegistry: Coordinates all resolvers
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple
from abc import ABC, abstractmethod

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.urn import URNBuilder


@dataclass
class URNDeclaration:
    """
    A URN declaration found in an artifact file.

    Represents where a URN is declared (source) vs referenced (target).
    """
    urn: str
    family: str
    source_path: Path
    line_number: Optional[int] = None
    context: Optional[str] = None


@dataclass
class URNResolution:
    """
    Result of resolving a URN to filesystem artifact(s).

    Attributes:
        urn: The URN being resolved
        family: URN family (wagon, feature, wmbt, etc.)
        resolved_paths: List of paths the URN resolves to
        is_deterministic: True if URN resolves to exactly one artifact
        error: Error message if resolution failed
        declaration: Source declaration of this URN
    """
    urn: str
    family: str
    resolved_paths: List[Path] = field(default_factory=list)
    is_deterministic: bool = True
    error: Optional[str] = None
    declaration: Optional[URNDeclaration] = None

    @property
    def is_resolved(self) -> bool:
        """True if URN resolved to at least one path."""
        return len(self.resolved_paths) > 0 and self.error is None

    @property
    def is_broken(self) -> bool:
        """True if URN could not be resolved."""
        return len(self.resolved_paths) == 0 or self.error is not None


class URNResolver(Protocol):
    """Protocol for family-specific URN resolvers."""

    @property
    def family(self) -> str:
        """Return the URN family this resolver handles."""
        ...

    def can_resolve(self, urn: str) -> bool:
        """Check if this resolver can handle the given URN."""
        ...

    def resolve(self, urn: str) -> URNResolution:
        """Resolve a URN to filesystem artifact(s)."""
        ...

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all URN declarations of this family in the codebase."""
        ...


class BaseResolver(ABC):
    """Base class for URN resolvers with common functionality."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or find_repo_root()
        self.plan_dir = self.repo_root / "plan"
        self.contracts_dir = self.repo_root / "contracts"
        self.telemetry_dir = self.repo_root / "telemetry"

    @property
    @abstractmethod
    def family(self) -> str:
        """Return the URN family this resolver handles."""
        pass

    def can_resolve(self, urn: str) -> bool:
        """Check if this resolver can handle the given URN."""
        return urn.startswith(f"{self.family}:")

    @abstractmethod
    def resolve(self, urn: str) -> URNResolution:
        """Resolve a URN to filesystem artifact(s)."""
        pass

    @abstractmethod
    def find_declarations(self) -> List[URNDeclaration]:
        """Find all URN declarations of this family."""
        pass

    # Directories pruned before recursion in os.walk
    _SKIP_DIRS = {
        ".git", "__pycache__", "node_modules", ".dart_tool",
        "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
        ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    }

    def _walk_files(self, root: Path, extensions: set[str]):
        """
        Walk directory tree yielding files matching extensions.

        Prunes vendored/build directories *before* recursing so os.walk
        never enters node_modules, .dart_tool, etc.
        """
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune in-place so os.walk skips these subtrees entirely
            dirnames[:] = [d for d in dirnames if d not in self._SKIP_DIRS]
            for fname in filenames:
                if any(fname.endswith(ext) for ext in extensions):
                    yield Path(dirpath) / fname

    def _validate_urn_format(self, urn: str) -> Optional[str]:
        """Validate URN format against PATTERNS. Returns error message or None."""
        pattern = URNBuilder.PATTERNS.get(self.family)
        if not pattern:
            return f"No pattern defined for family '{self.family}'"
        if not re.match(pattern, urn):
            return f"URN '{urn}' does not match pattern {pattern}"
        return None


class WagonResolver(BaseResolver):
    """
    Resolver for wagon: URNs.

    Resolution: wagon:{slug} -> plan/{slug}/_{slug}.yaml
    """

    @property
    def family(self) -> str:
        return "wagon"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a wagon URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        slug = urn.replace("wagon:", "")
        wagon_dir = self.plan_dir / slug.replace("-", "_")
        manifest_path = wagon_dir / f"_{slug.replace('-', '_')}.yaml"

        paths = []
        if manifest_path.exists():
            paths.append(manifest_path)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Wagon manifest not found: {manifest_path}",
        )

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all wagon URN declarations in manifests."""
        declarations = []
        if not self.plan_dir.exists():
            return declarations

        for manifest in self.plan_dir.rglob("_*.yaml"):
            try:
                import yaml

                with open(manifest, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    wagon_slug = data.get("wagon")
                    if wagon_slug:
                        urn = f"wagon:{wagon_slug}"
                        declarations.append(
                            URNDeclaration(
                                urn=urn,
                                family=self.family,
                                source_path=manifest,
                                context="wagon manifest",
                            )
                        )
            except Exception:
                continue

        return declarations


class FeatureResolver(BaseResolver):
    """
    Resolver for feature: URNs.

    Resolution: feature:{wagon}:{feature} -> plan/{wagon}/features/{feature}.yaml
    """

    @property
    def family(self) -> str:
        return "feature"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a feature URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        parts = urn.replace("feature:", "").split(":")
        if len(parts) != 2:
            return URNResolution(
                urn=urn, family=self.family, error="Invalid feature URN format"
            )

        wagon_slug, feature_slug = parts
        wagon_dir = self.plan_dir / wagon_slug.replace("-", "_")
        feature_path = wagon_dir / "features" / f"{feature_slug.replace('-', '_')}.yaml"

        paths = []
        if feature_path.exists():
            paths.append(feature_path)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Feature file not found: {feature_path}",
        )

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all feature URN declarations in feature files."""
        declarations = []
        if not self.plan_dir.exists():
            return declarations

        for feature_file in self.plan_dir.rglob("features/*.yaml"):
            try:
                import yaml

                with open(feature_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    feature_urn = data.get("urn")
                    if feature_urn and feature_urn.startswith("feature:"):
                        declarations.append(
                            URNDeclaration(
                                urn=feature_urn,
                                family=self.family,
                                source_path=feature_file,
                                context="feature file",
                            )
                        )
            except Exception:
                continue

        return declarations


class WMBTResolver(BaseResolver):
    """
    Resolver for wmbt: URNs.

    Resolution: wmbt:{wagon}:{STEP}{NNN} -> plan/{wagon}/{STEP}{NNN}.yaml
    """

    @property
    def family(self) -> str:
        return "wmbt"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a wmbt URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        parts = urn.replace("wmbt:", "").split(":")
        if len(parts) != 2:
            return URNResolution(
                urn=urn, family=self.family, error="Invalid wmbt URN format"
            )

        wagon_slug, step_id = parts
        wagon_dir = self.plan_dir / wagon_slug.replace("-", "_")
        wmbt_path = wagon_dir / f"{step_id}.yaml"

        paths = []
        if wmbt_path.exists():
            paths.append(wmbt_path)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"WMBT file not found: {wmbt_path}",
        )

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all WMBT URN declarations in WMBT files."""
        declarations = []
        if not self.plan_dir.exists():
            return declarations

        wmbt_pattern = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")
        for wagon_dir in self.plan_dir.iterdir():
            if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
                continue

            for wmbt_file in wagon_dir.glob("*.yaml"):
                if not wmbt_pattern.match(wmbt_file.name):
                    continue

                try:
                    import yaml

                    with open(wmbt_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        wmbt_urn = data.get("urn")
                        if wmbt_urn and wmbt_urn.startswith("wmbt:"):
                            declarations.append(
                                URNDeclaration(
                                    urn=wmbt_urn,
                                    family=self.family,
                                    source_path=wmbt_file,
                                    context="WMBT file",
                                )
                            )
                except Exception:
                    continue

        return declarations


class AcceptanceResolver(BaseResolver):
    """
    Resolver for acc: URNs.

    Resolution: acc:{wagon}:{wmbt_id}-{harness}-{seq} -> WMBT YAML acceptance blocks
    """

    @property
    def family(self) -> str:
        return "acc"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not an acc URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        parsed = URNBuilder.parse_urn(urn)
        wagon_slug = parsed.get("wagon_id")
        wmbt_id = parsed.get("wmbt_id")

        if not wagon_slug or not wmbt_id:
            return URNResolution(
                urn=urn, family=self.family, error="Could not parse acceptance URN"
            )

        wagon_dir = self.plan_dir / wagon_slug.replace("-", "_")
        wmbt_path = wagon_dir / f"{wmbt_id}.yaml"

        paths = []
        if wmbt_path.exists():
            paths.append(wmbt_path)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"WMBT file for acceptance not found: {wmbt_path}",
        )

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all acceptance URN declarations in WMBT files."""
        declarations = []
        if not self.plan_dir.exists():
            return declarations

        wmbt_pattern = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")
        for wagon_dir in self.plan_dir.iterdir():
            if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
                continue

            for wmbt_file in wagon_dir.glob("*.yaml"):
                if not wmbt_pattern.match(wmbt_file.name):
                    continue

                try:
                    import yaml

                    with open(wmbt_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        for acc in data.get("acceptances", []):
                            acc_urn = acc.get("identity", {}).get("urn")
                            if acc_urn and acc_urn.startswith("acc:"):
                                declarations.append(
                                    URNDeclaration(
                                        urn=acc_urn,
                                        family=self.family,
                                        source_path=wmbt_file,
                                        context="acceptance block",
                                    )
                                )
                except Exception:
                    continue

        return declarations


class ContractResolver(BaseResolver):
    """
    Resolver for contract: URNs.

    Resolution: contract:{domain}:{resource} -> contracts/{domain}/{resource}.schema.json
    """

    @property
    def family(self) -> str:
        return "contract"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a contract URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        contract_id = urn.replace("contract:", "")
        paths = self._find_contract_files(contract_id)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Contract schema not found for: {urn}",
        )

    def _find_contract_files(self, contract_id: str) -> List[Path]:
        """Find contract files matching the ID using multiple strategies."""
        paths = []
        if not self.contracts_dir.exists():
            return paths

        for contract_file in self.contracts_dir.rglob("*.schema.json"):
            try:
                import json

                with open(contract_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                file_id = data.get("$id", "")

                # Skip urn:jel:* IDs (JEL package headers, not ATDD contracts)
                if file_id.startswith("urn:jel:"):
                    continue

                # Strategy 1: Exact match
                if file_id == contract_id:
                    paths.append(contract_file)
                    continue

                # Strategy 2: Normalized match (colon vs dot)
                normalized_file_id = file_id.replace(".", ":")
                normalized_contract_id = contract_id.replace(".", ":")
                if normalized_file_id == normalized_contract_id:
                    paths.append(contract_file)
                    continue

                # Strategy 3: Path-based match
                contract_path = str(
                    contract_file.relative_to(self.contracts_dir)
                ).replace(".schema.json", "")
                urn_path = contract_id.replace(":", "/")
                if contract_path == urn_path:
                    paths.append(contract_file)
                    continue

            except Exception:
                continue

        return paths

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all contract URN declarations in contract schema files."""
        declarations = []
        if not self.contracts_dir.exists():
            return declarations

        import json

        for contract_file in self.contracts_dir.rglob("*.schema.json"):
            try:
                with open(contract_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                contract_id = data.get("$id")
                # Skip urn:jel:* IDs (JEL package headers, not ATDD contracts)
                if contract_id and contract_id.startswith("urn:jel:"):
                    continue
                if contract_id:
                    urn = f"contract:{contract_id}"
                    declarations.append(
                        URNDeclaration(
                            urn=urn,
                            family=self.family,
                            source_path=contract_file,
                            context="contract schema",
                        )
                    )
            except Exception:
                continue

        return declarations


class TelemetryResolver(BaseResolver):
    """
    Resolver for telemetry: URNs.

    Resolution: telemetry:{wagon}.{signal} -> telemetry/{wagon}/{signal}.yaml
    """

    @property
    def family(self) -> str:
        return "telemetry"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a telemetry URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        telemetry_id = urn.replace("telemetry:", "")
        paths = self._find_telemetry_files(telemetry_id)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Telemetry file not found for: {urn}",
        )

    def _find_telemetry_files(self, telemetry_id: str) -> List[Path]:
        """Find telemetry files matching the ID."""
        paths = []
        if not self.telemetry_dir.exists():
            return paths

        for telemetry_file in self.telemetry_dir.rglob("*.yaml"):
            try:
                import yaml

                with open(telemetry_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                file_id = data.get("$id") or data.get("id", "")

                # Match against telemetry ID
                if file_id == telemetry_id:
                    paths.append(telemetry_file)
                elif file_id == f"telemetry:{telemetry_id}":
                    paths.append(telemetry_file)

            except Exception:
                continue

        # Also check JSON files
        for telemetry_file in self.telemetry_dir.rglob("*.json"):
            try:
                import json

                with open(telemetry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                file_id = data.get("$id") or data.get("id", "")

                if file_id == telemetry_id or file_id == f"telemetry:{telemetry_id}":
                    paths.append(telemetry_file)

            except Exception:
                continue

        return paths

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all telemetry URN declarations."""
        declarations = []
        if not self.telemetry_dir.exists():
            return declarations

        import yaml
        import json

        for telemetry_file in self.telemetry_dir.rglob("*.yaml"):
            try:
                with open(telemetry_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                telemetry_id = data.get("$id") or data.get("id")
                if telemetry_id:
                    urn = (
                        telemetry_id
                        if telemetry_id.startswith("telemetry:")
                        else f"telemetry:{telemetry_id}"
                    )
                    declarations.append(
                        URNDeclaration(
                            urn=urn,
                            family=self.family,
                            source_path=telemetry_file,
                            context="telemetry definition",
                        )
                    )
            except Exception:
                continue

        for telemetry_file in self.telemetry_dir.rglob("*.json"):
            try:
                with open(telemetry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                telemetry_id = data.get("$id") or data.get("id")
                if telemetry_id:
                    urn = (
                        telemetry_id
                        if telemetry_id.startswith("telemetry:")
                        else f"telemetry:{telemetry_id}"
                    )
                    declarations.append(
                        URNDeclaration(
                            urn=urn,
                            family=self.family,
                            source_path=telemetry_file,
                            context="telemetry definition",
                        )
                    )
            except Exception:
                continue

        return declarations


class TrainResolver(BaseResolver):
    """
    Resolver for train: URNs.

    Resolution: train:{NNNN}-{slug} -> plan/_trains/{id}.yaml
    """

    @property
    def family(self) -> str:
        return "train"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a train URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        train_id = urn.replace("train:", "")
        trains_dir = self.plan_dir / "_trains"
        train_path = trains_dir / f"{train_id}.yaml"

        paths = []
        if train_path.exists():
            paths.append(train_path)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Train file not found: {train_path}",
        )

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all train URN declarations."""
        declarations = []
        trains_dir = self.plan_dir / "_trains"
        if not trains_dir.exists():
            return declarations

        import yaml

        for train_file in trains_dir.glob("*.yaml"):
            try:
                with open(train_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and isinstance(data, dict):
                    train_id = data.get("id") or train_file.stem
                    urn = f"train:{train_id}"
                    declarations.append(
                        URNDeclaration(
                            urn=urn,
                            family=self.family,
                            source_path=train_file,
                            context="train definition",
                        )
                    )
            except Exception:
                continue

        return declarations


class ComponentResolver(BaseResolver):
    """
    Resolver for component: URNs.

    Resolution: component:{wagon}:{feature}:{name}:{side}:{layer} -> code files
    """

    @property
    def family(self) -> str:
        return "component"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a component URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        parsed = URNBuilder.parse_urn(urn)
        wagon_id = parsed.get("wagon_id")
        feature_id = parsed.get("feature_id")
        component_name = parsed.get("component_name")
        side = parsed.get("side")
        layer = parsed.get("layer")

        if not all([wagon_id, feature_id, component_name, side, layer]):
            return URNResolution(
                urn=urn, family=self.family, error="Invalid component URN format"
            )

        paths = self._find_component_files(
            wagon_id, feature_id, component_name, side, layer
        )

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Component file not found for: {urn}",
        )

    @staticmethod
    def _stem_match(component_name: str, file_path: Path) -> bool:
        """Case-insensitive exact stem match (not substring) for deterministic resolution."""
        stem = file_path.stem.lower()
        # Normalize component name: PascalCase -> snake_case, dots -> underscores
        target = component_name.replace('.', '_')
        # Insert underscore before uppercase runs: "TrainRunner" -> "Train_Runner"
        target = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', target)
        target = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', target)
        target = target.lower()
        # Also try direct lowercase (for already-lowercase names)
        direct = component_name.lower().replace('.', '_').replace('-', '_')
        return stem == target or stem == direct

    def _find_component_files(
        self,
        wagon_id: str,
        feature_id: str,
        component_name: str,
        side: str,
        layer: str,
    ) -> List[Path]:
        """Find component source files matching the URN."""
        paths = []

        # Train infrastructure: component:trains:* resolves in python/trains/
        if wagon_id == 'trains':
            return self._find_train_infra_files(feature_id, component_name)

        # Map side to directory names
        side_dirs = {
            "frontend": ["lib", "src"], "fe": ["lib", "src"],
            "backend": ["python", "src"], "be": ["python", "src"],
        }
        layer_dirs = {
            "presentation": ["presentation", "views", "widgets"],
            "application": ["application", "services", "usecases"],
            "domain": ["domain", "models", "entities"],
            "integration": ["integration", "repositories", "adapters"],
            "assembly": ["assembly", ""],
        }

        for side_dir in side_dirs.get(side, []):
            base_dir = self.repo_root / side_dir
            if not base_dir.exists():
                continue

            for layer_dir in layer_dirs.get(layer, []):
                search_paths = [
                    base_dir / wagon_id.replace("-", "_") / feature_id.replace("-", "_") / layer_dir,
                    base_dir / "features" / feature_id.replace("-", "_") / layer_dir,
                    base_dir / wagon_id.replace("-", "_") / layer_dir,
                ]
                # For assembly, also check the feature root without layer subdir
                if layer == "assembly":
                    search_paths.append(
                        base_dir / wagon_id.replace("-", "_") / feature_id.replace("-", "_")
                    )

                for search_path in search_paths:
                    if not search_path.exists():
                        continue

                    for ext in ["*.py", "*.dart", "*.ts", "*.tsx"]:
                        for f in search_path.glob(ext):
                            if self._stem_match(component_name, f):
                                paths.append(f)

        return paths

    def _find_train_infra_files(
        self,
        feature_id: str,
        component_name: str,
    ) -> List[Path]:
        """Find train infrastructure component files in python/trains/."""
        paths = []
        trains_dir = self.repo_root / "python" / "trains"
        if not trains_dir.exists():
            return paths

        # Search in python/trains/{feature}/ then python/trains/
        search_paths = [
            trains_dir / feature_id.replace("-", "_"),
            trains_dir,
        ]

        for search_path in search_paths:
            if not search_path.exists():
                continue
            for ext in ["*.py", "*.dart", "*.ts", "*.tsx"]:
                for f in search_path.glob(ext):
                    if self._stem_match(component_name, f):
                        paths.append(f)

        return paths

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all component URN declarations in code files."""
        declarations = []
        # Support both # and // comment styles, case-insensitive URN:
        urn_pattern = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*(component:[^\s]+)")
        # Filter out regex patterns that are not actual URNs
        regex_metacharacters = re.compile(r"[\[\]\(\)\*\+\?\{\}\^\$\\]")

        for code_file in self._walk_files(self.repo_root, {".py", ".dart", ".ts", ".tsx"}):
            try:
                content = code_file.read_text(encoding="utf-8")
                for line_num, line in enumerate(content.split("\n"), 1):
                    match = urn_pattern.search(line)
                    if match:
                        urn_candidate = match.group(1)
                        # Skip regex patterns that are not actual URNs
                        if regex_metacharacters.search(urn_candidate):
                            continue
                        declarations.append(
                            URNDeclaration(
                                urn=urn_candidate,
                                family=self.family,
                                source_path=code_file,
                                line_number=line_num,
                                context="code comment",
                            )
                        )
            except Exception:
                continue

        return declarations


class TableResolver(BaseResolver):
    """
    Resolver for table: URNs.

    Resolution: table:{table_name} -> supabase/migrations/**/tables/{table_name}.sql
    """

    @property
    def family(self) -> str:
        return "table"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a table URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        table_name = urn.replace("table:", "")
        paths = self._find_table_files(table_name)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Table definition not found: {table_name}",
        )

    def _find_table_files(self, table_name: str) -> List[Path]:
        """Find SQL files defining the table."""
        paths = []
        supabase_dir = self.repo_root / "supabase"
        if not supabase_dir.exists():
            return paths

        # Search in migrations for table definitions
        for sql_file in supabase_dir.rglob("*.sql"):
            if table_name in sql_file.stem.lower():
                paths.append(sql_file)
                continue

            # Also check file content for CREATE TABLE
            try:
                content = sql_file.read_text(encoding="utf-8")
                if f"create table" in content.lower() and table_name in content.lower():
                    paths.append(sql_file)
            except Exception:
                continue

        return paths

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all table URN declarations in SQL files."""
        declarations = []
        supabase_dir = self.repo_root / "supabase"
        if not supabase_dir.exists():
            return declarations

        table_pattern = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(\w+)", re.IGNORECASE)

        for sql_file in supabase_dir.rglob("*.sql"):
            try:
                content = sql_file.read_text(encoding="utf-8")
                for match in table_pattern.finditer(content):
                    table_name = match.group(1)
                    urn = f"table:{table_name}"
                    declarations.append(
                        URNDeclaration(
                            urn=urn,
                            family=self.family,
                            source_path=sql_file,
                            context="CREATE TABLE statement",
                        )
                    )
            except Exception:
                continue

        return declarations


class MigrationResolver(BaseResolver):
    """
    Resolver for migration: URNs.

    Resolution: migration:{timestamp}_{name} -> supabase/migrations/{timestamp}_{name}.sql
    """

    @property
    def family(self) -> str:
        return "migration"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a migration URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        migration_id = urn.replace("migration:", "")
        migrations_dir = self.repo_root / "supabase" / "migrations"
        migration_path = migrations_dir / f"{migration_id}.sql"

        paths = []
        if migration_path.exists():
            paths.append(migration_path)

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Migration file not found: {migration_path}",
        )

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all migration URN declarations in migration files."""
        declarations = []
        migrations_dir = self.repo_root / "supabase" / "migrations"
        if not migrations_dir.exists():
            return declarations

        migration_pattern = re.compile(r"^(\d{14}_[a-z][a-z0-9_]*)\.sql$")

        for migration_file in migrations_dir.glob("*.sql"):
            match = migration_pattern.match(migration_file.name)
            if match:
                migration_id = match.group(1)
                urn = f"migration:{migration_id}"
                declarations.append(
                    URNDeclaration(
                        urn=urn,
                        family=self.family,
                        source_path=migration_file,
                        context="migration file",
                    )
                )

        return declarations


class TestResolver(BaseResolver):
    """
    Resolver for test: URNs.

    V3 behavior:
    - Primary: Scans test files for explicit ``# URN: test:...`` headers
    - Parses metadata lines: Acceptance:, WMBT:, Train:, Phase:, Layer:
    - Fallback (migration): auto-generates test: URNs from paths when no explicit header

    Resolution: test:{...} -> test file path (header scanning only for V3)
    """

    # Comment-style URN pattern (# URN: ... or // URN: ...)
    _URN_COMMENT_RE = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*([^\s]+)")
    _REGEX_META_RE = re.compile(r"[\[\]\(\)\*\+\?\{\}\^\$\\]")

    # V3 metadata line patterns (case-insensitive)
    _ACCEPTANCE_RE = re.compile(r"(?:#|//)\s*[Aa]cceptance:\s*([^\s]+)")
    _WMBT_RE = re.compile(r"(?:#|//)\s*[Ww][Mm][Bb][Tt]:\s*([^\s]+)")
    _TRAIN_RE = re.compile(r"(?:#|//)\s*[Tt]rain:\s*([^\s]+)")
    _PHASE_RE = re.compile(r"(?:#|//)\s*[Pp]hase:\s*(RED|GREEN|REFACTOR)")
    _LAYER_RE = re.compile(
        r"(?:#|//)\s*[Ll]ayer:\s*(presentation|application|domain|integration|assembly)"
    )
    _TESTED_BY_RE = re.compile(r"(?:#|//)\s*-\s*(test:[^\s]+)")

    # Valid phases and layers for test headers
    VALID_PHASES = {"RED", "GREEN", "REFACTOR"}
    VALID_TEST_LAYERS = {"presentation", "application", "domain", "integration", "assembly"}

    @property
    def family(self) -> str:
        return "test"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a test URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        # Header scanning only (S8.4) — no path-based derivation
        paths = []
        for test_file in self._iter_test_files():
            try:
                content = test_file.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    match = self._URN_COMMENT_RE.search(line)
                    if match and match.group(1) == urn:
                        paths.append(test_file)
                        break
            except Exception:
                continue

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Test file not found for: {urn}",
        )

    @classmethod
    def parse_test_header(cls, content: str) -> dict:
        """
        Parse V3 test header metadata from file content.

        Returns dict with keys: test_urn, acceptance, wmbt, train, phase, layer, format.
        format is 'acceptance' | 'journey' | 'legacy' | None.
        """
        result = {
            "test_urn": None,
            "acceptance": None,
            "wmbt": None,
            "train": None,
            "phase": None,
            "layer": None,
            "format": None,
        }

        for line in content.split("\n"):
            # Test URN
            m = cls._URN_COMMENT_RE.search(line)
            if m:
                candidate = m.group(1)
                if cls._REGEX_META_RE.search(candidate):
                    continue
                if candidate.startswith("test:") and result["test_urn"] is None:
                    result["test_urn"] = candidate
                    # Determine format
                    if candidate.startswith("test:train:"):
                        result["format"] = "journey"
                    elif ":" in candidate[5:] and re.match(
                        r"^test:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*:[A-Z]",
                        candidate,
                    ):
                        result["format"] = "acceptance"
                    else:
                        result["format"] = "legacy"

            # Acceptance line
            m = cls._ACCEPTANCE_RE.search(line)
            if m:
                result["acceptance"] = m.group(1)

            # WMBT line
            m = cls._WMBT_RE.search(line)
            if m:
                result["wmbt"] = m.group(1)

            # Train line
            m = cls._TRAIN_RE.search(line)
            if m:
                result["train"] = m.group(1)

            # Phase line
            m = cls._PHASE_RE.search(line)
            if m:
                result["phase"] = m.group(1)

            # Layer line
            m = cls._LAYER_RE.search(line)
            if m:
                result["layer"] = m.group(1)

        return result

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all test URN declarations in test files."""
        declarations = []
        seen_urns: Dict[str, URNDeclaration] = {}

        for test_file in self._iter_test_files():
            try:
                content = test_file.read_text(encoding="utf-8")
            except Exception:
                continue

            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                match = self._URN_COMMENT_RE.search(line)
                if not match:
                    continue
                urn_candidate = match.group(1)
                if self._REGEX_META_RE.search(urn_candidate):
                    continue

                if urn_candidate.startswith("test:"):
                    if urn_candidate not in seen_urns:
                        # Parse metadata for context
                        header = self.parse_test_header(content)
                        decl = URNDeclaration(
                            urn=urn_candidate,
                            family=self.family,
                            source_path=test_file,
                            line_number=line_num,
                            context=f"test file ({header.get('format', 'unknown')} format)",
                        )
                        seen_urns[urn_candidate] = decl
                        declarations.append(decl)

        return declarations

    # Test file name patterns (checked against filename, not glob)
    _TEST_PATTERNS = [
        re.compile(r"^test_.*\.py$"),
        re.compile(r"^.*_test\.py$"),
        re.compile(r"^.*_test\.dart$"),
        re.compile(r"^.*\.test\.tsx?$"),
        re.compile(r"^.*\.spec\.ts$"),
    ]

    def _iter_test_files(self):
        """Yield test files matching known patterns, pruning vendored dirs."""
        for fpath in self._walk_files(
            self.repo_root, {".py", ".dart", ".ts", ".tsx"}
        ):
            if any(p.match(fpath.name) for p in self._TEST_PATTERNS):
                yield fpath

class ResolverRegistry:
    """
    Registry coordinating all URN resolvers.

    Provides unified interface for resolving URNs across all families.
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or find_repo_root()
        self._resolvers: Dict[str, BaseResolver] = {}
        self._register_default_resolvers()

    def _register_default_resolvers(self) -> None:
        """Register all default family resolvers."""
        resolvers = [
            WagonResolver(self.repo_root),
            FeatureResolver(self.repo_root),
            WMBTResolver(self.repo_root),
            AcceptanceResolver(self.repo_root),
            ContractResolver(self.repo_root),
            TelemetryResolver(self.repo_root),
            TrainResolver(self.repo_root),
            ComponentResolver(self.repo_root),
            TableResolver(self.repo_root),
            MigrationResolver(self.repo_root),
            TestResolver(self.repo_root),
        ]
        for resolver in resolvers:
            self._resolvers[resolver.family] = resolver

    def register(self, resolver: BaseResolver) -> None:
        """Register a custom resolver."""
        self._resolvers[resolver.family] = resolver

    def get_resolver(self, family: str) -> Optional[BaseResolver]:
        """Get resolver for a specific family."""
        return self._resolvers.get(family)

    def get_family(self, urn: str) -> Optional[str]:
        """Extract family from URN."""
        if ":" not in urn:
            return None
        return urn.split(":")[0]

    def resolve(self, urn: str) -> URNResolution:
        """
        Resolve a URN to its filesystem artifact(s).

        Automatically routes to appropriate resolver based on URN family.
        """
        family = self.get_family(urn)
        if not family:
            return URNResolution(
                urn=urn, family="unknown", error=f"Invalid URN format: {urn}"
            )

        resolver = self._resolvers.get(family)
        if not resolver:
            return URNResolution(
                urn=urn,
                family=family,
                error=f"No resolver registered for family: {family}",
            )

        return resolver.resolve(urn)

    def resolve_all(self, urns: List[str]) -> Dict[str, URNResolution]:
        """Resolve multiple URNs."""
        return {urn: self.resolve(urn) for urn in urns}

    def find_all_declarations(
        self, families: Optional[List[str]] = None
    ) -> Dict[str, List[URNDeclaration]]:
        """
        Find all URN declarations across specified families.

        Args:
            families: List of families to scan. If None, scans all.

        Returns:
            Dict mapping family to list of declarations.
        """
        result = {}
        target_families = families or list(self._resolvers.keys())

        for family in target_families:
            resolver = self._resolvers.get(family)
            if resolver:
                result[family] = resolver.find_declarations()

        return result

    @property
    def families(self) -> List[str]:
        """Return list of registered family names."""
        return list(self._resolvers.keys())

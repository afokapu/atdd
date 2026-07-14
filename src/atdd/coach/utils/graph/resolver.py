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

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple
from abc import ABC, abstractmethod

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.urn import URNGrammar

LOG = logging.getLogger(__name__)

# Single-pass code scan (ResolverRegistry.find_all_declarations_single_pass).
# Same patterns the individual component/test resolvers use.
_COMPONENT_URN_RE = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*(component:[^\s]+)")
_TEST_URN_RE = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*([^\s]+)")
_REGEX_META_RE = re.compile(r"[\[\]\(\)\*\+\?\{\}\^\$\\]")
_CODE_EXTENSIONS = {".py", ".dart", ".ts", ".tsx"}
_CODE_GLOBS = ["*.py", "*.dart", "*.ts", "*.tsx"]


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
    metadata: Dict = field(default_factory=dict)


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
    metadata: Dict = field(default_factory=dict)

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

    def _load_yaml_dict(self, path: Path) -> Optional[dict]:
        """Parse a YAML file to a mapping. None when unreadable or not a mapping."""
        import yaml

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            LOG.debug("Skipping unreadable YAML %s: %s", path, e)
            return None

        return data if isinstance(data, dict) else None

    def _urn_declaration(
        self, yaml_file: Path, prefix: str, context: str
    ) -> Optional[URNDeclaration]:
        """Declaration for a file's top-level ``urn:`` field carrying ``prefix``.

        None when the file is unreadable, is not a mapping, or declares no
        matching URN.
        """
        data = self._load_yaml_dict(yaml_file)
        if not data:
            return None

        urn = data.get("urn")
        if not (urn and urn.startswith(prefix)):
            return None

        return URNDeclaration(
            urn=urn,
            family=self.family,
            source_path=yaml_file,
            context=context,
        )

    def _validate_urn_format(self, urn: str) -> Optional[str]:
        """Validate URN format against PATTERNS. Returns error message or None."""
        pattern = URNGrammar.PATTERNS.get(self.family)
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
            data = self._load_yaml_dict(manifest)
            if not data:
                continue

            wagon_slug = data.get("wagon")
            if wagon_slug:
                declarations.append(URNDeclaration(
                    urn=f"wagon:{wagon_slug}",
                    family=self.family,
                    source_path=manifest,
                    context="wagon manifest",
                ))

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
            declaration = self._urn_declaration(feature_file, "feature:", "feature file")
            if declaration:
                declarations.append(declaration)

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

                declaration = self._urn_declaration(wmbt_file, "wmbt:", "WMBT file")
                if declaration:
                    declarations.append(declaration)

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

        parsed = URNGrammar.parse_urn(urn)
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
        """Find all acceptance URN declarations in WMBT and train YAML files.

        WMBT acceptances live under ``plan/<wagon>/[DLPCEMYRK]NNN.yaml``.
        Train acceptances live under ``plan/_trains/<train-id>.yaml`` (substrate
        spec v12 §5.2). Both sources contribute ``acc:`` URN declarations.
        """
        declarations = []
        if not self.plan_dir.exists():
            return declarations

        # WMBT acceptances: plan/<wagon>/[DLPCEMYRK]NNN.yaml
        wmbt_pattern = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")
        for wagon_dir in self.plan_dir.iterdir():
            if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
                continue

            for wmbt_file in wagon_dir.glob("*.yaml"):
                if wmbt_pattern.match(wmbt_file.name):
                    declarations.extend(self._acc_declarations_in(wmbt_file, "WMBT acceptance block"))

        # Train acceptances: plan/_trains/<train-id>.yaml
        trains_dir = self.plan_dir / "_trains"
        if trains_dir.is_dir():
            for train_file in trains_dir.glob("*.yaml"):
                declarations.extend(self._acc_declarations_in(train_file, "train acceptance block"))

        return declarations

    def _acc_declarations_in(self, yaml_file: Path, context: str) -> List[URNDeclaration]:
        """The ``acc:`` URN declarations carried in one WMBT / train YAML file."""
        import yaml

        declarations: List[URNDeclaration] = []
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                return declarations

            for acc in data.get("acceptances", []) or []:
                acc_urn = acc.get("identity", {}).get("urn")
                if not (acc_urn and acc_urn.startswith("acc:")):
                    continue
                declarations.append(URNDeclaration(
                    urn=acc_urn,
                    family=self.family,
                    source_path=yaml_file,
                    context=context,
                ))
        except Exception as e:
            LOG.debug("Skipping unreadable acceptance source %s: %s", yaml_file, e)
        return declarations


class SecurityResolver(BaseResolver):
    """
    Resolver for security: URNs.

    Reads ``feature.yaml::security.abuse_cases[]`` and emits
    ``security:<wagon>:<feature-slug>:<threat-seq>`` URNs.

    Threat-seq is derived from ``abuse_case.id`` by stripping the
    alphabetic prefix and zero-padding the trailing number to three digits
    (e.g. id ``"THREAT-1"`` → seq ``"001"``; id ``"THREAT-42"`` → ``"042"``;
    id ``"THREAT-001"`` → ``"001"``). Ids whose tail is >999 are rejected.
    """

    _ABUSE_ID_RE = re.compile(r"^([A-Z][A-Z0-9-]*)-(\d+)$")

    @property
    def family(self) -> str:
        return "security"

    @classmethod
    def derive_threat_seq(cls, abuse_id: object) -> Tuple[Optional[str], Optional[str]]:
        """
        Validate an ``abuse_case.id`` value and derive the zero-padded
        three-digit threat sequence.

        Returns ``(seq, error)``. ``seq`` is None if validation fails;
        ``error`` is None on success.
        """
        if abuse_id is None:
            return None, "abuse_case is missing required 'id' field"
        if not isinstance(abuse_id, str) or not abuse_id.strip():
            return None, f"abuse_case 'id' must be a non-empty string (got {abuse_id!r})"
        match = cls._ABUSE_ID_RE.match(abuse_id.strip())
        if not match:
            return (
                None,
                (
                    f"abuse_case id {abuse_id!r} does not match required pattern "
                    f"^[A-Z][A-Z0-9-]*-\\d+$ (e.g. 'THREAT-001')"
                ),
            )
        numeric = int(match.group(2))
        if numeric > 999:
            return (
                None,
                (
                    f"abuse_case id {abuse_id!r} has numeric tail {numeric} which exceeds 999; "
                    "threat-seq must fit in three digits"
                ),
            )
        return f"{numeric:03d}", None

    def _iter_feature_files(self):
        """Yield every ``plan/<wagon>/features/*.yaml`` file."""
        if not self.plan_dir.exists():
            return
        for feature_file in self.plan_dir.rglob("features/*.yaml"):
            yield feature_file

    @staticmethod
    def _extract_wagon_feature_from_yaml(data: dict, fallback_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """
        Recover (wagon_slug, feature_slug) from a feature YAML.

        Prefer the canonical ``urn: feature:<wagon>:<feature>`` field; fall
        back to the on-disk path layout ``plan/<wagon>/features/<feature>.yaml``.
        """
        wagon_slug = None
        feature_slug = None
        feature_urn = data.get("urn") if isinstance(data, dict) else None
        if isinstance(feature_urn, str) and feature_urn.startswith("feature:"):
            parts = feature_urn[len("feature:"):].split(":")
            if len(parts) == 2 and all(parts):
                wagon_slug, feature_slug = parts[0], parts[1]
        if not wagon_slug or not feature_slug:
            try:
                # plan/<wagon>/features/<feature>.yaml
                feature_slug = feature_slug or fallback_path.stem.replace("_", "-")
                wagon_dir = fallback_path.parent.parent
                wagon_slug = wagon_slug or wagon_dir.name.replace("_", "-")
            except (AttributeError, IndexError) as exc:
                context = {
                    "resolver": "security",
                    "phase": "wagon_feature_path_fallback",
                    "fallback_path": str(fallback_path),
                    "wagon_slug": wagon_slug,
                    "feature_slug": feature_slug,
                    "exception_type": type(exc).__name__,
                }
                LOG.warning(
                    "SecurityResolver: could not derive wagon/feature from path %s: %s",
                    fallback_path, exc, extra=context,
                )
        return wagon_slug, feature_slug

    @staticmethod
    def _abuse_metadata(abuse: dict) -> Dict:
        """
        Build a metadata dict from an abuse_case YAML block.

        Preserves spec fields verbatim so downstream consumers
        (graph nodes, validators) can read them without re-parsing.
        """
        keys = ("id", "name", "threat", "mitigation", "severity", "acceptance_ref")
        return {k: abuse.get(k) for k in keys if k in abuse}

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all security URN declarations across feature YAMLs."""
        declarations: List[URNDeclaration] = []
        if not self.plan_dir.exists():
            return declarations

        for feature_file in self._iter_feature_files():
            declarations.extend(self._security_declarations_in(feature_file))

        return declarations

    def _security_declarations_in(self, feature_file: Path) -> List[URNDeclaration]:
        """The ``security:`` URNs declared by one feature YAML's abuse_cases block."""
        data = self._load_yaml_dict(feature_file)
        if not data:
            return []

        security = data.get("security")
        if not isinstance(security, dict):
            return []

        abuse_cases = security.get("abuse_cases")
        if not isinstance(abuse_cases, list) or not abuse_cases:
            return []

        wagon_slug, feature_slug = self._extract_wagon_feature_from_yaml(data, feature_file)
        if not wagon_slug or not feature_slug:
            return []

        declarations: List[URNDeclaration] = []
        for abuse in abuse_cases:
            if not isinstance(abuse, dict):
                continue

            seq, err = self.derive_threat_seq(abuse.get("id"))
            if err:
                raise ValueError(f"{feature_file}: {err}")

            declarations.append(URNDeclaration(
                urn=f"security:{wagon_slug}:{feature_slug}:{seq}",
                family=self.family,
                source_path=feature_file,
                context="abuse_case",
                metadata=self._abuse_metadata(abuse),
            ))
        return declarations

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a security URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        parsed = self._parse_security_urn(urn)
        if parsed is None:
            return URNResolution(
                urn=urn, family=self.family, error="Invalid security URN format"
            )
        wagon_slug, feature_slug, seq = parsed

        wagon_dir = self.plan_dir / wagon_slug.replace("-", "_")
        feature_path = wagon_dir / "features" / f"{feature_slug.replace('-', '_')}.yaml"

        if not feature_path.exists():
            return URNResolution(
                urn=urn,
                family=self.family,
                resolved_paths=[],
                is_deterministic=False,
                error=f"Feature file not found for security URN: {feature_path}",
            )

        data, load_error = self._load_feature_yaml(feature_path, urn)
        if load_error:
            return URNResolution(urn=urn, family=self.family, error=load_error)

        security = (data or {}).get("security") or {}
        abuse = self._matching_abuse(security.get("abuse_cases") or [], seq)
        if abuse is not None:
            return URNResolution(
                urn=urn,
                family=self.family,
                resolved_paths=[feature_path],
                is_deterministic=True,
                error=None,
                metadata=self._abuse_metadata(abuse),
            )

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=[],
            is_deterministic=False,
            error=f"No abuse_case with threat-seq {seq} found in {feature_path}",
        )

    def _parse_security_urn(self, urn: str) -> Optional[Tuple[str, str, str]]:
        """(wagon, feature, threat-seq) from a security URN; None when malformed."""
        parts = urn.replace("security:", "").split(":")
        if len(parts) != 3:
            return None
        return parts[0], parts[1], parts[2]

    def _load_feature_yaml(
        self, feature_path: Path, urn: str
    ) -> Tuple[Optional[dict], Optional[str]]:
        """Parse a feature YAML for resolution. Returns (data, error message)."""
        import yaml

        try:
            with open(feature_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f), None
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            wagon_slug, feature_slug, seq = self._parse_security_urn(urn) or ("", "", "")
            LOG.warning(
                "SecurityResolver: failed to parse feature file %s: %s",
                feature_path, exc,
                extra={
                    "resolver": "security",
                    "phase": "resolve_yaml_load",
                    "urn": urn,
                    "feature_path": str(feature_path),
                    "wagon_slug": wagon_slug,
                    "feature_slug": feature_slug,
                    "threat_seq": seq,
                    "exception_type": type(exc).__name__,
                },
            )
            return None, f"Failed to parse feature file {feature_path}: {exc}"

    def _matching_abuse(self, abuse_cases: list, seq: str) -> Optional[dict]:
        """The abuse_case whose derived threat sequence equals ``seq``."""
        for abuse in abuse_cases:
            if not isinstance(abuse, dict):
                continue

            derived_seq, derive_err = self.derive_threat_seq(abuse.get("id"))
            if derive_err or derived_seq != seq:
                continue
            return abuse
        return None


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

        for contract_file in self.contracts_dir.rglob("*.schema.json"):
            declaration = self._contract_declaration(contract_file)
            if declaration:
                declarations.append(declaration)

        return declarations

    def _contract_declaration(self, contract_file: Path) -> Optional[URNDeclaration]:
        """The ``contract:`` URN declared by one schema file, if it declares one."""
        import json

        try:
            with open(contract_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            LOG.debug("Skipping unreadable contract schema %s: %s", contract_file, e)
            return None

        if not isinstance(data, dict):
            return None

        contract_id = data.get("$id")
        # Skip urn:jel:* IDs (JEL package headers, not ATDD contracts)
        if not contract_id or contract_id.startswith("urn:jel:"):
            return None

        return URNDeclaration(
            urn=f"contract:{contract_id}",
            family=self.family,
            source_path=contract_file,
            context="contract schema",
        )


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

        # A file matches on either the bare id or the telemetry:-prefixed one
        wanted = {telemetry_id, f"telemetry:{telemetry_id}"}
        for pattern in ("*.yaml", "*.json"):
            for telemetry_file in self.telemetry_dir.rglob(pattern):
                if self._telemetry_file_id(telemetry_file) in wanted:
                    paths.append(telemetry_file)

        return paths

    def _telemetry_file_id(self, telemetry_file: Path) -> str:
        """The ``$id``/``id`` a telemetry file declares; "" when unreadable."""
        import json
        import yaml

        try:
            with open(telemetry_file, "r", encoding="utf-8") as f:
                if telemetry_file.suffix == ".json":
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)
        except Exception as e:
            LOG.debug("Skipping unreadable telemetry file %s: %s", telemetry_file, e)
            return ""

        if not isinstance(data, dict):
            return ""
        return data.get("$id") or data.get("id", "")

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all telemetry URN declarations."""
        declarations = []
        if not self.telemetry_dir.exists():
            return declarations

        for pattern in ("*.yaml", "*.json"):
            for telemetry_file in self.telemetry_dir.rglob(pattern):
                declaration = self._telemetry_declaration(telemetry_file)
                if declaration:
                    declarations.append(declaration)

        return declarations

    def _telemetry_declaration(self, telemetry_file: Path) -> Optional[URNDeclaration]:
        """The ``telemetry:`` URN declared by one telemetry file (YAML or JSON)."""
        import json
        import yaml

        try:
            with open(telemetry_file, "r", encoding="utf-8") as f:
                if telemetry_file.suffix == ".json":
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)
        except Exception as e:
            LOG.debug("Skipping unreadable telemetry file %s: %s", telemetry_file, e)
            return None

        if not isinstance(data, dict):
            return None

        telemetry_id = data.get("$id") or data.get("id")
        if not telemetry_id:
            return None

        urn = (
            telemetry_id
            if telemetry_id.startswith("telemetry:")
            else f"telemetry:{telemetry_id}"
        )
        return URNDeclaration(
            urn=urn,
            family=self.family,
            source_path=telemetry_file,
            context="telemetry definition",
        )


class SubjectResolver(BaseResolver):
    """
    Resolver for subject: URNs (issue #1421).

    ``subject:<name>`` is a 1-token ROOT family — the durable noun object of a
    train's change (e.g. ``subject:artifact-identity``). It exists so a typed
    2-token ``train:<subject>:<slug>`` has a real parent and is not flagged
    orphan by the graph model.

    Resolution: ``subject:<name>`` -> its entry in the subject registry
    ``plan/_subjects.yaml`` (the registry file is the resolved artifact). The
    registry is authored by the migration; its ABSENCE is tolerated gracefully
    (the family exists before the registry is authored mid-transition).

    Registry shape (coordinated with the migration worker, C4):

        subjects:
          - subject: artifact-identity
            title: Artifact identity
            description: ...
            status: active

    A dict-keyed shape (``subjects: {artifact-identity: {...}}``) and a bare
    top-level mapping are also tolerated so this resolver is robust to the final
    authoring choice.
    """

    _REGISTRY_NAME = "_subjects.yaml"

    @property
    def family(self) -> str:
        return "subject"

    def _registry_path(self) -> Path:
        return self.plan_dir / self._REGISTRY_NAME

    def _load_registry(self) -> Dict[str, dict]:
        """Return ``{name: entry}`` from the subject registry, or ``{}``.

        Tolerant of absence and of shape — never raises.
        """
        path = self._registry_path()
        if not path.exists():
            return {}
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOG.debug("subject registry unreadable; treating as empty",
                      extra={"path": str(path), "error": str(exc)})
            return {}
        return self._normalize_registry(data)

    @staticmethod
    def _normalize_registry(data) -> Dict[str, dict]:
        """Flatten a registry document into ``{name: entry}``.

        Accepts the canonical list-of-entries shape, a dict-keyed shape, and a
        bare top-level mapping. In every dict shape only dict-valued rows are
        treated as subjects, so scalar metadata (``version:`` etc.) is ignored.
        """
        entries: Dict[str, dict] = {}
        if not data:
            return entries

        block = data.get("subjects") if isinstance(data, dict) else None
        if block is None and isinstance(data, dict):
            block = data  # bare top-level mapping fallback

        if isinstance(block, list):
            return SubjectResolver._entries_from_list(block)

        if isinstance(block, dict):
            return {
                name: item
                for name, item in block.items()
                if isinstance(name, str) and isinstance(item, dict)
            }

        return entries

    @staticmethod
    def _entries_from_list(block: list) -> Dict[str, dict]:
        """Subjects from the canonical list-of-entries shape."""
        entries: Dict[str, dict] = {}
        for item in block:
            if isinstance(item, dict):
                name = item.get("subject") or item.get("name")
                if isinstance(name, str) and name:
                    entries[name] = item
            elif isinstance(item, str) and item:
                entries[item] = {"subject": item}
        return entries

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a subject URN")

        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        name = urn[len("subject:"):]
        registry_path = self._registry_path()
        if not registry_path.exists():
            return URNResolution(
                urn=urn,
                family=self.family,
                resolved_paths=[],
                is_deterministic=False,
                error=f"Subject registry not found: {registry_path}",
            )

        entries = self._load_registry()
        entry = entries.get(name)
        if entry is None:
            return URNResolution(
                urn=urn,
                family=self.family,
                resolved_paths=[],
                is_deterministic=False,
                error=f"Subject '{name}' not registered in {registry_path.name}",
            )

        metadata = {
            k: entry.get(k)
            for k in ("title", "description", "status")
            if isinstance(entry, dict) and k in entry
        }
        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=[registry_path],
            is_deterministic=True,
            error=None,
            metadata=metadata,
        )

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all subject URN declarations in the subject registry."""
        declarations: List[URNDeclaration] = []
        registry_path = self._registry_path()
        for name in self._load_registry():
            declarations.append(
                URNDeclaration(
                    urn=f"subject:{name}",
                    family=self.family,
                    source_path=registry_path,
                    context="subject registry",
                )
            )
        return declarations


class TrainResolver(BaseResolver):
    """
    Resolver for train: URNs.

    Typed grammar (issue #1421):
        ``train:<subject>:<slug>``  ->  ``plan/_trains/<subject>/<slug>.yaml``
    The reverse (path -> URN) reconstructs ``<subject>/<slug>`` from the nested
    directory layout — not the flat ``NNNN`` stem.

    Dual-resolution during migration: a legacy ``train:NNNN-slug`` URN STILL
    resolves. It is mapped to its typed nested file via the alias map the
    migration worker (C4) produces (``plan/_trains/_aliases.yaml``); if no alias
    is registered yet it falls back to the flat ``plan/_trains/NNNN-slug.yaml``
    file so nothing breaks mid-transition.
    """

    # Legacy flat train id: NNNN-slug (digit-led single token). Kept local and
    # scoped to the migration window — the typed grammar itself lives in the
    # convention (urn_grammar.yaml), executed by URNGrammar.
    _LEGACY_TRAIN_RE = re.compile(r"^\d{4}-[a-z0-9][a-z0-9-]*$")

    # Alias-map file candidates (the migration worker's data). Tolerant of
    # location so this resolver is robust to C4's final authoring choice.
    _ALIAS_FILE_CANDIDATES = ("_aliases.yaml", "_alias_map.yaml")

    @property
    def family(self) -> str:
        return "train"

    def resolve(self, urn: str) -> URNResolution:
        if not self.can_resolve(urn):
            return URNResolution(urn=urn, family=self.family, error="Not a train URN")

        body = urn[len("train:"):]
        trains_dir = self.plan_dir / "_trains"

        # Legacy dual-resolution: single-token, digit-led NNNN-slug. This form
        # is intentionally NOT in the typed engine grammar, so it must bypass
        # the strict format gate below.
        if ":" not in body and self._LEGACY_TRAIN_RE.match(body):
            return self._resolve_legacy(urn, body, trains_dir)

        # Typed grammar: train:<subject>:<slug>.
        error = self._validate_urn_format(urn)
        if error:
            return URNResolution(urn=urn, family=self.family, error=error)

        subject, slug = body.split(":", 1)
        train_path = trains_dir / subject / f"{slug}.yaml"
        paths = [train_path] if train_path.exists() else []
        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Train file not found: {train_path}",
        )

    def _resolve_legacy(
        self, urn: str, legacy_id: str, trains_dir: Path
    ) -> URNResolution:
        """Resolve a legacy ``train:NNNN-slug`` URN.

        Prefers the migration alias map (legacy id -> typed nested file); falls
        back to the flat ``plan/_trains/NNNN-slug.yaml`` file still in place
        pre-migration.
        """
        typed = self._alias_lookup(legacy_id)
        if typed:
            subject, slug = typed
            typed_path = trains_dir / subject / f"{slug}.yaml"
            if typed_path.exists():
                return URNResolution(
                    urn=urn,
                    family=self.family,
                    resolved_paths=[typed_path],
                    is_deterministic=True,
                    error=None,
                    metadata={"alias_of": f"train:{subject}:{slug}"},
                )

        flat_path = trains_dir / f"{legacy_id}.yaml"
        paths = [flat_path] if flat_path.exists() else []
        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Train file not found for legacy id: {flat_path}",
        )

    def _load_alias_map(self) -> Dict[str, Tuple[str, str]]:
        """Return ``{legacy-id: (subject, slug)}`` from the migration alias map.

        Tolerant of absence and of shape — never raises. Recognized content: a
        top-level ``aliases:`` mapping or a bare mapping, whose keys are
        ``NNNN-slug`` (optionally ``train:``-prefixed) and whose values are
        ``subject/slug`` | ``subject:slug`` | ``train:subject:slug``.
        """
        raw = self._load_alias_document()
        if not isinstance(raw, dict):
            return {}

        mapping = raw.get("aliases") if isinstance(raw.get("aliases"), dict) else raw
        if not isinstance(mapping, dict):
            return {}

        result: Dict[str, Tuple[str, str]] = {}
        for key, val in mapping.items():
            if not isinstance(key, str):
                continue
            legacy = key[len("train:"):] if key.startswith("train:") else key
            typed = self._split_typed(val)
            if typed:
                result[legacy] = typed
        return result

    def _load_alias_document(self) -> Optional[dict]:
        """Parse the first alias-map file that exists. None when absent or unreadable."""
        trains_dir = self.plan_dir / "_trains"
        for candidate in self._ALIAS_FILE_CANDIDATES:
            path = trains_dir / candidate
            if not path.exists():
                continue

            try:
                import yaml

                return yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as e:
                LOG.debug("Skipping unreadable alias map %s: %s", path, e)
                return None
        return None

    def _alias_lookup(self, legacy_id: str) -> Optional[Tuple[str, str]]:
        return self._load_alias_map().get(legacy_id)

    @staticmethod
    def _split_typed(val) -> Optional[Tuple[str, str]]:
        """Parse an alias value into ``(subject, slug)``.

        Tolerates a leading ``train:`` prefix and both ``subject/slug`` and
        ``subject:slug`` separators.
        """
        if not isinstance(val, str):
            return None
        v = val.strip()
        if v.startswith("train:"):
            v = v[len("train:"):]
        if "/" in v and ":" not in v:
            parts = v.split("/", 1)
        else:
            parts = v.split(":", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        return None

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all train URN declarations.

        Typed trains live at ``plan/_trains/<subject>/<slug>.yaml`` and their URN
        is reconstructed from the nested path (``subject/slug``, not the flat
        stem). Legacy flat files (``plan/_trains/NNNN-slug.yaml``) are still
        enumerated during migration, preferring an explicit ``id`` field, else
        the file stem.
        """
        declarations: List[URNDeclaration] = []
        trains_dir = self.plan_dir / "_trains"
        if not trains_dir.exists():
            return declarations

        # Typed: plan/_trains/<subject>/<slug>.yaml  (path -> subject/slug).
        for subject_dir in sorted(trains_dir.iterdir()):
            if not subject_dir.is_dir() or subject_dir.name.startswith("_"):
                continue

            for train_file in sorted(subject_dir.glob("*.yaml")):
                if train_file.name.startswith("_"):
                    continue
                declarations.append(URNDeclaration(
                    urn=f"train:{subject_dir.name}:{train_file.stem}",
                    family=self.family,
                    source_path=train_file,
                    context="train definition (typed)",
                ))

        # Legacy flat files (migration window). Registry/alias files (``_*``)
        # are skipped.
        for train_file in sorted(trains_dir.glob("*.yaml")):
            if train_file.name.startswith("_"):
                continue

            declarations.append(URNDeclaration(
                urn=self._legacy_train_urn(train_file),
                family=self.family,
                source_path=train_file,
                context="train definition (legacy)",
            ))

        return declarations

    def _legacy_train_urn(self, train_file: Path) -> str:
        """URN for a legacy flat train file: its ``id`` field, else the file stem."""
        data = self._load_yaml_dict(train_file)
        train_id = (data.get("id") if data else None) or train_file.stem
        if str(train_id).startswith("train:"):
            return train_id
        return f"train:{train_id}"


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

        parsed = URNGrammar.parse_urn(urn)
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
                search_paths = self._component_search_paths(
                    base_dir, wagon_id, feature_id, layer, layer_dir
                )
                for search_path in search_paths:
                    paths.extend(self._matching_component_files(search_path, component_name))

        return paths

    def _component_search_paths(
        self, base_dir: Path, wagon_id: str, feature_id: str, layer: str, layer_dir: str
    ) -> List[Path]:
        """Directories that may hold a component for this wagon/feature/layer."""
        wagon = wagon_id.replace("-", "_")
        feature = feature_id.replace("-", "_")

        search_paths = [
            base_dir / wagon / feature / layer_dir,
            base_dir / wagon / feature / "src" / layer_dir,
            base_dir / "features" / feature / layer_dir,
            base_dir / wagon / layer_dir,
        ]
        # For assembly, also check the feature root without layer subdir
        if layer == "assembly":
            search_paths.append(base_dir / wagon / feature)
        return search_paths

    def _matching_component_files(self, search_path: Path, component_name: str) -> List[Path]:
        """Code files under search_path whose stem matches the component name."""
        if not search_path.exists():
            return []

        return [
            f
            for ext in _CODE_GLOBS
            for f in search_path.rglob(ext)
            if self._stem_match(component_name, f)
        ]

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
        for code_file in self._walk_files(self.repo_root, _CODE_EXTENSIONS):
            declarations.extend(self._component_declarations_in(code_file))

        return declarations

    def _component_declarations_in(self, code_file: Path) -> List[URNDeclaration]:
        """Component URN declarations carried in one code file's comments."""
        try:
            content = code_file.read_text(encoding="utf-8")
        except Exception as e:
            LOG.debug("Skipping unreadable code file %s: %s", code_file, e)
            return []

        declarations: List[URNDeclaration] = []
        for line_num, line in enumerate(content.split("\n"), 1):
            match = _COMPONENT_URN_RE.search(line)
            if not match:
                continue

            # Skip regex patterns that are not actual URNs
            urn_candidate = match.group(1)
            if _REGEX_META_RE.search(urn_candidate):
                continue

            declarations.append(URNDeclaration(
                urn=urn_candidate,
                family=self.family,
                source_path=code_file,
                line_number=line_num,
                context="code comment",
            ))
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
            declarations.extend(self._table_declarations_in(sql_file, table_pattern))

        return declarations

    def _table_declarations_in(self, sql_file: Path, table_pattern) -> List[URNDeclaration]:
        """A ``table:`` URN for every CREATE TABLE statement in one SQL file."""
        try:
            content = sql_file.read_text(encoding="utf-8")
        except Exception as e:
            LOG.debug("Skipping unreadable SQL file %s: %s", sql_file, e)
            return []

        return [
            URNDeclaration(
                urn=f"table:{match.group(1)}",
                family=self.family,
                source_path=sql_file,
                context="CREATE TABLE statement",
            )
            for match in table_pattern.finditer(content)
        ]


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
                declarations.append(URNDeclaration(
                    urn=f"migration:{match.group(1)}",
                    family=self.family,
                    source_path=migration_file,
                    context="migration file",
                ))

        return declarations


class TestResolver(BaseResolver):
    """
    Resolver for test: URNs.

    NOTE: __test__ = False prevents pytest from collecting this as a test class.

    V3 behavior:
    - Scans test files for explicit ``# URN: test:...`` headers (S8.4)
    - Parses metadata lines: Acceptance:, WMBT:, Train:, Phase:, Layer:
    - No path-based derivation; header scanning only

    Resolution: test:{...} -> test file path
    """

    __test__ = False  # Prevent pytest collection

    # Comment-style URN pattern (# URN: ... or // URN: ...)
    _URN_COMMENT_RE = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*([^\s]+)")
    _REGEX_META_RE = re.compile(r"[\[\]\(\)\*\+\?\{\}\^\$\\]")

    # V3 metadata line patterns (case-insensitive)
    _ACCEPTANCE_RE = re.compile(r"(?:#|//)\s*[Aa]cceptance:\s*([^\s]+)")
    _WMBT_RE = re.compile(r"(?:#|//)\s*[Ww][Mm][Bb][Tt]:\s*([^\s]+)")
    _TRAIN_RE = re.compile(r"(?:#|//)\s*[Tt]rain:\s*([^\s]+)")
    _PHASE_RE = re.compile(r"(?:#|//)\s*[Pp]hase:\s*(RED|GREEN|SMOKE|REFACTOR)")
    _LAYER_RE = re.compile(
        r"(?:#|//)\s*[Ll]ayer:\s*(presentation|application|domain|integration|assembly)"
    )
    _ASSERTION_RE = re.compile(
        r"(?:#|//)\s*[Aa]ssertion:\s*(structural|behavioral)"
    )
    _TESTED_BY_RE = re.compile(r"(?:#|//)\s*-\s*(test:[^\s]+)")

    # Valid phases and layers for test headers
    VALID_PHASES = {"RED", "GREEN", "SMOKE", "REFACTOR"}
    VALID_TEST_LAYERS = {"presentation", "application", "domain", "integration", "assembly"}
    VALID_ASSERTIONS = {"structural", "behavioral"}

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
        paths = [f for f in self._iter_test_files() if self._declares_test_urn(f, urn)]

        return URNResolution(
            urn=urn,
            family=self.family,
            resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Test file not found for: {urn}",
        )

    def _declares_test_urn(self, test_file: Path, urn: str) -> bool:
        """Whether a test file's header declares exactly this test URN."""
        try:
            content = test_file.read_text(encoding="utf-8")
        except Exception as e:
            LOG.debug("Skipping unreadable test file %s: %s", test_file, e)
            return False

        for line in content.split("\n"):
            match = self._URN_COMMENT_RE.search(line)
            if match and match.group(1) == urn:
                return True
        return False

    @classmethod
    def parse_test_header(cls, content: str) -> dict:
        """
        Parse V3 test header metadata from file content.

        Returns dict with keys: test_urn, acceptance, wmbt, train, phase, layer, assertion, format.
        format is 'acceptance' | 'journey' | 'legacy' | None.
        assertion is 'structural' | 'behavioral' | None (None when undeclared — legacy tests).
        """
        result = {
            "test_urn": None,
            "acceptance": None,
            "wmbt": None,
            "train": None,
            "phase": None,
            "layer": None,
            "assertion": None,
            "format": None,
        }

        # Header fields each carried by a single "Key: value" comment line
        simple_fields = (
            ("acceptance", cls._ACCEPTANCE_RE),
            ("wmbt", cls._WMBT_RE),
            ("train", cls._TRAIN_RE),
            ("phase", cls._PHASE_RE),
            ("layer", cls._LAYER_RE),
            ("assertion", cls._ASSERTION_RE),
        )

        for line in content.split("\n"):
            if cls._parse_urn_header_line(line, result):
                continue

            for field, pattern in simple_fields:
                m = pattern.search(line)
                if m:
                    result[field] = m.group(1)

        return result

    @classmethod
    def _parse_urn_header_line(cls, line: str, result: Dict) -> bool:
        """Record the first ``test:`` URN on this line and its format.

        Returns True when the line carries a regex pattern rather than a URN,
        in which case the caller skips the rest of the line.
        """
        m = cls._URN_COMMENT_RE.search(line)
        if not m:
            return False

        candidate = m.group(1)
        if cls._REGEX_META_RE.search(candidate):
            return True

        if candidate.startswith("test:") and result["test_urn"] is None:
            result["test_urn"] = candidate
            result["format"] = cls._test_urn_format(candidate)
        return False

    @classmethod
    def _test_urn_format(cls, candidate: str) -> str:
        """Which test-URN grammar a candidate follows."""
        if candidate.startswith("test:train:"):
            return "journey"

        is_acceptance = ":" in candidate[5:] and re.match(
            r"^test:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*:[A-Z]",
            candidate,
        )
        return "acceptance" if is_acceptance else "legacy"

    def find_declarations(self) -> List[URNDeclaration]:
        """Find all test URN declarations in test files."""
        declarations = []
        seen_urns: Dict[str, URNDeclaration] = {}

        for test_file in self._iter_test_files():
            declarations.extend(self._test_declarations_in(test_file, seen_urns))

        return declarations

    def _test_declarations_in(
        self, test_file: Path, seen_urns: Dict[str, URNDeclaration]
    ) -> List[URNDeclaration]:
        """Test URN declarations in one file; the first declaration of each URN wins."""
        try:
            content = test_file.read_text(encoding="utf-8")
        except Exception as e:
            LOG.debug("Skipping unreadable test file %s: %s", test_file, e)
            return []

        declarations: List[URNDeclaration] = []
        for line_num, line in enumerate(content.split("\n"), 1):
            match = self._URN_COMMENT_RE.search(line)
            if not match:
                continue

            urn_candidate = match.group(1)
            if self._REGEX_META_RE.search(urn_candidate):
                continue
            if not urn_candidate.startswith("test:"):
                continue
            if urn_candidate in seen_urns:
                continue

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
            SecurityResolver(self.repo_root),
            ContractResolver(self.repo_root),
            TelemetryResolver(self.repo_root),
            SubjectResolver(self.repo_root),
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

    def find_all_declarations_single_pass(
        self, families: Optional[List[str]] = None
    ) -> Tuple[Dict[str, List[URNDeclaration]], Dict[str, str]]:
        """
        Find all URN declarations with a single file-tree walk for code files.

        Instead of component and test resolvers each walking the full tree,
        walks once and dispatches URN matches to both families in one pass.
        Non-code resolvers (wagon, feature, wmbt, acc, contract, telemetry,
        train, table, migration) delegate to their own find_declarations().

        Returns:
            Tuple of (declarations_dict, content_cache).
            content_cache maps str(file_path) -> file content for files
            that contained URN declarations (used by edge builders).
        """
        target_families = set(families) if families else set(self._resolvers.keys())
        result: Dict[str, List[URNDeclaration]] = {}
        content_cache: Dict[str, str] = {}

        # Families whose find_declarations() walks the full code tree.
        # Intentionally closed: this is a performance fast-path that batches
        # code-tree walks for component and test families. New URN families
        # whose declarations live in YAML/JSON are handled via their own
        # find_declarations() in the loop below — no edits here required.
        # Audit reference: docs/urn-prefix-audit-2026.md (finding #4).
        code_scan_families = {"component", "test"}

        # Non-code families: delegate to existing find_declarations()
        for family in target_families - code_scan_families:
            resolver = self._resolvers.get(family)
            if resolver:
                result[family] = resolver.find_declarations()

        scan_component = "component" in target_families
        scan_test = "test" in target_families

        if not scan_component and not scan_test:
            return result, content_cache

        component_decls: List[URNDeclaration] = []
        test_decls: List[URNDeclaration] = []
        seen_test_urns: Dict[str, URNDeclaration] = {}

        for fpath, fname in self._walk_code_files():
            found_component, found_test, content = self._scan_code_file(
                fpath, fname, scan_component, scan_test, seen_test_urns
            )
            component_decls.extend(found_component)
            test_decls.extend(found_test)

            # Cache content of files with URN declarations
            if found_component or found_test:
                content_cache[str(fpath)] = content

        if scan_component:
            result["component"] = component_decls
        if scan_test:
            result["test"] = test_decls

        return result, content_cache

    def _scan_code_file(
        self,
        fpath: Path,
        fname: str,
        scan_component: bool,
        scan_test: bool,
        seen_test_urns: Dict[str, URNDeclaration],
    ) -> Tuple[List[URNDeclaration], List[URNDeclaration], Optional[str]]:
        """Scan one code file for component and/or test URN declarations."""
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception as e:
            LOG.debug("Skipping unreadable source file %s: %s", fpath, e)
            return [], [], None

        found_component = (
            self._scan_component_urns(content, fpath) if scan_component else []
        )

        # Test URNs are only declared in test-named files
        is_test_file = any(p.match(fname) for p in TestResolver._TEST_PATTERNS)
        found_test = (
            self._scan_test_urns(content, fpath, seen_test_urns)
            if scan_test and is_test_file
            else []
        )
        return found_component, found_test, content

    def _walk_code_files(self):
        """Yield (path, filename) for every code file, pruning vendored/build dirs."""
        for dirpath, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = [d for d in dirnames if d not in BaseResolver._SKIP_DIRS]
            for fname in filenames:
                if any(fname.endswith(ext) for ext in _CODE_EXTENSIONS):
                    yield Path(dirpath) / fname, fname

    def _scan_component_urns(self, content: str, fpath: Path) -> List[URNDeclaration]:
        """Component URN declarations carried in one file's comments."""
        decls: List[URNDeclaration] = []
        for line_num, line in enumerate(content.split("\n"), 1):
            match = _COMPONENT_URN_RE.search(line)
            if not match:
                continue

            urn_candidate = match.group(1)
            if _REGEX_META_RE.search(urn_candidate):
                continue

            decls.append(
                URNDeclaration(
                    urn=urn_candidate,
                    family="component",
                    source_path=fpath,
                    line_number=line_num,
                    context="code comment",
                )
            )
        return decls

    def _scan_test_urns(
        self, content: str, fpath: Path, seen_test_urns: Dict[str, URNDeclaration]
    ) -> List[URNDeclaration]:
        """Test URN declarations in one test file, first declaration of each URN winning."""
        decls: List[URNDeclaration] = []
        for line_num, line in enumerate(content.split("\n"), 1):
            match = _TEST_URN_RE.search(line)
            if not match:
                continue

            urn_candidate = match.group(1)
            if _REGEX_META_RE.search(urn_candidate):
                continue
            if not urn_candidate.startswith("test:"):
                continue
            if urn_candidate in seen_test_urns:
                continue

            header = TestResolver.parse_test_header(content)
            decl = URNDeclaration(
                urn=urn_candidate,
                family="test",
                source_path=fpath,
                line_number=line_num,
                context=f"test file ({header.get('format', 'unknown')} format)",
            )
            seen_test_urns[urn_candidate] = decl
            decls.append(decl)
        return decls

    @property
    def families(self) -> List[str]:
        """Return list of registered family names."""
        return list(self._resolvers.keys())

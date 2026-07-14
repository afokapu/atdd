"""
Unified Registry System - Load and build all artifact registries.

Architecture: 4-Layer Clean Architecture (single file)
- Domain: Pure business logic (change detection, validation)
- Integration: File I/O adapters (YAML, file scanning)
- Application: Use cases (load registry, build registry)
- Presentation: CLI facades (RegistryLoader, RegistryBuilder)

Registries:
- plan/_wagons.yaml from wagon manifests
- contracts/_artifacts.yaml from contract schemas
- telemetry/_telemetry.yaml from telemetry signals
- atdd/tester/_tests.yaml from test files
- python/_implementations.yaml from Python files
- supabase/_functions.yaml from function files

This command helps maintain coherence between source files and registries.
"""


# ============================================================================
# DOMAIN - Drift error and fix-hint (wmbt:govern-lifecycle:E021)
# ============================================================================

class RegistryDriftError(Exception):
    """Raised when registry mirrors are out of sync with source-of-truth files."""

    def __init__(self, message: str, drift_report: dict | None = None) -> None:
        super().__init__(message)
        self.drift_report: dict = drift_report or {}


def format_fix_hint(drift_report: dict) -> str:
    """Return an actionable fix-hint for registry drift, suitable for stderr.

    Args:
        drift_report: dict with optional 'drifted_files' key listing file paths.

    Returns:
        Multi-line string containing 'atdd registry update --yes' and any drifted files.
    """
    lines = [
        "Registry mirror is out of sync with source-of-truth files.",
        "Run the following command to resync:",
        "  atdd registry update --yes",
    ]
    drifted_files: list = drift_report.get("drifted_files", [])
    if drifted_files:
        lines.append("Drifted files:")
        for f in drifted_files:
            lines.append(f"  - {f}")
    lines.append(
        "Then re-stage and push: git add plan/_wagons.yaml plan/_trains.yaml "
        "contracts/_artifacts.yaml && git commit --amend --no-edit"
    )
    return "\n".join(lines)
import yaml
import json
import re
import ast
import logging
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Any, Optional

from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.theme_map import get_theme_map

_logger = logging.getLogger(__name__)

# Train ID category digit → category name (train.convention.yaml).
CATEGORY_MAP = {"0": "nominal", "1": "error", "2": "alternate", "3": "exception"}

# Import URNGrammar for URN generation (following conventions)
try:
    from atdd.coach.utils.graph.urn import URNGrammar
except ImportError:
    # Fallback if URNGrammar not available
    class URNGrammar:
        @staticmethod
        def test(wagon: str, file: str, func: str) -> str:
            return f"test:{wagon}:{file}::{func}"

        @staticmethod
        def impl(wagon: str, layer: str, component: str, lang: str) -> str:
            return f"impl:{wagon}:{layer}:{component}:{lang}"


# ============================================================================
# PRESENTATION LAYER - CLI Facades
# ============================================================================
# Public API for loading and building registries.
# Delegates to application layer use cases.
# ============================================================================

class RegistryLoader:
    """Loads and queries registries (read-only)."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.plan_dir = repo_root / "plan"
        self.contracts_dir = repo_root / "contracts"
        self.telemetry_dir = repo_root / "telemetry"
        self.tester_dir = repo_root / "atdd" / "tester"
        self.python_dir = repo_root / "python"
        self.supabase_dir = repo_root / "supabase"

    def load_all(self) -> Dict[str, Any]:
        """Load all registries without distinction."""
        return {
            "plan": self.load_planner(),
            "contracts": self.load_contracts(),
            "telemetry": self.load_telemetry(),
            "tester": self.load_tester(),
            "coder": self.load_coder(),
            "supabase": self.load_supabase()
        }

    def load_planner(self) -> Dict[str, Any]:
        """Load planner registry (plan/_wagons.yaml)."""
        registry_path = self.plan_dir / "_wagons.yaml"
        if not registry_path.exists():
            return {"wagons": []}

        with open(registry_path) as f:
            return yaml.safe_load(f) or {"wagons": []}

    def load_contracts(self) -> Dict[str, Any]:
        """Load contracts registry (contracts/_artifacts.yaml)."""
        registry_path = self.contracts_dir / "_artifacts.yaml"
        if not registry_path.exists():
            return {"artifacts": []}

        with open(registry_path) as f:
            return yaml.safe_load(f) or {"artifacts": []}

    def load_telemetry(self) -> Dict[str, Any]:
        """Load telemetry registry (telemetry/_telemetry.yaml)."""
        registry_path = self.telemetry_dir / "_telemetry.yaml"
        if not registry_path.exists():
            return {"signals": []}

        with open(registry_path) as f:
            return yaml.safe_load(f) or {"signals": []}

    def load_tester(self) -> Dict[str, Any]:
        """Load tester registry (atdd/tester/_tests.yaml)."""
        registry_path = self.tester_dir / "_tests.yaml"
        if not registry_path.exists():
            return {"tests": []}

        with open(registry_path) as f:
            return yaml.safe_load(f) or {"tests": []}

    def load_coder(self) -> Dict[str, Any]:
        """Load coder implementation registry (python/_implementations.yaml)."""
        registry_path = self.python_dir / "_implementations.yaml"
        if not registry_path.exists():
            return {"implementations": []}

        with open(registry_path) as f:
            return yaml.safe_load(f) or {"implementations": []}

    def load_supabase(self) -> Dict[str, Any]:
        """Load supabase functions registry (supabase/_functions.yaml)."""
        registry_path = self.supabase_dir / "_functions.yaml"
        if not registry_path.exists():
            return {"functions": []}

        with open(registry_path) as f:
            return yaml.safe_load(f) or {"functions": []}

    def find_implementations_for_spec(self, spec_urn: str) -> List[Dict]:
        """Find all implementations linked to a spec URN."""
        coder_data = self.load_coder()
        return [
            impl for impl in coder_data.get("implementations", [])
            if impl.get("spec_urn") == spec_urn
        ]

    def find_tests_for_implementation(self, impl_urn: str) -> Optional[str]:
        """Find test URN linked to an implementation."""
        coder_data = self.load_coder()
        for impl in coder_data.get("implementations", []):
            if impl.get("urn") == impl_urn:
                return impl.get("test_urn")
        return None


# ============================================================================
# APPLICATION LAYER - Use Cases & Orchestration
# ============================================================================
# Coordinates domain and integration layers.
# Contains registry building logic and workflow orchestration.
# ============================================================================

class RegistryBuilder:
    """Builds and updates registries from source files (formerly RegistryUpdater)."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.plan_dir = repo_root / "plan"
        self.contracts_dir = repo_root / "contracts"
        self.telemetry_dir = repo_root / "telemetry"
        self.tester_dir = repo_root / "atdd" / "tester"
        self.python_dir = repo_root / "python"
        self.supabase_dir = repo_root / "supabase"

    # ========================================================================
    # MODE HANDLING - Unified confirmation and apply logic
    # ========================================================================
    # Handles interactive, apply, and check modes for all registries
    # ========================================================================

    def _confirm_and_apply(
        self,
        mode: str,
        registry_name: str,
        registry_path: Path,
        output_data: Dict[str, Any],
        stats: Dict[str, Any],
        preview_msg: str = ""
    ) -> Dict[str, Any]:
        """
        Handle confirmation and apply based on mode.

        Args:
            mode: "interactive", "apply", or "check"
            registry_name: Human-readable name for messages (e.g., "wagon", "contract")
            registry_path: Path to the registry file
            output_data: Data to write to the registry
            stats: Statistics dict to update with results
            preview_msg: Optional custom preview message

        Returns:
            Updated stats dict with has_changes flag
        """
        has_changes = stats.get("new", 0) > 0 or len(stats.get("changes", [])) > 0
        stats["has_changes"] = has_changes

        if mode == "check":
            if has_changes:
                print(f"\n⚠️  Drift detected in {registry_name} registry")
                hint = format_fix_hint({"drifted_files": [str(registry_path)]})
                print(hint)
            else:
                print(f"\n✅ {registry_name.capitalize()} registry is in sync")
            return stats

        if mode == "apply":
            # Write without prompting
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(registry_path, "w") as f:
                yaml.dump(output_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

            print(f"\n✅ {registry_name.capitalize()} registry updated successfully!")
            print(f"  📝 Registry: {registry_path}")
            return stats

        # Interactive mode - ask for confirmation
        print(f"\n❓ Do you want to apply these changes to the {registry_name} registry?")
        print("   Type 'yes' to confirm, or anything else to cancel:")
        response = input("   > ").strip().lower()

        if response != "yes":
            print("\n❌ Update cancelled by user")
            stats["cancelled"] = True
            return stats

        # Write registry
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(registry_path, "w") as f:
            yaml.dump(output_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"\n✅ {registry_name.capitalize()} registry updated successfully!")
        print(f"  📝 Registry: {registry_path}")
        return stats

    # ========================================================================
    # DOMAIN LAYER - Pure Business Logic (Change Detection)
    # ========================================================================
    # No I/O, no side effects - pure functions for detecting changes
    # ========================================================================

    def _detect_changes(self, slug: str, old_entry: Dict, new_entry: Dict) -> List[str]:
        """
        Detect field-level changes between old and new wagon entries.

        Returns:
            List of changed field names
        """
        changed_fields = []

        # Fields to compare
        compare_fields = ["description", "theme", "subject", "context", "action",
                         "goal", "outcome", "produce", "consume", "wmbt", "total"]

        for field in compare_fields:
            old_val = old_entry.get(field)
            new_val = new_entry.get(field)

            if old_val != new_val:
                changed_fields.append(field)

        return changed_fields

    def _detect_contract_changes(self, artifact_id: str, old_entry: Dict, new_entry: Dict) -> List[str]:
        """
        Detect field-level changes between old and new contract entries.

        Returns:
            List of changed field names
        """
        changed_fields = []

        # Fields to compare
        compare_fields = ["urn", "version", "title", "description", "path", "producer", "consumers"]

        for field in compare_fields:
            old_val = old_entry.get(field)
            new_val = new_entry.get(field)

            if old_val != new_val:
                changed_fields.append(field)

        return changed_fields

    def _detect_telemetry_changes(self, signal_id: str, old_entry: Dict, new_entry: Dict) -> List[str]:
        """
        Detect field-level changes between old and new telemetry signal entries.

        Returns:
            List of changed field names
        """
        changed_fields = []

        # Fields to compare
        compare_fields = ["type", "description", "path"]

        for field in compare_fields:
            old_val = old_entry.get(field)
            new_val = new_entry.get(field)

            if old_val != new_val:
                changed_fields.append(field)

        return changed_fields

    def _extract_features_from_manifest(self, manifest: Dict, wagon_slug: str) -> List[Dict]:
        """
        Extract features list from wagon manifest (DOMAIN logic).

        Args:
            manifest: Wagon manifest data
            wagon_slug: Wagon slug for legacy format conversion

        Returns:
            List of feature objects with 'urn' key, empty list if no features
        """
        if "features" not in manifest or not manifest["features"]:
            return []

        features_data = manifest["features"]

        # Handle array format (current)
        if isinstance(features_data, list):
            return features_data

        # Handle legacy dict format
        if isinstance(features_data, dict):
            return [{"urn": f"feature:{wagon_slug}.{k}"} for k in features_data.keys()]

        return []

    def _extract_wmbt_total_from_manifest(self, manifest: Dict) -> int:
        """
        Extract WMBT total count from wagon manifest (DOMAIN logic).

        Args:
            manifest: Wagon manifest data

        Returns:
            Total WMBT count, 0 if not found
        """
        # Try wmbt.total first (current location)
        if "wmbt" in manifest and isinstance(manifest["wmbt"], dict):
            return manifest["wmbt"].get("total", 0)

        # Fallback to root-level total (legacy)
        return manifest.get("total", 0)

    def _parse_feature_urn(self, urn: str) -> tuple[str, str]:
        """
        Parse feature URN to extract wagon and feature slugs (DOMAIN logic).

        Args:
            urn: Feature URN in format feature:wagon-slug:feature-slug or feature:wagon-slug.feature-slug

        Returns:
            Tuple of (wagon_slug, feature_slug)
        """
        if not urn or not urn.startswith("feature:"):
            return ("", "")

        # Remove 'feature:' prefix
        rest = urn.replace("feature:", "")

        # Try colon separator first (current format), then dot (legacy format)
        if ":" in rest:
            parts = rest.split(":", 1)
        elif "." in rest:
            parts = rest.split(".", 1)
        else:
            return ("", "")

        if len(parts) != 2:
            return ("", "")

        return (parts[0], parts[1])

    def _kebab_to_snake(self, text: str) -> str:
        """
        Convert kebab-case to snake_case (DOMAIN logic).

        Args:
            text: String in kebab-case (e.g., 'maintain-ux')

        Returns:
            String in snake_case (e.g., 'maintain_ux')
        """
        return text.replace("-", "_")

    def _find_implementation_paths(self, wagon_snake: str, feature_snake: str) -> List[str]:
        """
        Find existing implementation directories for a feature (INTEGRATION logic).

        Args:
            wagon_snake: Wagon name in snake_case
            feature_snake: Feature name in snake_case

        Returns:
            List of relative paths to existing implementation directories
        """
        paths = []

        # Check each potential implementation location
        locations = [
            self.repo_root / "python" / wagon_snake / feature_snake,
            self.repo_root / "lib" / wagon_snake / feature_snake,
            self.repo_root / "supabase" / "functions" / wagon_snake / feature_snake,
            self.repo_root / "packages" / wagon_snake / feature_snake
        ]

        for location in locations:
            if location.exists() and location.is_dir():
                # Store as relative path with trailing slash
                rel_path = location.relative_to(self.repo_root)
                paths.append(str(rel_path) + "/")

        return sorted(paths)

    # ========================================================================
    # PRESENTATION LAYER - Output Formatting
    # ========================================================================
    # CLI output formatting and user interaction
    # ========================================================================

    def _print_change_report(self, changes: List[Dict], preserved_drafts: List[str]):
        """
        Print detailed change report.

        Args:
            changes: List of change records
            preserved_drafts: List of preserved draft wagon slugs
        """
        if not changes and not preserved_drafts:
            return

        print("\n" + "=" * 60)
        print("DETAILED CHANGE REPORT")
        print("=" * 60)

        # Group changes by type
        new_wagons = [c for c in changes if c["type"] == "new"]
        updated_wagons = [c for c in changes if c["type"] == "updated"]

        # Report new wagons
        if new_wagons:
            print(f"\n🆕 NEW WAGONS ({len(new_wagons)}):")
            for change in sorted(new_wagons, key=lambda x: x["wagon"]):
                print(f"  • {change['wagon']}")

        # Report updated wagons with field changes
        if updated_wagons:
            print(f"\n🔄 UPDATED WAGONS ({len(updated_wagons)}):")
            for change in sorted(updated_wagons, key=lambda x: x["wagon"]):
                fields = ", ".join(change["fields"])
                print(f"  • {change['wagon']}")
                print(f"    Changed fields: {fields}")

        # Report unchanged wagons (synced but no changes)
        unchanged_count = len([c for c in changes if c["type"] == "updated" and not c["fields"]])
        if unchanged_count > 0:
            print(f"\n✓ UNCHANGED (synced, no changes): {unchanged_count} wagons")

        # Report preserved drafts
        if preserved_drafts:
            print(f"\n📝 PRESERVED DRAFT WAGONS ({len(preserved_drafts)}):")
            for slug in sorted(preserved_drafts):
                print(f"  • {slug}")

        print("\n" + "=" * 60)

    def _print_contract_change_report(self, changes: List[Dict]):
        """
        Print detailed change report for contracts.

        Args:
            changes: List of change records
        """
        if not changes:
            return

        print("\n" + "=" * 60)
        print("DETAILED CHANGE REPORT")
        print("=" * 60)

        # Group changes by type
        new_artifacts = [c for c in changes if c["type"] == "new"]
        updated_artifacts = [c for c in changes if c["type"] == "updated"]

        # Report new artifacts
        if new_artifacts:
            print(f"\n🆕 NEW ARTIFACTS ({len(new_artifacts)}):")
            for change in sorted(new_artifacts, key=lambda x: x["artifact"]):
                print(f"  • {change['artifact']}")

        # Report updated artifacts with field changes
        if updated_artifacts:
            print(f"\n🔄 UPDATED ARTIFACTS ({len(updated_artifacts)}):")
            for change in sorted(updated_artifacts, key=lambda x: x["artifact"]):
                fields = ", ".join(change["fields"])
                print(f"  • {change['artifact']}")
                print(f"    Changed fields: {fields}")

        print("\n" + "=" * 60)

    def _print_telemetry_change_report(self, changes: List[Dict]):
        """
        Print detailed change report for telemetry signals.

        Args:
            changes: List of change records
        """
        if not changes:
            return

        print("\n" + "=" * 60)
        print("DETAILED CHANGE REPORT")
        print("=" * 60)

        # Group changes by type
        new_signals = [c for c in changes if c["type"] == "new"]
        updated_signals = [c for c in changes if c["type"] == "updated"]

        # Report new signals
        if new_signals:
            print(f"\n🆕 NEW SIGNALS ({len(new_signals)}):")
            for change in sorted(new_signals, key=lambda x: x["signal"]):
                print(f"  • {change['signal']}")

        # Report updated signals with field changes
        if updated_signals:
            print(f"\n🔄 UPDATED SIGNALS ({len(updated_signals)}):")
            for change in sorted(updated_signals, key=lambda x: x["signal"]):
                fields = ", ".join(change["fields"])
                print(f"  • {change['signal']}")
                print(f"    Changed fields: {fields}")

        print("\n" + "=" * 60)

    # ========================================================================
    # INTEGRATION LAYER - File I/O & Source Scanning
    # ========================================================================
    # Reads/writes YAML files, scans directories for source files
    # ========================================================================

    def update_wagon_registry(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """
        Update plan/_wagons.yaml from wagon manifest files.

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)
            preview_only: Deprecated - use mode="check" instead

        Returns:
            Statistics about the update (includes has_changes flag for check mode)
        """
        # Backwards compatibility
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        print("📊 Analyzing wagon registry from manifest files...")

        # Load existing registry
        registry_path = self.plan_dir / "_wagons.yaml"
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_wagons = {w.get("wagon"): w for w in registry_data.get("wagons", [])}
        else:
            existing_wagons = {}

        # Scan for wagon manifests
        manifest_files = list(self.plan_dir.glob("*/_*.yaml"))
        manifest_files = [f for f in manifest_files if f.name != "_wagons.yaml"]

        stats = {
            "total_manifests": len(manifest_files),
            "updated": 0,
            "new": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        updated_wagons = self._scan_wagon_manifests(manifest_files, existing_wagons, stats)

        # Preserve draft wagons (those without manifests or with draft: true)
        preserved_drafts = self._preserve_orphan_wagons(
            existing_wagons, updated_wagons, stats
        )

        # Sort by wagon slug
        updated_wagons.sort(key=lambda w: w.get("wagon", ""))

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} wagons will be updated")
        print(f"  • {stats['new']} new wagons will be added")
        print(f"  • {stats['preserved_drafts']} draft wagons will be preserved")

        # Print detailed change report
        self._print_change_report(stats["changes"], preserved_drafts)

        # Use helper for confirm/apply
        output = {"wagons": updated_wagons}
        return self._confirm_and_apply(mode, "wagon", registry_path, output, stats)

    def _scan_wagon_manifests(
        self, manifest_files: List[Path], existing_wagons: Dict, stats: Dict
    ) -> List[Dict[str, Any]]:
        """Build a registry entry per wagon manifest, recording new/updated stats."""
        updated_wagons: List[Dict[str, Any]] = []
        for manifest_path in sorted(manifest_files):
            try:
                entry = self._build_wagon_entry(manifest_path)
                if entry is None:
                    continue

                slug = entry["wagon"]
                changed = (
                    self._detect_changes(slug, existing_wagons[slug], entry)
                    if slug in existing_wagons
                    else None
                )
                self._record_registry_change(
                    stats, "wagon", slug, changed, "all fields (new wagon)"
                )
                updated_wagons.append(entry)

            except Exception as e:
                print(f"  ❌ Error processing {manifest_path}: {e}")
        return updated_wagons

    def _build_wagon_entry(self, manifest_path: Path) -> Optional[Dict[str, Any]]:
        """Build one wagon registry entry. Returns None when the manifest has no slug."""
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        slug = manifest.get("wagon", "")
        if not slug:
            print(f"  ⚠️  Skipping {manifest_path}: no wagon slug found")
            return None

        return {
            "wagon": slug,
            "description": manifest.get("description", ""),
            "theme": manifest.get("theme", ""),
            "subject": manifest.get("subject", ""),
            "context": manifest.get("context", ""),
            "action": manifest.get("action", ""),
            "goal": manifest.get("goal", ""),
            "outcome": manifest.get("outcome", ""),
            "produce": manifest.get("produce", []),
            "consume": manifest.get("consume", []),
            "wmbt": manifest.get("wmbt", {}),
            "total": manifest.get("total", 0),
            "manifest": str(manifest_path.relative_to(self.repo_root)),
            "path": str(manifest_path.parent.relative_to(self.repo_root)) + "/"
        }

    def _preserve_orphan_wagons(
        self, existing_wagons: Dict, updated_wagons: List[Dict], stats: Dict
    ) -> List[str]:
        """Carry over draft/manifest-less wagons; returns the slugs preserved."""
        already_built = {w.get("wagon") for w in updated_wagons}
        preserved_drafts = []
        for slug, wagon in existing_wagons.items():
            if slug in already_built:
                continue
            has_no_manifest = not wagon.get("manifest") and not wagon.get("path")
            if wagon.get("draft", False) or has_no_manifest:
                updated_wagons.append(wagon)
                preserved_drafts.append(slug)
                stats["preserved_drafts"] += 1
        return preserved_drafts

    def check_wagon_registry_scoped(self, changed_files: List[str]) -> Dict[str, Any]:
        """PR-scoped registry drift check (wmbt:govern-lifecycle:E018).

        Validates only wagon sources that appear in the PR's changed-files list.
        If changed_files contains no wagon source paths, returns has_changes=False
        (trivial pass) regardless of any repo-wide aggregate drift.
        """
        wagon_source_pattern = re.compile(r"^plan/[^/]+/_[^/]+\.yaml$")
        aggregate_name = "_wagons.yaml"

        touched_sources = [
            f for f in changed_files
            if wagon_source_pattern.match(f) and not f.endswith(aggregate_name)
        ]

        if not touched_sources:
            print("✅ GT-002 scoped check: no wagon sources changed — trivial pass")
            return {"has_changes": False, "drifted_wagons": []}

        registry_path = self.plan_dir / "_wagons.yaml"
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f) or {}
            existing_wagons = {w.get("wagon"): w for w in registry_data.get("wagons", [])}
        else:
            existing_wagons = {}

        drifted: List[str] = []

        for rel_path in touched_sources:
            manifest_path = self.repo_root / rel_path
            if not manifest_path.exists():
                continue
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
            except Exception:
                continue

            slug = manifest.get("wagon", "")
            if not slug:
                continue

            current = existing_wagons.get(slug)
            if current is None:
                drifted.append(slug)
                continue

            if manifest.get("description", "") != current.get("description", ""):
                drifted.append(slug)

        if drifted:
            for slug in drifted:
                print(
                    f"❌ wagon:{slug} source changed but aggregate entry not updated — "
                    f"run: atdd registry update --scope wagon:{slug}"
                )
            return {"has_changes": True, "drifted_wagons": drifted}

        print(f"✅ GT-002 scoped check: {len(touched_sources)} wagon source(s) checked, all in sync")
        return {"has_changes": False, "drifted_wagons": []}

    def update_contract_registry(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """
        Update contracts/_artifacts.yaml from contract schema files.

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)
            preview_only: Deprecated - use mode="check" instead

        Returns:
            Statistics about the update (includes has_changes flag for check mode)
        """
        # Backwards compatibility
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        print("\n📊 Analyzing contract registry from schema files...")

        # Load existing registry
        registry_path = self.contracts_dir / "_artifacts.yaml"
        existing_artifacts = {}
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_artifacts = {a.get("id"): a for a in registry_data.get("artifacts", [])}

        stats = {
            "total_schemas": 0,
            "processed": 0,
            "updated": 0,
            "new": 0,
            "errors": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        # Scan for contract schemas
        schema_files = list(self.contracts_dir.glob("**/*.schema.json"))
        stats["total_schemas"] = len(schema_files)

        artifacts = self._scan_contract_schemas(schema_files, existing_artifacts, stats)

        # Preserve draft artifacts (path doesn't exist or draft: true)
        self._preserve_orphan_entries(existing_artifacts, artifacts, stats)

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} artifacts will be updated")
        print(f"  • {stats['new']} new artifacts will be added")
        print(f"  • {stats['preserved_drafts']} draft artifacts will be preserved")
        if stats["errors"] > 0:
            print(f"  ⚠️  {stats['errors']} errors encountered")

        # Print detailed change report
        self._print_contract_change_report(stats["changes"])

        # Use helper for confirm/apply
        output = {"artifacts": artifacts}
        return self._confirm_and_apply(mode, "contract", registry_path, output, stats)

    def _scan_contract_schemas(
        self, schema_files: List[Path], existing_artifacts: Dict, stats: Dict
    ) -> List[Dict[str, Any]]:
        """Build a registry entry per contract schema, recording new/updated stats."""
        artifacts: List[Dict[str, Any]] = []
        for schema_path in sorted(schema_files):
            try:
                artifact = self._build_artifact_entry(schema_path)
                artifact_id = artifact["id"]
                changed = (
                    self._detect_contract_changes(
                        artifact_id, existing_artifacts[artifact_id], artifact
                    )
                    if artifact_id in existing_artifacts
                    else None
                )
                self._record_registry_change(
                    stats, "artifact", artifact_id, changed, "all fields (new artifact)"
                )
                artifacts.append(artifact)
                stats["processed"] += 1

            except Exception as e:
                print(f"  ⚠️  Error processing {schema_path}: {e}")
                stats["errors"] += 1
        return artifacts

    def _build_artifact_entry(self, schema_path: Path) -> Dict[str, Any]:
        """Build one contract registry entry from a JSON schema file."""
        with open(schema_path) as f:
            schema = json.load(f)

        schema_id = schema.get("$id", "")
        metadata = schema.get("x-artifact-metadata", {})

        return {
            "id": schema_id,
            "urn": f"contract:{schema_id}",
            "version": schema.get("version", "1.0.0"),
            "title": schema.get("title", ""),
            "description": schema.get("description", ""),
            "path": str(schema_path.relative_to(self.repo_root)),
            "producer": metadata.get("producer", ""),
            "consumers": metadata.get("consumers", []),
        }

    def update_telemetry_registry(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """
        Update telemetry/_telemetry.yaml from telemetry signal files.

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)
            preview_only: Deprecated - use mode="check" instead

        Returns:
            Statistics about the update (includes has_changes flag for check mode)
        """
        # Backwards compatibility
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        print("\n📊 Analyzing telemetry registry from signal files...")

        # Load existing registry
        registry_path = self.telemetry_dir / "_telemetry.yaml"
        existing_signals = {}
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_signals = {s.get("id"): s for s in registry_data.get("signals", [])}

        stats = {
            "total_files": 0,
            "processed": 0,
            "updated": 0,
            "new": 0,
            "errors": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        # Scan for telemetry signal files (JSON or YAML)
        json_files = list(self.telemetry_dir.glob("**/*.json"))
        yaml_files = list(self.telemetry_dir.glob("**/*.yaml"))
        signal_files = [f for f in (json_files + yaml_files) if "_telemetry" not in f.name]

        stats["total_files"] = len(signal_files)

        signals = self._scan_telemetry_signals(signal_files, existing_signals, stats)

        # Preserve draft signals (path doesn't exist or draft: true)
        self._preserve_orphan_entries(existing_signals, signals, stats)

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} signals will be updated")
        print(f"  • {stats['new']} new signals will be added")
        print(f"  • {stats['preserved_drafts']} draft signals will be preserved")
        if stats["errors"] > 0:
            print(f"  ⚠️  {stats['errors']} errors encountered")

        # Print detailed change report
        self._print_telemetry_change_report(stats["changes"])

        # Use helper for confirm/apply
        output = {"signals": signals}
        return self._confirm_and_apply(mode, "telemetry", registry_path, output, stats)

    def _scan_telemetry_signals(
        self, signal_files: List[Path], existing_signals: Dict, stats: Dict
    ) -> List[Dict[str, Any]]:
        """Build a registry entry per telemetry signal, recording new/updated stats."""
        signals: List[Dict[str, Any]] = []
        for signal_path in sorted(signal_files):
            try:
                signal = self._build_signal_entry(signal_path)
                signal_id = signal["id"]
                changed = (
                    self._detect_telemetry_changes(
                        signal_id, existing_signals[signal_id], signal
                    )
                    if signal_id in existing_signals
                    else None
                )
                self._record_registry_change(
                    stats, "signal", signal_id, changed, "all fields (new signal)"
                )
                signals.append(signal)
                stats["processed"] += 1

            except Exception as e:
                print(f"  ⚠️  Error processing {signal_path}: {e}")
                stats["errors"] += 1
        return signals

    def _build_signal_entry(self, signal_path: Path) -> Dict[str, Any]:
        """Build one telemetry registry entry from a signal file (JSON or YAML)."""
        with open(signal_path) as f:
            if signal_path.suffix == ".json":
                signal_data = json.load(f)
            else:
                signal_data = yaml.safe_load(f)

        return {
            "id": signal_data.get("$id", signal_data.get("id", "")),
            "type": signal_data.get("type", "event"),
            "description": signal_data.get("description", ""),
            "path": str(signal_path.relative_to(self.repo_root)),
        }

    # Alias methods for unified API
    def build_planner(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """Build planner registry (alias for update_wagon_registry)."""
        # Backwards compatibility: preview_only=True maps to mode="check"
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        return self.update_wagon_registry(mode)

    def build_contracts(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """Build contracts registry (alias for update_contract_registry)."""
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        return self.update_contract_registry(mode)

    def build_telemetry(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """Build telemetry registry (alias for update_telemetry_registry)."""
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        return self.update_telemetry_registry(mode)

    def _normalize_test_code_field(self, field_value: Any) -> Dict[str, List[str]]:
        """
        Normalize test/code field to canonical structure.

        Train First-Class Spec v0.6 Section 5: Test/Code Field Typing Normalization
        - string -> {"backend": [string]}
        - list -> {"backend": list}
        - dict -> normalize each sub-field to list
        """
        if field_value is None:
            return {}

        if isinstance(field_value, str):
            return {"backend": [field_value]}
        elif isinstance(field_value, list):
            return {"backend": field_value}
        elif isinstance(field_value, dict):
            result = {}
            for key in ["backend", "frontend", "frontend_python"]:
                if key in field_value:
                    val = field_value[key]
                    result[key] = [val] if isinstance(val, str) else (val or [])
            return result
        return {}

    def _extract_wagons_from_participants(self, participants: List[str]) -> List[str]:
        """
        Extract wagon names from participants list.

        Train First-Class Spec v0.6 Section 4: Participants is Canonical Wagon Source
        """
        wagons = []
        for participant in participants:
            if isinstance(participant, str) and participant.startswith("wagon:"):
                wagon_name = participant.replace("wagon:", "")
                wagons.append(wagon_name)
        return wagons

    def _get_theme_key(self, theme_digit: str, theme_name: str) -> str:
        """Generate theme key like '0-commons' from digit and name."""
        return f"{theme_digit}-{theme_name}"

    def _get_category_key(self, theme_digit: str, category_digit: str, theme_name: str, category_name: str) -> str:
        """Generate category key like '00-commons-nominal' from digits and names."""
        return f"{theme_digit}{category_digit}-{theme_name}-{category_name}"

    def _index_trains_by_id(self, trains_list: List[Dict]) -> Dict[str, Dict]:
        """Index a flat list of train entries by train_id, skipping unidentified ones."""
        indexed = {}
        for train in trains_list:
            train_id = train.get("train_id")
            if train_id:
                indexed[train_id] = train
        return indexed

    def _flatten_nested_trains(self, trains_data: Dict) -> Dict[str, Dict]:
        """Flatten nested theme-category-grouped structure to dict by train_id."""
        if isinstance(trains_data, list):
            # Handle legacy flat list format
            return self._index_trains_by_id(trains_data)

        if not isinstance(trains_data, dict):
            return {}

        existing_trains: Dict[str, Dict] = {}
        for categories in trains_data.values():
            if not isinstance(categories, dict):
                continue
            for trains_list in categories.values():
                if isinstance(trains_list, list):
                    existing_trains.update(self._index_trains_by_id(trains_list))
        return existing_trains

    def build_trains(self, mode: str = "interactive") -> Dict[str, Any]:
        """
        Build trains registry from train manifest files.
        Scans plan/_trains/*.yaml files and builds plan/_trains.yaml.

        Train ID convention: NNXX-name where:
        - N = theme digit (0-9)
        - X = category digit (0=nominal, 1=error, 2=alternate, 3=exception)
        - XX = variation (01-99)
        - name = train slug

        Output format (per train.convention.yaml):
        trains:
          {digit}-{theme}:
            {theme_digit}{category_digit}-{theme}-{category}:
              - train_id: ...

        Train First-Class Spec v0.6 Normalization:
        - Section 1: Normalize file→path (deprecation)
        - Section 4: Extract wagons from participants
        - Section 5: Normalize test/code fields to {backend/frontend/frontend_python: []}

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)

        Returns:
            Statistics about the update (includes has_changes flag for check mode)
        """
        print("\n📊 Analyzing trains registry from manifest files...")

        # Set up paths
        trains_dir = self.plan_dir / "_trains"
        registry_path = self.plan_dir / "_trains.yaml"

        # Theme map merges built-in defaults with consumer overrides (#291).
        theme_map = get_theme_map(load_atdd_config(self.repo_root))
        existing_trains = self._load_existing_trains(registry_path)

        stats = {
            "total_manifests": 0,
            "processed": 0,
            "updated": 0,
            "new": 0,
            "errors": 0,
            "preserved_drafts": 0,
            "file_to_path_migrations": 0,
            "changes": []
        }

        if not trains_dir.exists():
            print(f"  ⚠️  No _trains/ directory found at {trains_dir}")
            return self._preserve_drafts_without_manifests(
                mode, registry_path, existing_trains, theme_map, stats
            )

        # Scan for train manifests
        manifest_files = [
            f for f in trains_dir.glob("*.yaml") if not f.name.startswith("_")
        ]
        stats["total_manifests"] = len(manifest_files)

        # Collect all train entries (flat list first, then group)
        all_train_entries = []
        for manifest_path in sorted(manifest_files):
            try:
                entry = self._process_train_manifest(
                    manifest_path, existing_trains, theme_map, stats
                )
            except Exception as e:
                print(f"  ❌ Error processing {manifest_path}: {e}")
                stats["errors"] += 1
                continue

            if entry is not None:
                all_train_entries.append(entry)
                stats["processed"] += 1

        self._preserve_orphan_draft_trains(
            existing_trains, all_train_entries, theme_map, stats
        )

        all_train_entries.sort(key=lambda t: t.get("train_id", ""))
        nested_trains = self._nest_train_entries(all_train_entries)
        self._print_trains_preview(stats, nested_trains)

        # Use helper for confirm/apply
        output = {"trains": nested_trains}
        return self._confirm_and_apply(mode, "trains", registry_path, output, stats)

    def _load_existing_trains(self, registry_path: Path) -> Dict[str, Dict]:
        """Load the existing trains registry, flattened to a dict keyed by train_id."""
        if not registry_path.exists():
            return {}
        with open(registry_path) as f:
            registry_data = yaml.safe_load(f)
            return self._flatten_nested_trains(registry_data.get("trains", {}))

    def _tag_train_grouping(self, train: Dict, train_id: str, theme_map: Dict) -> None:
        """Stamp theme/category grouping metadata onto an existing (draft) train entry."""
        theme_digit = train_id[0] if train_id and train_id[0].isdigit() else "0"
        category_digit = (
            train_id[1]
            if train_id and len(train_id) > 1 and train_id[1].isdigit()
            else "0"
        )
        train["_theme_digit"] = theme_digit
        train["_category_digit"] = category_digit
        train["_theme_name"] = theme_map.get(theme_digit, "unknown")
        train["_category_name"] = CATEGORY_MAP.get(category_digit, "unknown")

    def _nest_train_entries(self, entries: List[Dict]) -> Dict[str, Dict]:
        """Group entries into the nested {theme_key: {category_key: [train]}} output shape."""
        nested: Dict[str, Dict] = {}
        for entry in entries:
            theme_digit = entry.pop("_theme_digit", "0")
            category_digit = entry.pop("_category_digit", "0")
            theme_name = entry.pop("_theme_name", "unknown")
            category_name = entry.pop("_category_name", "unknown")

            theme_key = self._get_theme_key(theme_digit, theme_name)
            category_key = self._get_category_key(
                theme_digit, category_digit, theme_name, category_name
            )
            nested.setdefault(theme_key, {}).setdefault(category_key, []).append(entry)
        return nested

    def _preserve_drafts_without_manifests(
        self,
        mode: str,
        registry_path: Path,
        existing_trains: Dict,
        theme_map: Dict,
        stats: Dict,
    ) -> Dict[str, Any]:
        """No _trains/ directory: keep whatever drafts the registry already holds."""
        draft_entries = []
        for train_id, train in existing_trains.items():
            if train.get("draft", False):
                self._tag_train_grouping(train, train_id, theme_map)
                draft_entries.append(train)
                stats["preserved_drafts"] += 1

        if not stats["preserved_drafts"]:
            stats["has_changes"] = False
            return stats

        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['preserved_drafts']} draft trains will be preserved")
        output = {"trains": self._nest_train_entries(draft_entries)}
        return self._confirm_and_apply(mode, "trains", registry_path, output, stats)

    def _parse_train_grouping(self, train_id: str, theme_map: Dict) -> Dict[str, str]:
        """Derive theme/category grouping metadata from a manifest-declared train_id.

        Format: NNXX-name where N=theme digit, X=category digit.
        """
        grouping = {
            "_theme_digit": "",
            "_category_digit": "",
            "_theme_name": "",
            "_category_name": "",
        }
        if not (train_id and len(train_id) >= 2 and train_id[0].isdigit()):
            return grouping

        grouping["_theme_digit"] = train_id[0]
        grouping["_theme_name"] = theme_map.get(train_id[0], "unknown")
        if train_id[1].isdigit():
            grouping["_category_digit"] = train_id[1]
            grouping["_category_name"] = CATEGORY_MAP.get(train_id[1], "unknown")
        return grouping

    def _resolve_train_wagons(self, manifest: Dict, train_id: str) -> List[str]:
        """Participants are the canonical wagon source; an explicit list overrides them.

        Train First-Class Spec v0.6 Section 4.
        """
        wagons = self._extract_wagons_from_participants(manifest.get("participants", []))

        explicit_wagons = manifest.get("wagons", [])
        if not explicit_wagons:
            return wagons

        # Validate subset relationship before letting the explicit list win
        explicit_set = set(explicit_wagons)
        participant_set = set(wagons)
        if not explicit_set.issubset(participant_set) and participant_set:
            extra = explicit_set - participant_set
            warnings.warn(
                f"Train {train_id}: registry wagons {extra} not in YAML participants",
                UserWarning,
                stacklevel=2
            )
        return explicit_wagons

    def _build_train_entry(
        self, manifest: Dict, train_id: str, theme_map: Dict, stats: Dict
    ) -> Dict[str, Any]:
        """Build one registry entry from a train manifest (spec v0.6 normalization)."""
        # Section 1: Normalize file→path (deprecation)
        if manifest.get("file") and not manifest.get("path"):
            stats["file_to_path_migrations"] += 1
            warnings.warn(
                f"Train {train_id}: 'file' field is deprecated, migrating to 'path'",
                DeprecationWarning,
                stacklevel=2
            )

        entry = {
            "train_id": train_id,
            "description": manifest.get("description", manifest.get("title", "")),
            "path": f"plan/_trains/{train_id}.yaml",
            "wagons": self._resolve_train_wagons(manifest, train_id),
        }

        # Section 5: Normalize test/code fields, keeping them out when empty
        test_normalized = self._normalize_test_code_field(manifest.get("test"))
        code_normalized = self._normalize_test_code_field(manifest.get("code"))
        if test_normalized:
            entry["test"] = test_normalized
        if code_normalized:
            entry["code"] = code_normalized

        expectations = manifest.get("expectations")
        if expectations:
            entry["expectations"] = expectations

        # Store grouping metadata (stripped again when nesting the output)
        entry.update(self._parse_train_grouping(train_id, theme_map))
        return entry

    def _record_registry_change(
        self,
        stats: Dict,
        key: str,
        entity_id: str,
        changed_fields: Optional[List[str]],
        new_label: str,
    ) -> None:
        """Log a registry entry as new or updated, and bump the matching counter.

        ``changed_fields`` is None when the entity is absent from the existing
        registry (i.e. new); an empty list means present but unchanged.
        """
        if changed_fields is None:
            stats["new"] += 1
            stats["changes"].append({key: entity_id, "type": "new", "fields": [new_label]})
            return

        stats["updated"] += 1
        if changed_fields:
            stats["changes"].append({key: entity_id, "type": "updated", "fields": changed_fields})

    def _preserve_orphan_entries(
        self, existing: Dict, entries: List[Dict], stats: Dict, id_key: str = "id"
    ) -> None:
        """Carry over registry entries that are drafts or whose source file is gone."""
        already_built = {e.get(id_key) for e in entries}
        for entity_id, entity in existing.items():
            if entity_id in already_built:
                continue
            path_exists = entity.get("path") and (self.repo_root / entity.get("path")).exists()
            if entity.get("draft", False) or not path_exists:
                entries.append(entity)
                stats["preserved_drafts"] += 1

    def _detect_train_changes(self, old: Dict, entry: Dict) -> List[str]:
        """Fields that differ between the stored train entry and the rebuilt one."""
        return [
            field
            for field in ["description", "wagons", "path", "test", "code", "expectations"]
            if old.get(field) != entry.get(field)
        ]

    def _process_train_manifest(
        self, manifest_path: Path, existing_trains: Dict, theme_map: Dict, stats: Dict
    ) -> Optional[Dict[str, Any]]:
        """Load and normalize a single train manifest. Returns None when it is empty."""
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        if not manifest:
            print(f"  ⚠️  Skipping empty manifest: {manifest_path}")
            return None

        # Fall back to the filename (e.g. 0001-auth-session.yaml -> 0001-auth-session)
        train_id = manifest.get("train_id", manifest.get("train", "")) or manifest_path.stem

        entry = self._build_train_entry(manifest, train_id, theme_map, stats)
        changed = (
            self._detect_train_changes(existing_trains[train_id], entry)
            if train_id in existing_trains
            else None
        )
        self._record_registry_change(
            stats, "train", train_id, changed, "all fields (new train)"
        )
        return entry

    def _preserve_orphan_draft_trains(
        self, existing_trains: Dict, all_train_entries: List[Dict], theme_map: Dict, stats: Dict
    ) -> None:
        """Carry over registry trains that are drafts or have no manifest of their own."""
        already_built = {t.get("train_id") for t in all_train_entries}
        for train_id, train in existing_trains.items():
            if train_id in already_built:
                continue
            if train.get("draft", False) or not train.get("manifest"):
                self._tag_train_grouping(train, train_id, theme_map)
                all_train_entries.append(train)
                stats["preserved_drafts"] += 1

    def _print_trains_preview(self, stats: Dict, nested_trains: Dict) -> None:
        """Show what building the trains registry would change."""
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} trains will be updated")
        print(f"  • {stats['new']} new trains will be added")
        print(f"  • {stats['preserved_drafts']} draft trains will be preserved")
        print(f"  • Grouped into {len(nested_trains)} themes")
        if stats["file_to_path_migrations"] > 0:
            print(f"  ⚠️  {stats['file_to_path_migrations']} file→path migrations (deprecation)")
        if stats["errors"] > 0:
            print(f"  ⚠️  {stats['errors']} errors encountered")

    def _skip_empty_stub(self, kind: str, registry_path, items, stats) -> Optional[Dict[str, Any]]:
        """Do not (re)create a vestigial empty registry stub.

        The tech/test code-root registries (``supabase/_functions.yaml``, the
        root ``atdd/tester/_tests.yaml``) are extension-domain now, not core
        roots — under the extension-first model a runtime like Supabase lives in
        an extension workspace, not a core registry. When there is nothing to
        register, remove any existing *empty* stub (file + now-empty parent
        dirs) and skip the write instead of stamping a `functions: []` /
        `tests: []` placeholder into the repo. Returns a skip-result when it
        skips, else ``None`` (proceed with the normal write).
        """
        if items:
            return None
        try:
            if registry_path.exists():
                existing = yaml.safe_load(registry_path.read_text()) or {}
                if not any(existing.get(k) for k in ("tests", "functions", "implementations")):
                    registry_path.unlink()
                    d = registry_path.parent
                    while d != self.repo_root and d.exists() and not any(d.iterdir()):
                        d.rmdir()
                        d = d.parent
        except OSError as exc:
            _logger.debug("empty-stub cleanup skipped", extra={"kind": kind, "error": str(exc)})
        print(f"  (no {kind} artifacts — skipping; extension-domain registry not stubbed)")
        return {"registry": kind, "skipped": True, "stats": stats}

    def build_tester(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """
        Build tester registry from test files.
        Scans atdd/tester/**/*_test.py files for URNs and metadata.

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)
            preview_only: Deprecated - use mode="check" instead
        """
        # Backwards compatibility
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        print("\n📊 Analyzing tester registry from test files...")

        # Load existing registry
        registry_path = self.tester_dir / "_tests.yaml"
        existing_tests = {}
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_tests = {t.get("urn"): t for t in registry_data.get("tests", [])}

        tests = []
        stats = {
            "total_files": 0,
            "processed": 0,
            "updated": 0,
            "new": 0,
            "errors": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        # Scan for test files
        if self.tester_dir.exists():
            test_files = list(self.tester_dir.glob("**/*_test.py"))
            test_files.extend(list(self.tester_dir.glob("**/test_*.py")))
            test_files = [f for f in test_files if not f.name.startswith("_")]
            stats["total_files"] = len(test_files)

            for test_file in sorted(test_files):
                try:
                    with open(test_file) as f:
                        content = f.read()

                    urns = re.findall(r'URN:\s*(\S+)', content)
                    spec_urns = re.findall(r'Spec:\s*(\S+)', content)
                    acceptance_urns = re.findall(r'Acceptance:\s*(\S+)', content)

                    rel_path = test_file.relative_to(self.tester_dir)
                    wagon = rel_path.parts[0] if len(rel_path.parts) > 1 else "unknown"

                    for urn in urns:
                        test_entry = {
                            "urn": urn,
                            "file": str(test_file.relative_to(self.repo_root)),
                            "wagon": wagon
                        }

                        if spec_urns:
                            test_entry["spec_urn"] = spec_urns[0]
                        if acceptance_urns:
                            test_entry["acceptance_urn"] = acceptance_urns[0]

                        if urn in existing_tests:
                            stats["updated"] += 1
                        else:
                            stats["new"] += 1
                            stats["changes"].append({
                                "test": urn,
                                "type": "new",
                                "fields": ["all fields (new test)"]
                            })

                        tests.append(test_entry)
                        stats["processed"] += 1

                except Exception as e:
                    print(f"  ⚠️  Error processing {test_file}: {e}")
                    stats["errors"] += 1

        # Preserve draft tests (file doesn't exist or draft: true)
        for urn, test in existing_tests.items():
            is_draft = test.get("draft", False)
            file_exists = test.get("file") and (self.repo_root / test.get("file")).exists()
            if is_draft or not file_exists:
                if urn not in [t.get("urn") for t in tests]:
                    tests.append(test)
                    stats["preserved_drafts"] += 1

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} tests will be updated")
        print(f"  • {stats['new']} new tests will be added")
        print(f"  • {stats['preserved_drafts']} draft tests will be preserved")
        if stats["errors"] > 0:
            print(f"  ⚠️  {stats['errors']} errors encountered")

        # Use helper for confirm/apply
        skip = self._skip_empty_stub("tester", registry_path, tests, stats)
        if skip is not None:
            return skip
        output = {"tests": tests}
        return self._confirm_and_apply(mode, "tester", registry_path, output, stats)

    def build_coder(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """
        Build coder implementation registry from Python files.
        Scans python/**/*.py files for implementations.

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)
            preview_only: Deprecated - use mode="check" instead
        """
        # Backwards compatibility
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        print("\n📊 Analyzing coder registry from Python files...")

        # Load existing registry
        registry_path = self.python_dir / "_implementations.yaml"
        existing_impls = {}
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_impls = {i.get("urn"): i for i in registry_data.get("implementations", [])}

        implementations = []
        stats = {
            "total_files": 0,
            "processed": 0,
            "updated": 0,
            "new": 0,
            "errors": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        # Scan for Python implementation files
        if self.python_dir.exists():
            py_files = list(self.python_dir.glob("**/*.py"))
            py_files = [
                f for f in py_files
                if not f.name.startswith("_")
                and "__pycache__" not in str(f)
                and "/tests/" not in str(f)
                and "/test/" not in str(f)
                and not f.name.endswith("_test.py")
                and not f.name.startswith("test_")
            ]
            stats["total_files"] = len(py_files)

            for py_file in sorted(py_files):
                try:
                    with open(py_file) as f:
                        content = f.read()

                    spec_urns = re.findall(r'Spec:\s*(\S+)', content)
                    test_urns = re.findall(r'Test:\s*(\S+)', content)

                    rel_path = py_file.relative_to(self.python_dir)
                    parts = rel_path.parts

                    wagon = parts[0] if len(parts) > 0 else "unknown"
                    layer = "unknown"

                    if "domain" in str(py_file):
                        layer = "domain"
                    elif "application" in str(py_file):
                        layer = "application"
                    elif "integration" in str(py_file) or "infrastructure" in str(py_file):
                        layer = "integration"
                    elif "presentation" in str(py_file):
                        layer = "presentation"

                    component = py_file.stem
                    impl_urn = f"impl:{wagon}:{layer}:{component}:python"

                    impl_entry = {
                        "urn": impl_urn,
                        "file": str(py_file.relative_to(self.repo_root)),
                        "wagon": wagon,
                        "layer": layer,
                        "component_type": "entity",
                        "language": "python"
                    }

                    if spec_urns:
                        impl_entry["spec_urn"] = spec_urns[0]
                    if test_urns:
                        impl_entry["test_urn"] = test_urns[0]

                    if impl_urn in existing_impls:
                        stats["updated"] += 1
                    else:
                        stats["new"] += 1
                        stats["changes"].append({
                            "impl": impl_urn,
                            "type": "new",
                            "fields": ["all fields (new implementation)"]
                        })

                    implementations.append(impl_entry)
                    stats["processed"] += 1

                except Exception as e:
                    print(f"  ⚠️  Error processing {py_file}: {e}")
                    stats["errors"] += 1

        # Preserve draft implementations (file doesn't exist or draft: true)
        for urn, impl in existing_impls.items():
            is_draft = impl.get("draft", False)
            file_exists = impl.get("file") and (self.repo_root / impl.get("file")).exists()
            if is_draft or not file_exists:
                if urn not in [i.get("urn") for i in implementations]:
                    implementations.append(impl)
                    stats["preserved_drafts"] += 1

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} implementations will be updated")
        print(f"  • {stats['new']} new implementations will be added")
        print(f"  • {stats['preserved_drafts']} draft implementations will be preserved")
        if stats["errors"] > 0:
            print(f"  ⚠️  {stats['errors']} errors encountered")

        # Use helper for confirm/apply
        output = {"implementations": implementations}
        return self._confirm_and_apply(mode, "coder", registry_path, output, stats)

    def build_supabase(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """
        Build supabase functions registry.
        Scans supabase/functions/**/ for function directories.

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)
            preview_only: Deprecated - use mode="check" instead
        """
        # Backwards compatibility
        if preview_only is not None:
            mode = "check" if preview_only else "interactive"
        print("\n📊 Analyzing supabase registry from function files...")

        # Load existing registry
        registry_path = self.supabase_dir / "_functions.yaml"
        existing_funcs = {}
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_funcs = {fn.get("id"): fn for fn in registry_data.get("functions", [])}

        functions = []
        stats = {
            "total_dirs": 0,
            "processed": 0,
            "updated": 0,
            "new": 0,
            "errors": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        # Scan for function directories
        functions_dir = self.supabase_dir / "functions"
        if functions_dir.exists():
            func_dirs = [d for d in functions_dir.iterdir() if d.is_dir()]
            stats["total_dirs"] = len(func_dirs)

            for func_dir in sorted(func_dirs):
                try:
                    func_id = func_dir.name
                    index_file = func_dir / "index.ts"

                    if not index_file.exists():
                        continue

                    rel_path = str(index_file.relative_to(self.repo_root))

                    func_entry = {
                        "id": func_id,
                        "path": rel_path,
                        "description": f"Supabase function: {func_id}"
                    }

                    if func_id in existing_funcs:
                        stats["updated"] += 1
                    else:
                        stats["new"] += 1
                        stats["changes"].append({
                            "function": func_id,
                            "type": "new",
                            "fields": ["all fields (new function)"]
                        })

                    functions.append(func_entry)
                    stats["processed"] += 1

                except Exception as e:
                    print(f"  ⚠️  Error processing {func_dir}: {e}")
                    stats["errors"] += 1

        # Preserve draft functions (path doesn't exist or draft: true)
        for func_id, func in existing_funcs.items():
            is_draft = func.get("draft", False)
            path_exists = func.get("path") and (self.repo_root / func.get("path")).exists()
            if is_draft or not path_exists:
                if func_id not in [fn.get("id") for fn in functions]:
                    functions.append(func)
                    stats["preserved_drafts"] += 1

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} functions will be updated")
        print(f"  • {stats['new']} new functions will be added")
        print(f"  • {stats['preserved_drafts']} draft functions will be preserved")

        # Use helper for confirm/apply
        skip = self._skip_empty_stub("supabase", registry_path, functions, stats)
        if skip is not None:
            return skip
        output = {"functions": functions}
        return self._confirm_and_apply(mode, "supabase", registry_path, output, stats)

    def build_python_manifest(self, preview_only: bool = False) -> Dict[str, Any]:
        """
        Build python/_manifest.yaml from Python modules.
        Discovers Python modules and generates package configuration.

        Returns:
            Statistics about the manifest generation
        """
        print("\n📊 Building Python manifest from discovered modules...")

        # Check if python directory exists
        if not self.python_dir.exists():
            print("  ⚠️  No python/ directory found")
            return {"total_modules": 0, "manifest_created": False}

        # Discover Python modules
        modules = []
        for item in self.python_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('_'):
                if (item / '__init__.py').exists() or any(item.rglob('*.py')):
                    modules.append(item.name)

        modules = sorted(modules)

        stats = {
            "total_modules": len(modules),
            "manifest_created": False
        }

        # Generate manifest data structure
        manifest_data = {
            "project": {
                "name": "jel-extractor",
                "version": "0.1.0",
                "description": "Job Element Extractor - Knowledge graph construction from narrative materials",
                "requires_python": ">=3.10",
                "authors": [
                    {"name": "JEL Extractor Team"}
                ]
            },
            "dependencies": [
                "pydantic>=2.0",
                "pyyaml>=6.0",
                "openai>=1.0",
                "anthropic>=0.18.0"
            ],
            "dev_dependencies": [
                "pytest>=7.0",
                "pytest-cov>=4.0",
                "black>=23.0",
                "ruff>=0.1.0",
                "mypy>=1.0"
            ],
            "modules": modules,
            "test": {
                "testpaths": ["python"],
                "python_files": "test_*.py",
                "python_classes": "Test*",
                "python_functions": "test_*"
            },
            "formatting": {
                "line_length": 100,
                "target_version": "py310"
            }
        }

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['total_modules']} Python modules discovered")
        print(f"  • Modules: {', '.join(modules)}")

        if preview_only:
            print("\n⚠️  Preview mode - no changes applied")
            return stats

        # Ask for confirmation
        print("\n❓ Do you want to generate python/_manifest.yaml?")
        print("   Type 'yes' to confirm, or anything else to cancel:")
        response = input("   > ").strip().lower()

        if response != "yes":
            print("\n❌ Manifest generation cancelled by user")
            stats["cancelled"] = True
            return stats

        # Write manifest
        manifest_path = self.python_dir / "_manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        stats["manifest_created"] = True

        print(f"\n✅ Python manifest generated successfully!")
        print(f"  • Discovered {stats['total_modules']} modules")
        print(f"  • Modules: {', '.join(modules)}")
        print(f"  📝 Manifest: {manifest_path}")

        return stats

    def check(self) -> int:
        """Check all registry mirrors for drift without applying any changes.

        Convenience wrapper around build_all(mode="check") that returns an
        exit code (0 = no drift, 1 = drift detected), matching the GT-850
        gate contract (wmbt:govern-lifecycle:E021).

        Returns:
            0 if all mirrors are in sync, 1 if any drift is detected.
        """
        results = self.build_all(mode="check")
        has_drift = any(
            r.get("has_changes", False) or r.get("new", 0) > 0 or len(r.get("changes", [])) > 0
            for r in results.values()
            if isinstance(r, dict)
        )
        return 1 if has_drift else 0

    def _declared_code_roots(self) -> set:
        """Return the code-root keys the repo EXPLICITLY declares in config.

        Reads the optional ``code:`` block of ``.atdd/config.yaml`` and returns
        its keys verbatim. Unlike
        :func:`atdd.coach.utils.config.get_code_roots`, this does NOT merge the
        game-template ``DEFAULT_CODE_ROOTS`` (``python``/``supabase``/``web``):
        the registry build must materialize only roots the repo actually ships,
        never force the defaults into a repo that declares none — which is what
        leaves stray ``python/``/``supabase/`` stub dirs after every
        ``atdd pr`` / ``atdd registry update --apply`` (#984, sibling of #970).

        Returns:
            Set of declared code-root keys (e.g. ``{"toolkit"}``); empty when no
            ``code:`` block is declared.
        """
        config = load_atdd_config(self.repo_root)
        code = config.get("code") if isinstance(config, dict) else None
        return set(code.keys()) if isinstance(code, dict) else set()

    def build_all(self, mode: str = "interactive") -> Dict[str, Any]:
        """Build all registries.

        Code-root mirrors (``python``/``supabase``/``telemetry``) are gated on
        what the repo actually declares so the build never stubs the
        game-template ``DEFAULT_CODE_ROOTS`` into a repo that ships none of them
        (#984). The universal ATDD registries (plan/trains/contracts/tester) are
        always built — every ATDD repo has those artifacts.

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)
        """
        print("=" * 60)
        print("Unified Registry Builder - Synchronizing from source files")
        print("=" * 60)

        results = {
            "plan": self.build_planner(mode),
            "trains": self.build_trains(mode),
            "contracts": self.build_contracts(mode),
            "tester": self.build_tester(mode),
        }

        # Code-root-gated mirrors (#984): materialize a mirror only when the repo
        # declares that root in `.atdd/config.yaml` `code:` (or it already exists
        # on disk). Never force the game-template DEFAULT_CODE_ROOTS — or the
        # telemetry mirror — into a repo that ships none of them.
        declared = self._declared_code_roots()
        if "telemetry" in declared or self.telemetry_dir.exists():
            results["telemetry"] = self.build_telemetry(mode)
        if "python" in declared or self.python_dir.exists():
            results["coder"] = self.build_coder(mode)
        if "supabase" in declared or self.supabase_dir.exists():
            results["supabase"] = self.build_supabase(mode)

        print("\n" + "=" * 60)
        print("Registry Build Complete")
        print("=" * 60)

        return results

    def enrich_wagon_registry(self, preview_only: bool = False) -> Dict[str, Any]:
        """
        Enrich _wagons.yaml with features and simplified WMBT totals.

        SPEC-COACH-UTILS-0290: Add features section and simplify WMBT counts

        Adds features: list from wagon manifests and replaces detailed wmbt
        entries with just total: N field.

        Args:
            preview_only: If True, only show what would change without applying

        Returns:
            Statistics about the enrichment
        """
        print("\n📊 Enriching wagon registry with features and WMBT totals...")

        # Load existing registry
        registry_path = self.plan_dir / "_wagons.yaml"
        if not registry_path.exists():
            print("  ⚠️  No _wagons.yaml found")
            return {"total": 0, "enriched": 0}

        with open(registry_path) as f:
            registry_data = yaml.safe_load(f)

        wagons = registry_data.get("wagons", [])
        enriched_wagons = []
        stats = {
            "total": len(wagons),
            "enriched": 0,
            "with_features": 0,
            "wmbt_simplified": 0
        }

        for wagon_entry in wagons:
            slug = wagon_entry.get("wagon", "")

            # Load wagon manifest to get features and wmbt.total
            manifest_path = None
            if "manifest" in wagon_entry:
                manifest_path = self.repo_root / wagon_entry["manifest"]
            else:
                # Fallback: construct from slug
                dirname = slug.replace("-", "_")
                manifest_path = self.plan_dir / dirname / f"_{dirname}.yaml"

            enriched_entry = wagon_entry.copy()

            if manifest_path and manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        manifest = yaml.safe_load(f)

                    # Extract features from manifest (DOMAIN)
                    features = self._extract_features_from_manifest(manifest, slug)
                    enriched_entry["features"] = features
                    if features:
                        stats["with_features"] += 1

                    # Extract WMBT total from manifest (DOMAIN)
                    wmbt_total = self._extract_wmbt_total_from_manifest(manifest)

                    # Structure WMBT with total and coverage
                    if "wmbt" in enriched_entry and enriched_entry["wmbt"]:
                        stats["wmbt_simplified"] += 1
                    enriched_entry["wmbt"] = {
                        "total": wmbt_total,
                        "coverage": 0  # To be computed later
                    }

                    # Remove legacy root-level total field
                    if "total" in enriched_entry:
                        del enriched_entry["total"]

                    stats["enriched"] += 1

                except Exception as e:
                    print(f"  ⚠️  Error processing {slug}: {e}")
                    # Keep original entry if error
                    enriched_entry["features"] = []
                    enriched_entry["wmbt"] = {"total": 0, "coverage": 0}
                    if "total" in enriched_entry:
                        del enriched_entry["total"]
            else:
                # No manifest, add empty features and default wmbt
                enriched_entry["features"] = []
                enriched_entry["wmbt"] = {"total": wagon_entry.get("total", 0), "coverage": 0}
                # Remove legacy root-level total field
                if "total" in enriched_entry:
                    del enriched_entry["total"]

            enriched_wagons.append(enriched_entry)

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['enriched']} wagons will be enriched")
        print(f"  • {stats['with_features']} wagons have features")
        print(f"  • {stats['wmbt_simplified']} WMBT sections simplified")

        if preview_only:
            print("\n⚠️  Preview mode - no changes applied")
            return stats

        # Write enriched registry
        output = {"wagons": enriched_wagons}
        with open(registry_path, "w") as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"\n✅ Wagon registry enriched successfully!")
        print(f"  • Enriched {stats['enriched']} wagons")
        print(f"  • Added features to {stats['with_features']} wagons")
        print(f"  • Simplified {stats['wmbt_simplified']} WMBT sections")
        print(f"  📝 Registry: {registry_path}")

        return stats

    def update_feature_implementation_paths(self, preview_only: bool = False) -> Dict[str, Any]:
        """
        Update feature manifest files with implementation paths from filesystem.

        SPEC-COACH-UTILS-0291: Add implementation paths array to feature manifests

        Scans filesystem for implementation directories and adds paths array to
        each feature manifest at plan/{wagon_snake}/features/{feature_snake}.yaml

        Args:
            preview_only: If True, only show what would change without applying

        Returns:
            Statistics about the update
        """
        print("\n📊 Updating feature manifests with implementation paths...")

        # Find all feature manifest files
        feature_files = list(self.plan_dir.glob("*/features/*.yaml"))

        stats = {
            "total_features": len(feature_files),
            "updated": 0,
            "with_paths": 0,
            "errors": 0
        }

        for feature_file in sorted(feature_files):
            try:
                # Load feature manifest
                with open(feature_file) as f:
                    feature_data = yaml.safe_load(f)

                if not feature_data:
                    continue

                # Extract URN
                urn = feature_data.get("urn", "")
                if not urn:
                    continue

                # Parse URN to get wagon and feature slugs (DOMAIN)
                wagon_slug, feature_slug = self._parse_feature_urn(urn)
                if not wagon_slug or not feature_slug:
                    continue

                # Convert to snake_case for filesystem (DOMAIN)
                wagon_snake = self._kebab_to_snake(wagon_slug)
                feature_snake = self._kebab_to_snake(feature_slug)

                # Find existing implementation paths (INTEGRATION)
                impl_paths = self._find_implementation_paths(wagon_snake, feature_snake)

                # Add paths to feature data
                feature_data["paths"] = impl_paths
                if impl_paths:
                    stats["with_paths"] += 1

                if not preview_only:
                    # Write updated feature manifest
                    with open(feature_file, "w") as f:
                        yaml.dump(feature_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

                stats["updated"] += 1

            except Exception as e:
                print(f"  ⚠️  Error processing {feature_file}: {e}")
                stats["errors"] += 1

        # Show summary
        print(f"\n📋 SUMMARY:")
        print(f"  • {stats['updated']} features processed")
        print(f"  • {stats['with_paths']} features have implementations")
        print(f"  • {stats['total_features'] - stats['with_paths']} features have no implementations yet")
        if stats["errors"] > 0:
            print(f"  ⚠️  {stats['errors']} errors encountered")

        if preview_only:
            print("\n⚠️  Preview mode - no changes applied")
        else:
            print(f"\n✅ Feature manifests updated successfully!")

        return stats

    def update_all(self) -> Dict[str, Any]:
        """Update all registries (alias for backward compatibility)."""
        return self.build_all()


# Backward compatibility alias
RegistryUpdater = RegistryBuilder


def main(repo_root: Path):
    """Main entry point for registry builder."""
    builder = RegistryBuilder(repo_root)
    return builder.build_all()


if __name__ == "__main__":
    from atdd.coach.utils.repo import find_repo_root
    repo_root = find_repo_root()
    main(repo_root)

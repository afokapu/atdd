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
- telemetry/_signals.yaml from telemetry signals
- atdd/tester/_tests.yaml from test files
- python/_implementations.yaml from Python files
- supabase/_functions.yaml from function files

This command helps maintain coherence between source files and registries.
"""
import yaml
import json
import re
import ast
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Import URNBuilder for URN generation (following conventions)
try:
    from atdd.coach.utils.graph.urn import URNBuilder
except ImportError:
    # Fallback if URNBuilder not available
    class URNBuilder:
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
        """Load telemetry registry (telemetry/_signals.yaml)."""
        registry_path = self.telemetry_dir / "_signals.yaml"
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

        updated_wagons = []
        stats = {
            "total_manifests": len(manifest_files),
            "updated": 0,
            "new": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        for manifest_path in sorted(manifest_files):
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)

                slug = manifest.get("wagon", "")
                if not slug:
                    print(f"  ⚠️  Skipping {manifest_path}: no wagon slug found")
                    continue

                # Get relative paths
                wagon_dir = manifest_path.parent
                rel_manifest = str(manifest_path.relative_to(self.repo_root))
                rel_dir = str(wagon_dir.relative_to(self.repo_root)) + "/"

                # Build registry entry
                entry = {
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
                    "manifest": rel_manifest,
                    "path": rel_dir
                }

                # Check if updating or new
                if slug in existing_wagons:
                    stats["updated"] += 1
                    changes = self._detect_changes(slug, existing_wagons[slug], entry)
                    if changes:
                        stats["changes"].append({
                            "wagon": slug,
                            "type": "updated",
                            "fields": changes
                        })
                else:
                    stats["new"] += 1
                    stats["changes"].append({
                        "wagon": slug,
                        "type": "new",
                        "fields": ["all fields (new wagon)"]
                    })

                updated_wagons.append(entry)

            except Exception as e:
                print(f"  ❌ Error processing {manifest_path}: {e}")

        # Preserve draft wagons (those without manifests or with draft: true)
        preserved_drafts = []
        for slug, wagon in existing_wagons.items():
            is_draft = wagon.get("draft", False)
            has_no_manifest = not wagon.get("manifest") and not wagon.get("path")
            if is_draft or has_no_manifest:
                # Check if already added from manifest scan
                if slug not in [w.get("wagon") for w in updated_wagons]:
                    updated_wagons.append(wagon)
                    preserved_drafts.append(slug)
                    stats["preserved_drafts"] += 1

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

        artifacts = []
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

        for schema_path in sorted(schema_files):
            try:
                with open(schema_path) as f:
                    schema = json.load(f)

                # Extract metadata
                schema_id = schema.get("$id", "")
                version = schema.get("version", "1.0.0")
                title = schema.get("title", "")
                description = schema.get("description", "")
                metadata = schema.get("x-artifact-metadata", {})

                # Build artifact entry
                rel_path = str(schema_path.relative_to(self.repo_root))

                artifact_id = schema_id
                artifact = {
                    "id": artifact_id,
                    "urn": f"contract:{schema_id}",
                    "version": version,
                    "title": title,
                    "description": description,
                    "path": rel_path,
                    "producer": metadata.get("producer", ""),
                    "consumers": metadata.get("consumers", []),
                }

                # Track changes
                if artifact_id in existing_artifacts:
                    stats["updated"] += 1
                    changes = self._detect_contract_changes(artifact_id, existing_artifacts[artifact_id], artifact)
                    if changes:
                        stats["changes"].append({
                            "artifact": artifact_id,
                            "type": "updated",
                            "fields": changes
                        })
                else:
                    stats["new"] += 1
                    stats["changes"].append({
                        "artifact": artifact_id,
                        "type": "new",
                        "fields": ["all fields (new artifact)"]
                    })

                artifacts.append(artifact)
                stats["processed"] += 1

            except Exception as e:
                print(f"  ⚠️  Error processing {schema_path}: {e}")
                stats["errors"] += 1

        # Preserve draft artifacts (path doesn't exist or draft: true)
        for artifact_id, artifact in existing_artifacts.items():
            is_draft = artifact.get("draft", False)
            path_exists = artifact.get("path") and (self.repo_root / artifact.get("path")).exists()
            if is_draft or not path_exists:
                if artifact_id not in [a.get("id") for a in artifacts]:
                    artifacts.append(artifact)
                    stats["preserved_drafts"] += 1

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

    def update_telemetry_registry(self, mode: str = "interactive", preview_only: bool = None) -> Dict[str, Any]:
        """
        Update telemetry/_signals.yaml from telemetry signal files.

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
        registry_path = self.telemetry_dir / "_signals.yaml"
        existing_signals = {}
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_signals = {s.get("id"): s for s in registry_data.get("signals", [])}

        signals = []
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
        signal_files = [f for f in (json_files + yaml_files) if "_signals" not in f.name]

        stats["total_files"] = len(signal_files)

        for signal_path in sorted(signal_files):
            try:
                # Load signal file
                if signal_path.suffix == ".json":
                    with open(signal_path) as f:
                        signal_data = json.load(f)
                else:
                    with open(signal_path) as f:
                        signal_data = yaml.safe_load(f)

                # Extract metadata
                signal_id = signal_data.get("$id", signal_data.get("id", ""))
                signal_type = signal_data.get("type", "event")
                description = signal_data.get("description", "")

                # Build signal entry
                rel_path = str(signal_path.relative_to(self.repo_root))

                signal = {
                    "id": signal_id,
                    "type": signal_type,
                    "description": description,
                    "path": rel_path,
                }

                # Track changes
                if signal_id in existing_signals:
                    stats["updated"] += 1
                    changes = self._detect_telemetry_changes(signal_id, existing_signals[signal_id], signal)
                    if changes:
                        stats["changes"].append({
                            "signal": signal_id,
                            "type": "updated",
                            "fields": changes
                        })
                else:
                    stats["new"] += 1
                    stats["changes"].append({
                        "signal": signal_id,
                        "type": "new",
                        "fields": ["all fields (new signal)"]
                    })

                signals.append(signal)
                stats["processed"] += 1

            except Exception as e:
                print(f"  ⚠️  Error processing {signal_path}: {e}")
                stats["errors"] += 1

        # Preserve draft signals (path doesn't exist or draft: true)
        for signal_id, signal in existing_signals.items():
            is_draft = signal.get("draft", False)
            path_exists = signal.get("path") and (self.repo_root / signal.get("path")).exists()
            if is_draft or not path_exists:
                if signal_id not in [s.get("id") for s in signals]:
                    signals.append(signal)
                    stats["preserved_drafts"] += 1

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

    def build_trains(self, mode: str = "interactive") -> Dict[str, Any]:
        """
        Build trains registry from train manifest files.
        Scans plan/_trains/*.yaml files and builds plan/_trains.yaml.

        Train ID convention: NN-XX-name where:
        - NN = theme prefix (first 2 digits for grouping)
        - XX = category within theme
        - name = train slug

        Args:
            mode: "interactive" (prompt), "apply" (no prompt), or "check" (verify only)

        Returns:
            Statistics about the update (includes has_changes flag for check mode)
        """
        print("\n📊 Analyzing trains registry from manifest files...")

        # Set up paths
        trains_dir = self.plan_dir / "_trains"
        registry_path = self.plan_dir / "_trains.yaml"

        # Load existing registry
        existing_trains = {}
        if registry_path.exists():
            with open(registry_path) as f:
                registry_data = yaml.safe_load(f)
                existing_trains = {t.get("train_id"): t for t in registry_data.get("trains", [])}

        trains = []
        stats = {
            "total_manifests": 0,
            "processed": 0,
            "updated": 0,
            "new": 0,
            "errors": 0,
            "preserved_drafts": 0,
            "changes": []
        }

        # Check if trains directory exists
        if not trains_dir.exists():
            print(f"  ⚠️  No _trains/ directory found at {trains_dir}")
            # Still preserve existing drafts
            for train_id, train in existing_trains.items():
                if train.get("draft", False):
                    trains.append(train)
                    stats["preserved_drafts"] += 1

            if stats["preserved_drafts"] > 0:
                print(f"\n📋 PREVIEW:")
                print(f"  • {stats['preserved_drafts']} draft trains will be preserved")
                output = {"trains": trains}
                return self._confirm_and_apply(mode, "trains", registry_path, output, stats)

            stats["has_changes"] = False
            return stats

        # Scan for train manifests
        manifest_files = list(trains_dir.glob("*.yaml"))
        manifest_files = [f for f in manifest_files if not f.name.startswith("_")]
        stats["total_manifests"] = len(manifest_files)

        for manifest_path in sorted(manifest_files):
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)

                if not manifest:
                    print(f"  ⚠️  Skipping empty manifest: {manifest_path}")
                    continue

                train_id = manifest.get("train_id", manifest.get("train", ""))
                if not train_id:
                    # Try to infer from filename (e.g., 01-01-setup.yaml -> 01-01-setup)
                    train_id = manifest_path.stem

                # Parse theme from train_id (first 2 digits)
                theme = ""
                if len(train_id) >= 2 and train_id[:2].isdigit():
                    theme = train_id[:2]

                # Build train entry
                rel_manifest = str(manifest_path.relative_to(self.repo_root))

                entry = {
                    "train_id": train_id,
                    "theme": theme,
                    "title": manifest.get("title", manifest.get("description", "")),
                    "description": manifest.get("description", ""),
                    "wagons": manifest.get("wagons", []),
                    "status": manifest.get("status", "planned"),
                    "manifest": rel_manifest
                }

                # Check if updating or new
                if train_id in existing_trains:
                    stats["updated"] += 1
                    # Check for field changes
                    old = existing_trains[train_id]
                    changed_fields = []
                    for field in ["title", "description", "wagons", "status", "theme"]:
                        if old.get(field) != entry.get(field):
                            changed_fields.append(field)
                    if changed_fields:
                        stats["changes"].append({
                            "train": train_id,
                            "type": "updated",
                            "fields": changed_fields
                        })
                else:
                    stats["new"] += 1
                    stats["changes"].append({
                        "train": train_id,
                        "type": "new",
                        "fields": ["all fields (new train)"]
                    })

                trains.append(entry)
                stats["processed"] += 1

            except Exception as e:
                print(f"  ❌ Error processing {manifest_path}: {e}")
                stats["errors"] += 1

        # Preserve draft trains (those without manifests or with draft: true)
        for train_id, train in existing_trains.items():
            is_draft = train.get("draft", False)
            has_no_manifest = not train.get("manifest")
            if is_draft or has_no_manifest:
                if train_id not in [t.get("train_id") for t in trains]:
                    trains.append(train)
                    stats["preserved_drafts"] += 1

        # Sort by train_id
        trains.sort(key=lambda t: t.get("train_id", ""))

        # Show preview
        print(f"\n📋 PREVIEW:")
        print(f"  • {stats['updated']} trains will be updated")
        print(f"  • {stats['new']} new trains will be added")
        print(f"  • {stats['preserved_drafts']} draft trains will be preserved")
        if stats["errors"] > 0:
            print(f"  ⚠️  {stats['errors']} errors encountered")

        # Use helper for confirm/apply
        output = {"trains": trains}
        return self._confirm_and_apply(mode, "trains", registry_path, output, stats)

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

    def build_all(self, mode: str = "interactive") -> Dict[str, Any]:
        """Build all registries.

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
            "telemetry": self.build_telemetry(mode),
            "tester": self.build_tester(mode),
            "coder": self.build_coder(mode),
            "supabase": self.build_supabase(mode)
        }

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

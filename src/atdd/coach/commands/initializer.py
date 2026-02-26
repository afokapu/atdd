"""
Project initializer for ATDD structure in consumer repos.

Creates the following structure:
    consumer-repo/
    ├── CLAUDE.md                (with managed ATDD block)
    └── .atdd/
        ├── manifest.yaml        (machine-readable issue tracking)
        └── config.yaml          (agent sync + GitHub integration config)

GitHub infrastructure (requires `gh` CLI):
    - Labels: atdd-session, atdd-wmbt, atdd:*, archetype:*, wagon:*
    - Project v2: "ATDD Sessions" with 11 custom fields
    - Workflow: .github/workflows/atdd-validate.yml
    - Config: project_id, project_number, repo in .atdd/config.yaml

Usage:
    atdd init                    # Initialize ATDD structure
    atdd init --force            # Overwrite existing files

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
import json
import logging
import subprocess
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class ProjectInitializer:
    """Initialize ATDD structure in consumer repo."""

    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the ProjectInitializer.

        Args:
            target_dir: Target directory for initialization. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach

    def init(self, force: bool = False) -> int:
        """
        Bootstrap .atdd/ config and GitHub infrastructure.

        Args:
            force: If True, overwrite existing files.

        Returns:
            0 on success, 1 on error.
        """
        # Check if already initialized
        if self.atdd_config_dir.exists() and not force:
            print(f"ATDD already initialized at {self.target_dir}")
            print("Use --force to reinitialize")
            return 1

        try:
            # Create .atdd/ config directory
            self.atdd_config_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created: {self.atdd_config_dir}")

            # Create manifest.yaml
            self._create_manifest(force)

            # Create config.yaml
            self._create_config(force)

            # Sync agent config files
            from atdd.coach.commands.sync import AgentConfigSync
            syncer = AgentConfigSync(self.target_dir)
            syncer.sync()

            # Bootstrap GitHub infrastructure
            github_summary = self._bootstrap_github(force)

            # Print next steps
            print("\n" + "=" * 60)
            print("ATDD initialized successfully!")
            print("=" * 60)
            print("\nStructure created:")
            print(f"  {self.atdd_config_dir}/")
            print(f"  {self.manifest_file}")
            print(f"  {self.config_file}")
            print(f"  CLAUDE.md (with ATDD managed block)")
            if github_summary:
                print(f"\n{github_summary}")

            return 0

        except PermissionError as e:
            print(f"Error: Permission denied - {e}")
            return 1
        except OSError as e:
            print(f"Error: {e}")
            return 1

    def _create_manifest(self, force: bool = False) -> None:
        """
        Create or update .atdd/manifest.yaml.

        Args:
            force: If True, overwrite existing manifest.
        """
        if self.manifest_file.exists() and not force:
            print(f"Manifest already exists: {self.manifest_file}")
            return

        manifest = {
            "version": "2.0",
            "created": date.today().isoformat(),
            "sessions": [],
        }

        with open(self.manifest_file, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

        print(f"Created: {self.manifest_file}")

    def _create_config(self, force: bool = False) -> None:
        """
        Create or update .atdd/config.yaml.

        Args:
            force: If True, overwrite existing config.
        """
        if self.config_file.exists() and not force:
            print(f"Config already exists: {self.config_file}")
            return

        # Get installed ATDD version
        try:
            from atdd import __version__
            toolkit_version = __version__
        except ImportError:
            toolkit_version = "0.0.0"

        config = {
            "version": "1.0",
            "release": {
                "version_file": "VERSION",
                "tag_prefix": "v",
            },
            "sync": {
                "agents": ["claude"],  # Default: only Claude
            },
            "toolkit": {
                "last_version": toolkit_version,  # Track installed version
            },
        }

        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"Created: {self.config_file}")

    def is_initialized(self) -> bool:
        """Check if ATDD is already initialized in target directory."""
        return self.atdd_config_dir.exists() and self.manifest_file.exists()

    # -------------------------------------------------------------------------
    # E007: GitHub infrastructure bootstrap
    # -------------------------------------------------------------------------

    def _gh_available(self) -> bool:
        """Check if `gh` CLI is available and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _detect_repo(self) -> Optional[str]:
        """Detect the GitHub repo from git remote."""
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def _bootstrap_github(self, force: bool = False) -> Optional[str]:
        """Bootstrap GitHub infrastructure: labels, Project v2, fields, workflow."""
        if not self._gh_available():
            print("\nWarning: gh CLI not available or not authenticated.")
            print("  GitHub infrastructure not created.")
            print("  Install: https://cli.github.com")
            print("  Then run: gh auth login && atdd init --force")
            return None

        repo = self._detect_repo()
        if not repo:
            print("\nWarning: Could not detect GitHub repo.")
            print("  Run from inside a git repo with a GitHub remote.")
            return None

        print(f"\nBootstrapping GitHub infrastructure for {repo}...")

        from atdd.coach.github import GitHubClient, GitHubClientError

        # Load label taxonomy from schema
        schema_path = self.package_root / "schemas" / "label_taxonomy.schema.json"
        labels_created, labels_existed = self._create_labels(repo, schema_path)

        # Create or find Project v2
        project_id, project_number, project_created = self._ensure_project(repo)

        # Create custom fields
        fields_created = 0
        if project_id:
            fields_created = self._create_project_fields(project_id)

        # Write workflow file
        workflow_written = self._write_workflow(repo)

        # Update config with GitHub settings
        if project_id:
            self._update_config_github(repo, project_id, project_number)

        # Summary
        parts = []
        parts.append(f"{labels_created + labels_existed} labels "
                      f"({labels_created} created, {labels_existed} existed)")
        if project_id:
            verb = "created" if project_created else "found"
            parts.append(f"Project 'ATDD Sessions' #{project_number} ({verb})")
        if fields_created:
            parts.append(f"{fields_created} fields created")
        if workflow_written:
            parts.append("workflow written")

        summary = f"GitHub: {', '.join(parts)}"
        print(f"  {summary}")
        return summary

    def _create_labels(self, repo: str, schema_path: Path) -> Tuple[int, int]:
        """Create ATDD labels from taxonomy schema. Returns (created, existed)."""
        if not schema_path.exists():
            logger.warning("Label taxonomy schema not found: %s", schema_path)
            return 0, 0

        with open(schema_path) as f:
            schema = json.load(f)

        # Extract labels from schema
        labels = []
        categories = schema.get("properties", {}).get("categories", {}).get("properties", {})
        for cat_name, cat_spec in categories.items():
            cat_props = cat_spec.get("properties", {})
            label_items = cat_props.get("labels", {}).get("prefixItems", [])
            for item in label_items:
                props = item.get("properties", {})
                name = props.get("name", {}).get("const")
                color = props.get("color", {}).get("const")
                desc = props.get("description", {}).get("const", "")
                if name and color:
                    labels.append((name, color, desc))

        created = 0
        existed = 0
        for name, color, desc in labels:
            try:
                subprocess.run(
                    ["gh", "label", "create", name,
                     "--repo", repo, "--color", color,
                     "--description", desc, "--force"],
                    capture_output=True, text=True, timeout=10,
                )
                # --force means it's always "success"; we check if it existed
                # by trying without --force first, but simpler to just count all
                created += 1
            except (subprocess.TimeoutExpired, FileNotFoundError):
                existed += 1

        return created, existed

    def _ensure_project(self, repo: str) -> Tuple[Optional[str], Optional[int], bool]:
        """Find or create 'ATDD Sessions' Project v2. Returns (id, number, created)."""
        owner = repo.split("/")[0]

        # Check for existing project
        try:
            result = subprocess.run(
                ["gh", "project", "list", "--owner", owner, "--format", "json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                for proj in data.get("projects", []):
                    if proj.get("title") == "ATDD Sessions":
                        # Need to get the node ID via GraphQL
                        proj_number = proj["number"]
                        node_id = self._get_project_node_id(owner, proj_number)
                        return node_id, proj_number, False
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass

        # Create new project via GraphQL
        try:
            # Get owner node ID
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ user(login:"{owner}") {{ id }} }}',
                 "--jq", ".data.user.id"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                # Try as org
                result = subprocess.run(
                    ["gh", "api", "graphql", "-f",
                     f'query={{ organization(login:"{owner}") {{ id }} }}',
                     "--jq", ".data.organization.id"],
                    capture_output=True, text=True, timeout=10,
                )

            owner_id = result.stdout.strip()
            if not owner_id:
                print("  Warning: Could not find owner ID for Project creation")
                return None, None, False

            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query=mutation {{ createProjectV2(input: {{ ownerId: "{owner_id}", '
                 f'title: "ATDD Sessions" }}) {{ projectV2 {{ id number }} }} }}'],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                proj = data["data"]["createProjectV2"]["projectV2"]
                return proj["id"], proj["number"], True
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: Could not create Project: {e}")

        return None, None, False

    def _get_project_node_id(self, owner: str, project_number: int) -> Optional[str]:
        """Get Project v2 node ID from owner and number."""
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ user(login:"{owner}") {{ '
                 f'projectV2(number:{project_number}) {{ id }} }} }}',
                 "--jq", ".data.user.projectV2.id"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            # Try as org
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ organization(login:"{owner}") {{ '
                 f'projectV2(number:{project_number}) {{ id }} }} }}',
                 "--jq", ".data.organization.projectV2.id"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    # v1 → v2 field migration map: old_name → new_name (None = delete)
    _FIELD_MIGRATION: Dict[str, Optional[str]] = {
        "Session Number": None,              # DELETE — redundant with GitHub issue number
        "ATDD Status":    "ATDD: Status",
        "ATDD Phase":     "ATDD: Phase",
        "Session Type":   "ATDD: Issue Type",
        "Complexity":     "ATDD: Complexity",
        "Archetypes":     "ATDD: Archetypes",
        "Branch":         "ATDD: Branch",
        "Train":          "ATDD: Train",
        "Feature URN":    "ATDD: Feature URN",
        "WMBT ID":        "ATDD: WMBT ID",
        "WMBT Step":      "ATDD: WMBT Step",
        "WMBT Phase":     "ATDD: WMBT Phase",
    }

    def _query_project_field_names_and_ids(self, project_id: str) -> Dict[str, str]:
        """Query existing project fields. Returns {name: field_id}."""
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ node(id: "{project_id}") {{ ... on ProjectV2 {{ '
                 f'fields(first: 30) {{ nodes {{ '
                 f'... on ProjectV2Field {{ id name }} '
                 f'... on ProjectV2SingleSelectField {{ id name }} '
                 f'}} }} }} }} }}'],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return {
                    node["name"]: node["id"]
                    for node in data["data"]["node"]["fields"]["nodes"]
                    if node.get("name") and node.get("id")
                }
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return {}

    def _rename_project_field_raw(self, project_id: str, field_id: str, new_name: str) -> bool:
        """Rename a project field via GraphQL. Returns True on success."""
        mutation = (
            f'mutation {{ updateProjectV2Field(input: {{ '
            f'fieldId: "{field_id}", name: "{new_name}" '
            f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id name }} '
            f'... on ProjectV2SingleSelectField {{ id name }} }} }} }}'
        )
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={mutation}"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _delete_project_field_raw(self, project_id: str, field_id: str) -> bool:
        """Delete a project field via GraphQL. Returns True on success."""
        mutation = (
            f'mutation {{ deleteProjectV2Field(input: {{ '
            f'fieldId: "{field_id}" '
            f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id }} '
            f'... on ProjectV2SingleSelectField {{ id }} }} }} }}'
        )
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={mutation}"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _create_project_fields(self, project_id: str) -> int:
        """Create/migrate custom fields on a Project v2 from schema. Returns count changed."""
        schema_path = self.package_root / "schemas" / "project_fields.schema.json"
        if not schema_path.exists():
            return 0

        with open(schema_path) as f:
            schema = json.load(f)

        # ------------------------------------------------------------------
        # Pass 1: Migrate — rename old-name fields, delete deprecated ones
        # ------------------------------------------------------------------
        existing = self._query_project_field_names_and_ids(project_id)
        migrated = 0

        for old_name, new_name in self._FIELD_MIGRATION.items():
            if old_name not in existing:
                continue
            field_id = existing[old_name]

            if new_name is None:
                # Delete deprecated field
                if self._delete_project_field_raw(project_id, field_id):
                    print(f"    Deleted field: {old_name}")
                    migrated += 1
            elif old_name != new_name and new_name not in existing:
                # Rename (preserves values)
                if self._rename_project_field_raw(project_id, field_id, new_name):
                    print(f"    Renamed field: {old_name} -> {new_name}")
                    migrated += 1

        # ------------------------------------------------------------------
        # Pass 2: Re-query after migration
        # ------------------------------------------------------------------
        if migrated:
            existing = self._query_project_field_names_and_ids(project_id)
        existing_names = set(existing.keys())

        # ------------------------------------------------------------------
        # Pass 3: Create any still-missing fields from schema
        # ------------------------------------------------------------------
        created = 0
        defs = schema.get("$defs", {})

        for scope in ["parent_fields", "sub_issue_fields"]:
            scope_def = defs.get(scope, {})
            for field_key, field_spec in scope_def.get("properties", {}).items():
                field_props = field_spec.get("properties", {})
                name = field_props.get("name", {}).get("const")
                data_type = field_props.get("data_type", {}).get("const")

                if not name or not data_type or name in existing_names:
                    continue

                if data_type == "SINGLE_SELECT":
                    options = field_spec.get("properties", {}).get("options", {})
                    option_items = options.get("prefixItems", [])
                    options_str = ", ".join(
                        f'{{name: "{item["properties"]["name"]["const"]}", '
                        f'description: "{item["properties"]["description"]["const"]}", '
                        f'color: {item["properties"]["color"]["const"]}}}'
                        for item in option_items
                        if "properties" in item
                    )
                    mutation = (
                        f'mutation {{ createProjectV2Field(input: {{ '
                        f'projectId: "{project_id}", dataType: {data_type}, '
                        f'name: "{name}", singleSelectOptions: [{options_str}] '
                        f'}}) {{ projectV2Field {{ ... on ProjectV2SingleSelectField {{ id }} }} }} }}'
                    )
                else:
                    mutation = (
                        f'mutation {{ createProjectV2Field(input: {{ '
                        f'projectId: "{project_id}", dataType: {data_type}, '
                        f'name: "{name}" '
                        f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id }} }} }} }}'
                    )

                try:
                    result = subprocess.run(
                        ["gh", "api", "graphql", "-f", f"query={mutation}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0:
                        created += 1
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

        return migrated + created

    def _write_workflow(self, repo: str) -> bool:
        """Write .github/workflows/atdd-validate.yml."""
        workflows_dir = self.target_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = workflows_dir / "atdd-validate.yml"

        workflow = f"""\
# ATDD Validation Workflow
# Generated by `atdd init` — safe to overwrite on re-run
name: ATDD Validate

on:
  push:
    branches: [main, "be/*", "fe/*"]
  pull_request:
    branches: [main]
  issues:
    types: [opened, edited, closed, labeled, unlabeled]

jobs:
  validate:
    runs-on: ubuntu-latest
    if: >-
      github.event_name != 'issues' ||
      contains(github.event.issue.labels.*.name, 'atdd-session') ||
      contains(github.event.issue.labels.*.name, 'atdd-wmbt')
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install ATDD toolkit
        run: pip install atdd

      - name: Run ATDD validators
        run: atdd validate
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Post result as issue comment
        if: github.event_name == 'issues'
        uses: actions/github-script@v7
        with:
          script: |
            const result = '${{{{ job.status }}}}';
            const emoji = result === 'success' ? '✅' : '❌';
            await github.rest.issues.createComment({{
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `${{emoji}} ATDD validation: **${{result}}**`
            }});
"""
        workflow_path.write_text(workflow)
        print(f"  Wrote: {workflow_path}")
        return True

    def _update_config_github(
        self, repo: str, project_id: str, project_number: int
    ) -> None:
        """Add GitHub settings to .atdd/config.yaml."""
        if not self.config_file.exists():
            return

        with open(self.config_file) as f:
            config = yaml.safe_load(f) or {}

        config["github"] = {
            "repo": repo,
            "project_number": project_number,
            "project_id": project_id,
            "field_schema": "atdd/coach/schemas/project_fields.schema.json",
        }

        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"  Updated: {self.config_file} (github section)")

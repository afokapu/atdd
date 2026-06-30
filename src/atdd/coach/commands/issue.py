"""
Issue management for ATDD tracking via GitHub Issues.

Creates GitHub Issues with Project v2 custom fields and WMBT sub-issues.
Requires `gh` CLI authenticated with `project` scope.

Usage:
    atdd new my-feature                            # Create GitHub issue + WMBT sub-issues
    atdd new my-feature --type migration            # Specify issue type
    atdd list                                      # List all issues
    atdd archive 11                                # Archive issue
    atdd update 11 --status RED                    # Update issue fields
    atdd close-wmbt 11 D005                        # Close WMBT sub-issue

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
import json
import logging
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple

import yaml

logger = logging.getLogger(__name__)

# Literal placeholder splice point in PARENT-ISSUE-TEMPLATE.md (Phase 2 of #682)
# — `atdd issue <slug>` replaces it with `build_architecture_context_for_wagon`
# output at creation time. Kept as a module constant so both the template and
# the splice site stay in lock-step.
GRAPH_CONTEXT_PLACEHOLDER = "(graph context will be injected at creation by atdd issue <slug>)"
GRAPH_CONTEXT_UNAVAILABLE = (
    "(graph unavailable — assign wagon in `plan/<slug>/_<slug>.yaml`, then re-run "
    "`atdd issue <N> --refresh-graph`)"
)

# Issue type → conventional commit / branch prefix mapping.
# Used by `atdd new` (title prefix) and `atdd branch` (worktree prefix).
TYPE_TO_PREFIX = {
    "implementation": "feat",
    "migration": "feat",
    "refactor": "refactor",
    "analysis": "chore",
    "planning": "chore",
    "cleanup": "chore",
    "tracking": "chore",
}

# Allowed branch prefixes (derived from TYPE_TO_PREFIX values + fix, docs, devops).
ALLOWED_BRANCH_PREFIXES = ("feat", "fix", "refactor", "chore", "docs", "devops")

# Step code to step name mapping
STEP_CODES = {
    "D": "Define",
    "L": "Locate",
    "P": "Prepare",
    "C": "Confirm",
    "E": "Execute",
    "M": "Monitor",
    "Y": "Modify",
    "R": "Resolve",
    "K": "Conclude",
}

# The CLI verb that registers a new parent issue. Manifest-commit failures on
# this path must fail loudly (#738) — a "success" with an unregistered issue is
# silently wrong. Other manifest verbs (status mirroring) stay tolerant.
_MANIFEST_REGISTRATION_VERB = "atdd issue"

# Archetype-specific gate test rows for the Validation table.
# Each entry: (gate_id, phase, command, validator_path)
ARCHETYPE_GATES = {
    "be": [
        ("GT-010", "implementation", "atdd validate coder", "src/atdd/coder/validators/test_python_architecture.py"),
        ("GT-011", "implementation", "atdd validate coder", "src/atdd/coder/validators/test_import_boundaries.py"),
    ],
    "fe": [
        ("GT-020", "implementation", "atdd validate coder", "src/atdd/coder/validators/test_typescript_architecture.py"),
        ("GT-021", "implementation", "atdd validate coder", "src/atdd/coder/validators/test_design_system_compliance.py"),
    ],
    "contracts": [
        ("GT-030", "tester", "atdd validate tester", "src/atdd/tester/validators/test_contract_schema_compliance.py"),
    ],
    "wmbt": [
        ("GT-040", "planner", "atdd validate planner", "src/atdd/planner/validators/test_wmbt_consistency.py"),
    ],
    "wagon": [
        ("GT-050", "planner", "atdd validate planner", "src/atdd/planner/validators/test_wagon_urn_chain.py"),
    ],
    "train": [
        ("GT-060", "planner", "atdd validate planner", "src/atdd/planner/validators/test_train_validation.py"),
    ],
    "db": [
        ("GT-070", "implementation", "supabase db push --dry-run", "supabase/migrations/"),
    ],
    "migrations": [
        ("GT-071", "implementation", "supabase db push --dry-run", "supabase/migrations/"),
    ],
    "telemetry": [
        ("GT-080", "tester", "atdd validate tester", "src/atdd/tester/validators/test_telemetry_validation.py"),
    ],
    "coach": [
        ("GT-090", "implementation", "atdd validate coach", "src/atdd/coach/validators/test_issue_validation.py"),
        ("GT-091", "implementation", "atdd validate coach", "src/atdd/coach/validators/test_registry.py"),
    ],
}


# E019: module-level placeholder — allows `patch("atdd.coach.commands.issue.GitHubClient", ...)`
# in unit tests. Actual construction uses `globals().get('GitHubClient') or _gh.GitHubClient`
# so that tests patching either `issue.GitHubClient` OR `atdd.coach.github.GitHubClient` work.
GitHubClient = None  # type: ignore


class IssueBodyComplianceError(Exception):
    """Raised when an issue body fails the local --check gate before publishing."""


class IssueBodyCheckResult:
    """Result of IssueBodyChecker.check()."""

    def __init__(self, passed: bool, errors: list) -> None:
        self.passed = passed
        self.errors = errors


class IssueBodyChecker:
    """Validate an issue body against required-section rules before publishing.

    Checks that ``### Graph Context`` and ``### Mirror Across Agents`` are
    present and that the Graph Context placeholder has been replaced.  Deliberately
    does NOT check H2 template sections — those are editorial, not publication gates.
    """

    def check(self, body: str) -> IssueBodyCheckResult:
        from atdd.coach.commands.issue_template import REQUIRED_SUBSECTIONS  # lazy: avoids circular at import time

        errors: list[str] = []
        for section in REQUIRED_SUBSECTIONS:
            if section not in body:
                errors.append(f"Missing required section: {section}")

        if GRAPH_CONTEXT_PLACEHOLDER in body:
            errors.append(
                "Graph Context section still contains the unfilled placeholder text"
            )

        return IssueBodyCheckResult(passed=not errors, errors=errors)


def dup_check_before_file(
    slug: str,
    run_gh=None,
) -> list:
    """Search GitHub for open issues matching the slug before filing a new one.

    Returns a list of dicts with 'number' and 'title' for each match.
    run_gh is injectable for unit tests; defaults to real subprocess call.

    E013: minimize issues filed without dup-check (#657).
    """
    if run_gh is None:
        def run_gh(s):
            words = s.replace("-", " ")
            return subprocess.run(
                ["gh", "issue", "list", "--search", words, "--state", "open",
                 "--json", "number,title,state", "--limit", "10"],
                capture_output=True,
                text=True,
            )

    try:
        result = run_gh(slug)
        if result.returncode != 0 or not result.stdout.strip():
            return []
        issues = json.loads(result.stdout)
        return [{"number": i["number"], "title": i["title"]} for i in issues]
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return []


class IssueManager:
    """Manage ATDD issues via GitHub Issues and Projects v2."""

    VALID_TYPES = {
        "implementation",
        "migration",
        "refactor",
        "analysis",
        "planning",
        "cleanup",
        "tracking",
    }

    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the IssueManager.

        Args:
            target_dir: Target directory containing .atdd/ config. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
        self.wmbt_template_source = self.package_root / "templates" / "WMBT-SUBISSUE-TEMPLATE.md"
        self.parent_template_source = self.package_root / "templates" / "PARENT-ISSUE-TEMPLATE.md"

    def _check_initialized(self) -> bool:
        """Check if ATDD is initialized with GitHub integration."""
        if not self.config_file.exists():
            print("Error: ATDD not initialized. Run 'atdd init' first.")
            print(f"Expected: {self.config_file}")
            return False
        if not self._has_github_config():
            print("Error: GitHub integration not configured. Run 'atdd init' first.")
            return False
        return True

    def _load_manifest(self) -> Dict[str, Any]:
        """Load the manifest.yaml file."""
        with open(self.manifest_file) as f:
            return yaml.safe_load(f) or {}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Save the manifest.yaml file."""
        with open(self.manifest_file, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    def _commit_manifest_change(
        self,
        verb: str,
        message: str,
        allow_main: bool = False,
        strict: Optional[bool] = None,
    ) -> None:
        """Atomically commit the local manifest after a CLI-driven write.

        Convention: src/atdd/coach/conventions/issue.convention.yaml
                    (manifest_write_discipline)

        No-ops when ``self.target_dir`` is not a git working tree (e.g. unit
        tests that supply a bare ``tmp_path`` without ``git init``).

        Failure handling depends on ``strict`` (#738):

        - ``strict=True`` — issue registration (``atdd issue``). A genuine
          ``ManifestCommitError`` is re-raised so the caller can fail loudly
          with a non-zero exit; reporting success with an unregistered issue
          is silently wrong.
        - ``strict=False`` — the status-mirror path (``atdd update --status``).
          A ``ManifestCommitError`` is surfaced as a printed warning so the
          verb's primary work (the GitHub status transition) is not lost;
          transitions for issues created outside the CLI are valid.

        When ``strict`` is ``None`` it defaults to whether ``verb`` is the
        issue-registration verb.

        Raises:
            ManifestCommitError: when ``strict`` and the commit genuinely
                cannot complete.
        """
        if strict is None:
            strict = verb.strip() == _MANIFEST_REGISTRATION_VERB
        if not (self.target_dir / ".git").exists():
            return
        if not self.manifest_file.exists():
            return
        from atdd.coach.utils.git import (
            ManifestCommitError,
            git_commit_manifest_update,
        )
        try:
            sha = git_commit_manifest_update(
                path=self.manifest_file,
                message=message,
                verb=verb,
                repo_root=self.target_dir,
                allow_main=allow_main,
            )
        except ManifestCommitError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            if strict:
                # Issue registration must never report a silent success.
                raise
            print(f"  Warning: manifest not committed — {exc}")
            print(
                "    Run `git add .atdd/manifest.yaml && git commit` once "
                "you have addressed the cause."
            )
            return
        if sha:
            print(f"  Committed manifest update ({sha[:8]})")

    def _store_set_status(self, issue_number: int, status: str) -> bool:
        """Write the lifecycle phase to the State Store (#1203 Phase 2, authoritative).

        Resolves issue_number → work-item slug via the GitHub ``external_ref`` and
        sets the object ``state`` through the storage API (no raw SQL — within the
        #1220 boundaries). Returns True on a store write, False if the store is
        unavailable or the issue is not yet in the store; the caller's manifest
        mirror still runs (dual-write keeps the manifest projection valid until it
        is fully demoted). Never raises — the GitHub transition must not be lost.
        """
        try:
            from atdd.state.db import connect, init_state_store
            from atdd.state.store import StateStore
            from atdd.state.work_item_reader import WorkItemReader

            # WorkItemReader auto-imports the manifest on first read when the store
            # is empty, so the work item exists before we resolve + write it.
            with WorkItemReader(control_root=self.target_dir) as reader:
                obj = reader.get(issue_number)
            if obj is None:
                return False
            conn = connect(init_state_store(start=self.target_dir))
            try:
                StateStore(conn).objects.set_state(obj.uid, status)
            finally:
                conn.close()
            return True
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "State Store status write unavailable; manifest mirror still applies",
                extra={"issue": issue_number, "status": status, "error": str(exc)},
            )
            return False

    def _update_manifest_status(self, issue_number: int, status: str) -> None:
        """Record a successful GitHub status transition.

        #1203 Phase 2: the State Store is authoritative for the work-item phase —
        this writes the store first, then mirrors the manifest ``sessions`` entry
        (a compatibility projection, retained until the manifest is fully demoted).
        A missing manifest or a manifest without a matching session is a no-op for
        the mirror — transitions for unregistered issues are valid (e.g. issues
        created outside the atdd CLI) and must not crash the lifecycle.
        """
        self._store_set_status(issue_number, status)
        if not self.manifest_file.exists():
            return
        manifest = self._load_manifest()
        sessions = manifest.get("sessions") or []
        mutated = False
        for entry in sessions:
            if entry.get("issue_number") == issue_number:
                entry["status"] = status
                mutated = True
        if mutated:
            self._save_manifest(manifest)
            self._commit_manifest_change(
                verb="atdd update --status",
                message=(
                    f"chore(coach): mirror issue #{issue_number} status → {status} in manifest"
                ),
            )

    def _store_work_item_field(
        self, issue_number: int, field: str
    ) -> Optional[str]:
        """Read a work-item field (``status``/``train``/``branch``) from the State Store.

        #1203 Phase 1 (shadow reads): the State Store is the read source for
        work-item lifecycle state, resolved by GitHub issue number through the
        ``external_refs`` projection. The reader auto-imports the manifest into
        the store on first read when the store is empty (Decision #3), so callers
        normally get the value from the store. Returns ``None`` on any store
        unavailability so the caller falls back to the manifest — never raises.
        """
        try:
            from atdd.state.work_item_reader import WorkItemReader

            with WorkItemReader(control_root=self.target_dir) as reader:
                value = getattr(reader, field)(issue_number)
            return str(value) if value else None
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "State Store read unavailable; falling back to manifest",
                extra={"issue": issue_number, "field": field, "error": str(exc)},
            )
            return None

    def _manifest_train(self, issue_number: int) -> Optional[str]:
        """Return the train assigned to *issue_number*.

        #1203 Phase 1: reads shadow through the State Store first (the
        authoritative read source), then fall back to the local manifest —
        ``issues.<n>.train`` first, then any ``train`` recorded on the matching
        ``sessions`` entry. The manifest remains the sole source for train
        lineage past PLANNED (#1051, decommission Projects v2). Returns None when
        no train is recorded anywhere.
        """
        from_store = self._store_work_item_field(issue_number, "train")
        if from_store:
            return from_store
        if not self.manifest_file.exists():
            return None
        manifest = self._load_manifest()
        issues = manifest.get("issues") or {}
        entry = issues.get(str(issue_number)) or {}
        train = entry.get("train")
        if train:
            return str(train)
        for session in manifest.get("sessions") or []:
            if session.get("issue_number") == issue_number and session.get("train"):
                return str(session["train"])
        return None

    def _manifest_branch(self, issue_number: int) -> Optional[str]:
        """Return the branch recorded for *issue_number*.

        #1203 Phase 1: reads shadow through the State Store first, then fall back
        to the local manifest — the matching ``sessions`` entry first, then
        ``issues.<n>.branch``. Replaces the retired Projects v2 ``ATDD Branch``
        read (#1051).
        """
        from_store = self._store_work_item_field(issue_number, "branch")
        if from_store:
            return from_store
        if not self.manifest_file.exists():
            return None
        manifest = self._load_manifest()
        for session in manifest.get("sessions") or []:
            if session.get("issue_number") == issue_number and session.get("branch"):
                return str(session["branch"])
        entry = (manifest.get("issues") or {}).get(str(issue_number)) or {}
        branch = entry.get("branch")
        return str(branch) if branch else None

    def _store_update_fields(self, issue_number: int, fields: Dict[str, Any]) -> bool:
        """Merge work-item metadata (branch/train/...) into the State Store.

        #1203 Phase 2: resolves issue_number → slug via the github external_ref and
        merges ``fields`` into the work item's ``data`` bag (preserving its kind and
        lifecycle ``state``) through ``ObjectStore.upsert`` — storage API, no raw SQL,
        within the #1220 boundaries. Returns True on a store write, False if the store
        is unavailable or the issue is not in the store. Never raises.
        """
        try:
            from atdd.state.db import connect, init_state_store
            from atdd.state.store import StateStore
            from atdd.state.work_item_reader import WorkItemReader

            with WorkItemReader(control_root=self.target_dir) as reader:
                obj = reader.get(issue_number)
            if obj is None:
                return False
            merged = {**obj.data, **fields}
            conn = connect(init_state_store(start=self.target_dir))
            try:
                StateStore(conn).objects.upsert(
                    obj.uid, obj.kind, state=obj.state, data=merged
                )
            finally:
                conn.close()
            return True
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "State Store field write unavailable; manifest mirror still applies",
                extra={"issue": issue_number, "fields": sorted(fields), "error": str(exc)},
            )
            return False

    def _update_manifest_fields(
        self, issue_number: int, fields: Dict[str, Any]
    ) -> None:
        """Record work-item metadata (branch/train/...).

        #1203 Phase 2: the State Store is authoritative — this writes the store
        first (merging into the work item's ``data``), then mirrors the manifest
        ``sessions`` entry and the ``issues.<n>`` record (a compatibility
        projection). A missing manifest is a no-op for the mirror — transitions
        for issues created outside the atdd CLI remain valid.
        """
        self._store_update_fields(issue_number, fields)
        if not self.manifest_file.exists():
            return
        manifest = self._load_manifest()
        mutated = False
        for session in manifest.get("sessions") or []:
            if session.get("issue_number") == issue_number:
                session.update(fields)
                mutated = True
        issues = manifest.setdefault("issues", {})
        record = issues.get(str(issue_number))
        if record is not None:
            record.update(fields)
            mutated = True
        if mutated:
            self._save_manifest(manifest)
            self._commit_manifest_change(
                verb="atdd update",
                message=(
                    f"chore(coach): mirror issue #{issue_number} metadata in manifest"
                ),
            )

    def _slugify(self, text: str) -> str:
        """Convert text to kebab-case slug."""
        # Convert to lowercase
        slug = text.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove non-alphanumeric characters except hyphens
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Remove consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def _load_config(self) -> Dict[str, Any]:
        """Load .atdd/config.yaml."""
        if not self.config_file.exists():
            return {}
        with open(self.config_file) as f:
            return yaml.safe_load(f) or {}

    def _has_github_config(self) -> bool:
        """Check if GitHub integration is configured.

        Only ``github.repo`` is required (#1051): the Projects v2 board — and
        its ``project_id`` — was decommissioned, so the issue label (REST) plus
        the local manifest carry all state.
        """
        config = self._load_config()
        github = config.get("github", {})
        return bool(github.get("repo"))

    def _get_github_client(self):
        """Get a GitHubClient from config. Returns None if not configured."""
        from atdd.coach.github import GitHubClient, ProjectConfig, GitHubClientError
        try:
            project_config = ProjectConfig.from_config(self.config_file)
            return GitHubClient(
                repo=project_config.repo,
                project_id=project_config.project_id,
            )
        except GitHubClientError as e:
            logger.debug("GitHub client not available: %s", e, extra={"error": str(e)})
            return None

    def _render_wmbt_body(
        self, wagon: str, wmbt_id: str, statement: str,
        acceptances: List[str], test_file: str,
    ) -> str:
        """Render WMBT sub-issue body from template."""
        if not self.wmbt_template_source.exists():
            # Inline fallback
            template = (
                "## wmbt:{wagon}:{wmbt_id}\n\n"
                "**Step:** {step_name} | **URN:** `wmbt:{wagon}:{wmbt_id}`\n"
                "**Statement:** {statement}\n\n"
                "### ATDD Cycle\n\n"
                "- [ ] RED: failing test written\n"
                "- [ ] GREEN: implementation passes test\n"
                "- [ ] SMOKE: integration test against real infrastructure\n"
                "- [ ] REFACTOR: architecture compliance verified\n\n"
                "### Acceptance Criteria\n\n"
                "{acceptance_criteria}\n\n"
                "### Test File\n\n"
                "`{test_file_path}`\n"
            )
        else:
            template = self.wmbt_template_source.read_text()

        step_code = wmbt_id[0] if wmbt_id else "E"
        step_name = STEP_CODES.get(step_code, "Execute")

        if acceptances:
            acceptance_criteria = "\n".join(f"- {a}" for a in acceptances)
        else:
            acceptance_criteria = "- (no acceptance criteria defined in plan YAML)"

        return template.format(
            wagon=wagon,
            wmbt_id=wmbt_id,
            step_name=step_name,
            statement=statement,
            acceptance_criteria=acceptance_criteria,
            test_file_path=test_file,
        )

    def _build_gate_test_rows(self, archetypes_list: List[str]) -> str:
        """Build archetype-specific gate test table rows."""
        rows = []
        for arch in archetypes_list:
            for gate_id, phase, command, validator in ARCHETYPE_GATES.get(arch, []):
                rows.append(
                    f"| {gate_id} | {phase} | `{command}` | PASS | `{validator}` | TODO |"
                )
        if rows:
            return "\n".join(rows) + "\n"
        return ""

    def _inject_graph_context(self, body: str, slug: str, train: Optional[str]) -> str:
        """Replace `GRAPH_CONTEXT_PLACEHOLDER` with the rendered graph section.

        Phase 2 of #682: `atdd issue <slug>` now auto-fills the
        `### Graph Context` subsection from `plan/<slug>/_<slug>.yaml` so
        operators stop manually re-running `atdd repo graph`. When the wagon
        manifest is absent (no plan/ entry yet), splices `GRAPH_CONTEXT_UNAVAILABLE`
        — a graceful fallback that names the recovery path without erroring.
        """
        if GRAPH_CONTEXT_PLACEHOLDER not in body:
            return body
        try:
            from atdd.coach.commands.issue_graph import build_architecture_context_for_wagon

            train_id = train if train and train != "TBD" else None
            graph = build_architecture_context_for_wagon(
                slug, train_id=train_id, repo_root=self.target_dir,
            )
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            graph = None

        if not graph:
            return body.replace(GRAPH_CONTEXT_PLACEHOLDER, GRAPH_CONTEXT_UNAVAILABLE)

        # `build_architecture_context_for_wagon` returns a block that opens with
        # `## Architecture context`. We splice INTO an existing `### Graph Context`
        # H3, so strip the leading H2 heading line + the following blank line to
        # avoid a nested-heading collision.
        lines = graph.splitlines()
        if lines and lines[0].startswith("## "):
            lines = lines[1:]
        if lines and lines[0] == "":
            lines = lines[1:]
        inner = "\n".join(lines)
        return body.replace(GRAPH_CONTEXT_PLACEHOLDER, inner)

    def _render_parent_body(
        self,
        slug: str,
        issue_type: str,
        today: str,
        train_display: str,
        archetypes_display: str,
    ) -> str:
        """Render parent issue body from template.

        Falls back to inline minimal body if the template file is missing.
        """
        archetypes_list = [
            a.strip() for a in archetypes_display.split(",") if a.strip() and a.strip() != "TBD"
        ]

        # Conditional Data Model section
        has_db = any(a in ("db", "migrations") for a in archetypes_list)
        if has_db:
            data_model_section = (
                "### Data Model\n\n"
                "```sql\n"
                "-- Table/view definitions\n"
                "CREATE TABLE IF NOT EXISTS public.example (\n"
                "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                "  data JSONB NOT NULL,\n"
                "  created_at TIMESTAMPTZ DEFAULT NOW(),\n"
                "  updated_at TIMESTAMPTZ DEFAULT NOW()\n"
                ");\n"
                "```"
            )
        else:
            data_model_section = ""

        gate_tests_rows = self._build_gate_test_rows(archetypes_list)

        if not self.parent_template_source.exists():
            return self._render_parent_body_inline(
                slug, issue_type, today, train_display, archetypes_display,
            )

        # D001: seed Branch to `{prefix}/{slug}` based on issue_type so orchestrate
        # can resolve the branch without a post-hoc body amendment.
        prefix = TYPE_TO_PREFIX.get(issue_type, "feat")
        branch_display = f"`{prefix}/{slug}`"

        template = self.parent_template_source.read_text()
        return template.format(
            today=today,
            slug=slug,
            issue_type=issue_type,
            train_display=train_display,
            archetypes_display=archetypes_display,
            data_model_section=data_model_section,
            gate_tests_rows=gate_tests_rows,
            branch_display=branch_display,
        )

    def _render_parent_body_inline(
        self,
        slug: str,
        issue_type: str,
        today: str,
        train_display: str,
        archetypes_display: str,
    ) -> str:
        """Inline fallback body when template file is missing."""
        return (
            f"## Issue Metadata\n\n"
            f"| Field | Value |\n"
            f"|-------|-------|\n"
            f"| Date | `{today}` |\n"
            f"| Status | `INIT` |\n"
            f"| Type | `{issue_type}` |\n"
            f"| Branch | TBD |\n"
            f"| Archetypes | {archetypes_display} |\n"
            f"| Train | {train_display} |\n"
            f"| Feature | TBD |\n\n"
            f"---\n\n"
            f"## Context\n\n"
            f"(fill in)\n\n"
            f"---\n\n"
            f"## Activity Log\n\n"
            f"### Entry 1 ({today})\n\n"
            f"**Completed:**\n"
            f"- Issue created via `atdd issue {slug}`\n"
        )

    def _discover_wmbts_from_feature(
        self,
        wagon: str,
        feature_urn: str,
    ) -> List[Dict[str, Any]]:
        """Discover WMBTs by following a feature URN to its WMBT YAML files.

        Unlike :meth:`_discover_wmbts`, which expects inline WMBT dicts under
        ``wmbts:`` in the feature YAML, this resolver walks the
        ``wagon:<id>:<WMBT>`` URN list most features actually contain and
        loads each WMBT YAML from ``plan/<wagon_snake>/<WMBT>.yaml``.
        """
        plan_dir = self.target_dir / "plan"
        wagon_snake = wagon.replace("-", "_")
        wagon_dir = plan_dir / wagon_snake

        feature_slug = feature_urn.split(":")[-1]
        feature_file = wagon_dir / "features" / f"{feature_slug.replace('-', '_')}.yaml"

        if not feature_file.exists():
            return []

        with open(feature_file) as f:
            feature_data = yaml.safe_load(f) or {}

        wmbts: List[Dict[str, Any]] = []
        for urn in feature_data.get("wmbts", []):
            if not isinstance(urn, str) or not urn.startswith("wmbt:"):
                continue
            parts = urn.split(":")
            if len(parts) != 3:
                continue
            wmbt_id = parts[2]
            wmbt_path = wagon_dir / f"{wmbt_id}.yaml"
            if not wmbt_path.exists():
                continue
            with open(wmbt_path) as f:
                wmbt_data = yaml.safe_load(f) or {}
            statement = wmbt_data.get("statement", "")
            acceptances = []
            for a in wmbt_data.get("acceptances", []):
                identity = a.get("identity", {}) if isinstance(a, dict) else {}
                acceptances.append(identity.get("purpose") or identity.get("urn") or "")
            wmbts.append({"id": wmbt_id, "statement": statement, "acceptances": acceptances})

        return wmbts

    def sync_wmbts(self, issue_number: int) -> int:
        """Backfill GitHub WMBT sub-issues for a parent issue from plan YAMLs.

        Idempotent: sub-issues whose titles already contain ``wmbt:<wagon>:<id>``
        are left alone. Missing ones are created and linked to the parent.

        Manifest requirement: the session entry for ``issue_number`` must have
        ``wagon`` and ``feature`` fields so the backfill can resolve the feature
        YAML and its WMBT URN list. This is intentional — sync is only safe
        for issues whose plan artifacts are known.

        Returns the number of sub-issues created, or 1 on a hard error.
        """
        manifest = self._load_manifest() if self.manifest_file.exists() else {}
        sessions = manifest.get("sessions") or []
        entry = next(
            (s for s in sessions if s.get("issue_number") == issue_number),
            None,
        )
        if entry is None:
            print(f"Error: Issue #{issue_number} not found in manifest.")
            return 1

        wagon = entry.get("wagon")
        feature_urn = entry.get("feature")
        if not wagon or not feature_urn:
            print(
                f"Error: Issue #{issue_number} session entry missing 'wagon' or "
                f"'feature' fields. sync_wmbts needs both to resolve plan artifacts."
            )
            return 1

        wmbts = self._discover_wmbts_from_feature(wagon, feature_urn)
        if not wmbts:
            print(
                f"No WMBTs discovered for feature {feature_urn}. "
                f"Check plan/{wagon.replace('-', '_')}/features/."
            )
            return 0

        client = self._get_github_client()
        existing_subs = client.get_sub_issues(issue_number)
        existing_ids = set()
        for sub in existing_subs:
            title = sub.get("title", "")
            if f":{wagon}:" not in title:
                continue
            for wmbt in wmbts:
                if f":{wmbt['id']}" in title:
                    existing_ids.add(wmbt["id"])

        created = 0
        for wmbt in wmbts:
            if wmbt["id"] in existing_ids:
                continue
            sub_title = f"wmbt:{wagon}:{wmbt['id']} — {wmbt['statement']}"
            sub_body = self._render_wmbt_body(
                wagon=wagon,
                wmbt_id=wmbt["id"],
                statement=wmbt["statement"],
                acceptances=wmbt["acceptances"],
                test_file=f"src/atdd/coach/commands/tests/test_{wmbt['id']}_{entry.get('slug', wagon)}.py",
            )
            sub_number = client.create_issue(
                title=sub_title,
                body=sub_body,
                labels=["atdd-wmbt"],
            )
            client.add_sub_issue(issue_number, sub_number)
            created += 1

        if created:
            print(f"sync_wmbts: created {created} sub-issue(s) for #{issue_number}")
        else:
            print(f"sync_wmbts: #{issue_number} already has all WMBT sub-issues")
        return created

    # -------------------------------------------------------------------------
    # sync_labels — derive label set from body metadata, apply delta
    # -------------------------------------------------------------------------

    # Phase labels the schema declares as ``exactly_one`` and swap-on-transition.
    _PHASE_LABELS = (
        "atdd:INIT", "atdd:PLANNED", "atdd:RED", "atdd:GREEN",
        "atdd:SMOKE", "atdd:REFACTOR", "atdd:COMPLETE", "atdd:BLOCKED",
    )

    def _derive_expected_labels(self, body: str) -> List[str]:
        """Compute the label set implied by the Issue Metadata table.

        Source of truth is the ``## Issue Metadata`` table:
        - ``Status`` → ``atdd:<STATUS>`` (phase label)
        - ``Archetypes`` → one ``archetype:<id>`` per comma-separated entry,
          backticks tolerated on each entry (e.g., ```coach`, `planner``)
        - ``Wagon`` → one ``wagon:<slug>`` per ``wagon:X`` token found in
          the row; descriptive trailers are tolerated
          (e.g., ``wagon:a (primary), wagon:b (secondary) — note``).

        ``atdd-issue`` is always included because any issue with the
        PARENT template is by definition a parent issue.
        """
        import re
        from atdd.coach.commands.session_template import parse_metadata

        meta = parse_metadata(body or "")
        expected: List[str] = ["atdd-issue"]

        status = (meta.get("Status") or "").strip().strip("`").upper()
        if status and status != "TBD":
            expected.append(f"atdd:{status}")

        archetypes_raw = (meta.get("Archetypes") or "").strip()
        if archetypes_raw and archetypes_raw.upper() != "TBD":
            for part in archetypes_raw.split(","):
                name = part.strip().strip("`").strip()
                if name and name.upper() != "TBD":
                    expected.append(f"archetype:{name}")

        wagon_raw = (meta.get("Wagon") or "").strip()
        if wagon_raw and wagon_raw.upper() != "TBD":
            # Accept multiple ``wagon:X`` tokens in the row (cross-wagon
            # issues are first-class per Decision #5). Tolerate backticks
            # and descriptive trailers. Fall back to bare slug if the row
            # contains no ``wagon:`` prefix.
            matches = re.findall(r"wagon:([a-z][a-z0-9-]*)", wagon_raw)
            if matches:
                for slug in matches:
                    expected.append(f"wagon:{slug}")
            else:
                slug = wagon_raw.strip("`").strip()
                if re.fullmatch(r"[a-z][a-z0-9-]*", slug):
                    expected.append(f"wagon:{slug}")

        return expected

    def _labels_in_scope_for_sync(self, label: str) -> bool:
        """Only these label families are managed by ``sync_labels``.

        Non-ATDD labels (e.g., ``bug``, ``good-first-issue``) are left
        alone — sync_labels is idempotent on its own surface and never
        removes labels outside the scheme.
        """
        if label == "atdd-issue":
            return True
        if label.startswith("atdd:"):
            return True
        if label.startswith("archetype:"):
            return True
        if label.startswith("wagon:"):
            return True
        return False

    def sync_labels(
        self, issue_number: int, dry_run: bool = False,
    ) -> Dict[str, List[str]]:
        """Read the issue body on GitHub, derive the expected label set
        from the Issue Metadata table, and apply the delta.

        Returns a dict with ``to_add`` and ``to_remove`` lists so callers
        (CLI, tests) can report the delta.

        In dry-run mode the lists are computed but no ``add_label`` /
        ``remove_label`` calls are issued.

        Only labels inside the ATDD scheme (``atdd-issue``, ``atdd:*``,
        ``archetype:*``, ``wagon:*``) are compared — unrelated labels on
        the issue are left untouched.
        """
        client = self._get_github_client()
        issue = client.get_issue(issue_number)

        body = issue.get("body") or ""
        current_raw = issue.get("labels") or []
        current_labels: Set[str] = set()
        for entry in current_raw:
            if isinstance(entry, dict):
                name = entry.get("name")
                if name:
                    current_labels.add(name)
            elif isinstance(entry, str):
                current_labels.add(entry)

        expected = set(self._derive_expected_labels(body))

        in_scope_current = {lbl for lbl in current_labels if self._labels_in_scope_for_sync(lbl)}

        to_add = sorted(expected - current_labels)
        to_remove = sorted(in_scope_current - expected)

        if dry_run:
            return {"to_add": to_add, "to_remove": to_remove}

        if to_add:
            client.add_label(issue_number, to_add)
        if to_remove:
            client.remove_label(issue_number, to_remove)

        return {"to_add": to_add, "to_remove": to_remove}

    def sync_labels_all(
        self, dry_run: bool = False,
    ) -> List[Tuple[int, Dict[str, List[str]]]]:
        """Apply sync_labels to every open ``atdd-issue`` in the repo.

        Sub-issues (``atdd-wmbt``) are out of scope — their label surface
        is ``atdd-wmbt`` only and is maintained by ``sync_wmbts``.

        Returns a list of ``(issue_number, delta)`` tuples so callers
        (CLI, tests) can render output. Presentation is not this method's
        responsibility — see ``_print_sync_labels_delta`` in cli.py.
        """
        client = self._get_github_client()
        issues = client.list_issues_by_label("atdd-issue", include_body=False)
        results: List[Tuple[int, Dict[str, List[str]]]] = []
        for issue in issues:
            number = issue.get("number")
            if not number:
                continue
            delta = self.sync_labels(int(number), dry_run=dry_run)
            results.append((int(number), delta))
        return results

    def _discover_wmbts(self, wagon: str) -> List[Dict[str, Any]]:
        """Discover WMBTs from plan YAML for a wagon."""
        plan_dir = self.target_dir / "plan"
        wagon_snake = wagon.replace("-", "_")
        wagon_dir = plan_dir / wagon_snake

        wmbts = []
        if not wagon_dir.exists():
            logger.debug("No plan dir for wagon %s at %s", wagon, wagon_dir, extra={"wagon": wagon})
            return wmbts

        # Look for feature YAMLs containing wmbt sections
        for feature_file in sorted(wagon_dir.glob("features/*.yaml")):
            with open(feature_file) as f:
                feature_data = yaml.safe_load(f) or {}

            for wmbt in feature_data.get("wmbts", []):
                wmbt_id = wmbt.get("id", "")
                wmbts.append({
                    "id": wmbt_id,
                    "statement": wmbt.get("statement", wmbt.get("description", "")),
                    "acceptances": [
                        a.get("text", a) if isinstance(a, dict) else str(a)
                        for a in wmbt.get("acceptances", wmbt.get("acceptance_criteria", []))
                    ],
                })

        return wmbts

    def _build_github_client(self, github_config: dict):
        """Construct a GitHubClient honoring both test patch targets (E019).

        Tests may patch either ``atdd.coach.commands.issue.GitHubClient``
        (module-level sentinel) or ``atdd.coach.github.GitHubClient`` (the
        real class).  Checking ``globals()`` first handles the former; falling
        through to the imported module handles the latter.
        """
        import atdd.coach.github as _gh_module

        _GHC = globals().get("GitHubClient") or _gh_module.GitHubClient
        return _GHC(
            repo=github_config["repo"],
            project_id=github_config.get("project_id"),
        )

    def _store_create_work_item(
        self, issue_number: int, slug: str, *, status: Optional[str], data: Dict[str, Any]
    ) -> bool:
        """Create/register a work item in the State Store (#1203 Phase 2).

        Upserts the work item keyed by ``slug`` and links its GitHub issue number as
        the authoritative ``external_ref`` (storage APIs only — no raw SQL, within the
        #1220 boundaries; the link's ON CONFLICT keeps one ref per issue). Preserves an
        existing object's lifecycle ``state`` and merges into its ``data`` so a
        re-registration never clobbers live phase. Returns True on a store write, False
        if the store is unavailable. Never raises.
        """
        try:
            from atdd.state.db import connect, init_state_store
            from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
            from atdd.state.store import StateStore

            conn = connect(init_state_store(start=self.target_dir))
            try:
                store = StateStore(conn)
                existing = store.objects.get(slug)
                state = existing.state if existing is not None else status
                merged = {**(existing.data if existing is not None else {}), **data}
                store.objects.upsert(slug, WORK_ITEM_KIND, state=state, data=merged)
                store.external_refs.link(
                    slug, GITHUB_PROVIDER, "issue", str(issue_number),
                    data={"source": "atdd-issue"},
                )
            finally:
                conn.close()
            return True
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "State Store work-item create unavailable; manifest registration still applies",
                extra={"issue": issue_number, "slug": slug, "error": str(exc)},
            )
            return False

    def _register_issue_in_manifest(
        self,
        issue_number: int,
        slug: str,
        train: Optional[str] = None,
    ) -> None:
        """Register a newly published issue.

        #1203 Phase 2: writes the work item to the State Store first (authoritative),
        then mirrors the manifest ``issues.<n>`` record (a compatibility projection).
        """
        self._store_create_work_item(
            issue_number, slug, status="INIT", data={"train": train}
        )
        if not self.manifest_file.exists():
            return
        manifest = self._load_manifest()
        issues = manifest.setdefault("issues", {})
        issues[str(issue_number)] = {"slug": slug, "train": train}
        self._save_manifest(manifest)
        self._commit_manifest_change("atdd issue", f"Add issue #{issue_number} ({slug})")

    def create_new_issue(
        self,
        slug: str,
        issue_type: str = "implementation",
        train: Optional[str] = None,
        archetypes: Optional[str] = None,
    ) -> int:
        """Create a GitHub issue with a pre-publish local compliance gate (E019).

        Validates the rendered body locally via IssueBodyChecker before making
        any GitHub API call.  Publishes via a single ``gh issue create`` — no
        follow-up body edit.

        Raises IssueBodyComplianceError when the body fails the gate.
        Returns the new issue number on success.
        """
        from atdd.coach.github import GitHubClientError

        try:
            config = self._load_config()
            github_config = config["github"]
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            print(f"Error: config load failed: {exc}")
            return 1

        today = date.today().isoformat()
        train_display = train or "TBD"
        archetypes_display = archetypes or "TBD"
        prefix = TYPE_TO_PREFIX.get(issue_type, "feat")
        title_text = slug.replace("-", " ").title()
        title = f"{prefix}(atdd): {title_text}"

        body = self._render_parent_body(slug, issue_type, today, train_display, archetypes_display)
        body = self._inject_graph_context(body, slug, train)

        checker = IssueBodyChecker()
        check_result = checker.check(body)
        if not check_result.passed:
            raise IssueBodyComplianceError(
                "Issue body failed compliance check — refusing to publish.\n"
                + "\n".join(check_result.errors)
            )

        try:
            client = self._build_github_client(github_config)
        except GitHubClientError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            print(f"Error: GitHub integration failed: {exc}")
            return 1

        parent_labels = ["atdd-issue", "atdd:INIT"]
        if archetypes:
            for arch in archetypes.split(","):
                arch = arch.strip()
                if arch:
                    parent_labels.append(f"archetype:{arch}")

        parent_number = client.create_issue(title=title, body=body, labels=parent_labels)
        print(f"Created #{parent_number}: {title}")

        # Issue state is carried by the atdd:INIT label (REST) + the manifest
        # record below — no Projects v2 board writes (#1051).
        self._register_issue_in_manifest(parent_number, slug, train)

        wmbts = self._discover_wmbts(slug)
        if wmbts:
            print(f"Creating {len(wmbts)} WMBT sub-issues...")

        return parent_number

    def edit_issue_body(self, issue_number: int, body: str) -> None:
        """Edit an existing GitHub issue body after re-running the compliance gate (E019).

        Raises IssueBodyComplianceError when the body fails --check.
        """
        checker = IssueBodyChecker()
        check_result = checker.check(body)
        if not check_result.passed:
            raise IssueBodyComplianceError(
                "Replacement body failed compliance check — refusing to edit.\n"
                + "\n".join(check_result.errors)
            )

        try:
            config = self._load_config()
            github_config = config["github"]
            client = self._build_github_client(github_config)
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            print(f"Error: GitHub integration failed: {exc}")
            return

        client.edit_issue(issue_number, body)

    def new(
        self,
        slug: str,
        issue_type: str = "implementation",
        train: Optional[str] = None,
        archetypes: Optional[str] = None,
        allow_main_commit: bool = False,
        no_dup_check: bool = False,
    ) -> int:
        """
        Create new issue.

        Creates a parent GitHub Issue + WMBT sub-issues with Project v2 fields.

        Args:
            slug: Issue slug (will be converted to kebab-case).
            issue_type: Type of issue (implementation, migration, etc.).
            train: Optional train ID to assign to the issue.
            archetypes: Optional comma-separated archetype IDs (e.g., "be,contracts,wmbt").
            no_dup_check: Skip duplicate-check search (use when you've already verified uniqueness).

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        # Validate issue type
        if issue_type not in self.VALID_TYPES:
            print(f"Error: Invalid issue type '{issue_type}'")
            print(f"Valid types: {', '.join(sorted(self.VALID_TYPES))}")
            return 1

        # Slugify the name
        slug = self._slugify(slug)
        if not slug:
            print("Error: Invalid slug - results in empty string")
            return 1

        # E013: dup-check before filing (#657)
        if not no_dup_check:
            matches = dup_check_before_file(slug)
            if matches:
                print(f"Warning: Found {len(matches)} potentially duplicate issue(s) for '{slug}':")
                for m in matches:
                    print(f"  #{m['number']}: {m['title']}")
                print("To file anyway, pass --no-dup-check to bypass this check.")
                return 1

        return self._new_github_issue(
            slug, issue_type, train=train, archetypes=archetypes,
            allow_main_commit=allow_main_commit,
        )

    def _new_github_issue(
        self,
        slug: str,
        issue_type: str,
        train: Optional[str] = None,
        archetypes: Optional[str] = None,
        allow_main_commit: bool = False,
    ) -> int:
        """Create a GitHub Issue with WMBT sub-issues."""
        from atdd.coach.github import GitHubClient, ProjectConfig, GitHubClientError

        try:
            config = self._load_config()
            github_config = config["github"]
            client = GitHubClient(
                repo=github_config["repo"],
                project_id=github_config.get("project_id"),
            )
        except (GitHubClientError, KeyError) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: GitHub integration failed: {e}")
            return 1

        today = date.today().isoformat()
        title_text = slug.replace("-", " ").title()
        prefix = TYPE_TO_PREFIX.get(issue_type, "feat")
        title = f"{prefix}(atdd): {title_text}"

        train_display = train or "TBD"
        archetypes_display = archetypes if archetypes else "TBD"

        # Render full-structure body from template
        body = self._render_parent_body(
            slug, issue_type, today, train_display, archetypes_display,
        )

        # Phase 2 of #682 — auto-inject `### Graph Context` from
        # `plan/<slug>/_<slug>.yaml` so operators stop manually invoking
        # `atdd repo graph --issue <N>`. Graceful fallback when the wagon
        # manifest is absent.
        body = self._inject_graph_context(body, slug, train)

        # Determine labels for parent
        parent_labels = ["atdd-issue", "atdd:INIT"]

        # Add archetype labels
        if archetypes:
            for arch in archetypes.split(","):
                arch = arch.strip()
                if arch:
                    parent_labels.append(f"archetype:{arch}")

        # Create parent issue
        print(f"Creating parent issue...")
        parent_number = client.create_issue(
            title=title,
            body=body,
            labels=parent_labels,
        )
        print(f"  Created #{parent_number}: {title}")

        # Phase/type/train/archetypes are carried by the atdd:INIT label (REST)
        # and the local manifest record (#1051) — the Projects v2 board is
        # decommissioned, so no board writes happen on creation.

        # Discover WMBTs from plan YAML
        wagon = slug  # Default: wagon slug = issue slug
        wmbts = self._discover_wmbts(wagon)

        wmbt_count = 0
        if wmbts:
            print(f"Creating {len(wmbts)} WMBT sub-issues...")
            for wmbt in wmbts:
                wmbt_id = wmbt["id"]
                statement = wmbt["statement"]
                acceptances = wmbt["acceptances"]
                step_code = wmbt_id[0] if wmbt_id else "E"
                step_name = STEP_CODES.get(step_code, "Execute")

                sub_title = f"wmbt:{wagon}:{wmbt_id} — {statement}"
                sub_body = self._render_wmbt_body(
                    wagon=wagon,
                    wmbt_id=wmbt_id,
                    statement=statement,
                    acceptances=acceptances,
                    test_file=f"src/atdd/coach/commands/tests/test_{wmbt_id}_{slug}.py",
                )

                sub_number = client.create_issue(
                    title=sub_title,
                    body=sub_body,
                    labels=["atdd-wmbt"],
                )
                print(f"  Created #{sub_number}: wmbt:{wagon}:{wmbt_id}")

                # Link as sub-issue
                try:
                    client.add_sub_issue(parent_number, sub_number)
                except GitHubClientError as e:
                    print(f"    Warning: Could not link sub-issue: {e}")

                # WMBT sub-issues carry their identity via labels only (#1051);
                # the Projects v2 board WMBT fields are decommissioned.

                wmbt_count += 1

        # Update manifest
        manifest = self._load_manifest()
        issue_entry = {
            "id": f"{parent_number:02d}" if parent_number < 100 else str(parent_number),
            "slug": slug,
            "file": None,
            "issue_number": parent_number,
            "type": issue_type,
            "status": "INIT",
            "created": today,
            "archived": None,
        }
        if "sessions" not in manifest:
            manifest["sessions"] = []
        manifest["sessions"].append(issue_entry)
        # #1203 Phase 2: the State Store is authoritative — record the new work item
        # there too (slug + github external_ref), keeping the manifest as a mirror.
        self._store_create_work_item(
            parent_number, slug, status="INIT",
            data={k: v for k, v in issue_entry.items() if k not in ("slug", "status")},
        )
        self._save_manifest(manifest)
        # Registration must land or fail loudly — never a silent exit-0 with an
        # unregistered issue (#738). _commit_manifest_change(strict=True) for the
        # registration verb re-raises a genuine ManifestCommitError.
        from atdd.coach.utils.git import ManifestCommitError
        try:
            self._commit_manifest_change(
                verb=_MANIFEST_REGISTRATION_VERB,
                message=f"chore(coach): register issue #{parent_number} in manifest",
                allow_main=allow_main_commit,
            )
        except ManifestCommitError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(
                f"Error: issue #{parent_number} created on GitHub but its "
                f".atdd/manifest.yaml registration could not be committed — {exc}"
            )
            print(
                "    The issue is NOT registered. Resolve the cause, then run "
                "`git add .atdd/manifest.yaml && git commit`."
            )
            return 1

        print(f"\nCreated #{parent_number} with {wmbt_count} WMBTs")
        print(f"  Repo: {github_config['repo']}")
        print(f"  Type: {issue_type}")
        print(f"  Status: INIT")

        return 0

    # -------------------------------------------------------------------------
    # E002: list
    # -------------------------------------------------------------------------

    def list(self) -> int:
        """List issues from GitHub."""
        if not self._check_initialized():
            return 1

        return self._list_github()

    def _list_github(self) -> int:
        """List issues from GitHub with sub-issue progress."""
        from atdd.coach.github import GitHubClientError

        try:
            client = self._get_github_client()
            issues = client.list_issues_by_label("atdd-issue")
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {e}")
            return 1

        if not issues:
            print("No issues found.")
            print("Create one with: atdd new my-feature")
            return 0

        print("\n" + "=" * 80)
        print("ATDD Issues")
        print("=" * 80)
        print(f"{'#':<6} {'Status':<12} {'Progress':<10} {'Title':<50}")
        print("-" * 80)

        for issue in sorted(issues, key=lambda x: x["number"]):
            num = issue["number"]
            title = issue["title"][:50]
            labels = [l["name"] for l in issue.get("labels", [])]

            # Extract status from atdd:* label
            status = "UNKNOWN"
            for label in labels:
                if label.startswith("atdd:") and label != "atdd-issue":
                    status = label.split(":")[1]
                    break

            # Get sub-issue progress
            try:
                subs = client.get_sub_issues(num)
                total = len(subs)
                closed = sum(1 for s in subs if s.get("state") == "closed")
                progress = f"{closed}/{total}" if total > 0 else "-"
            except Exception:
                progress = "?"

            print(f"#{num:<5} {status:<12} {progress:<10} {title}")

        print("-" * 80)
        print(f"Total: {len(issues)} issues")
        return 0

    # -------------------------------------------------------------------------
    # E010: open_issues (all open issues, not just ATDD-labeled)
    # -------------------------------------------------------------------------

    def open_issues(
        self,
        label: Optional[str] = None,
        limit: int = 30,
        assignee: Optional[str] = None,
    ) -> int:
        """List open GitHub issues (all, not just ATDD-labeled).

        Args:
            label: Optional label filter.
            limit: Max issues to return (default 30).
            assignee: Optional assignee login filter.

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        from atdd.coach.github import GitHubClientError

        try:
            client = self._get_github_client()
            issues = client.list_open_issues(
                label=label, limit=limit, assignee=assignee,
            )
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {e}")
            return 1

        if not issues:
            print("No open issues found.")
            return 0

        print("\n" + "=" * 80)
        print("Open Issues")
        print("=" * 80)
        print(f"{'#':<7} {'Title':<42} {'Labels':<16} {'Created':<12}")
        print("-" * 80)

        for issue in sorted(issues, key=lambda x: x["number"]):
            num = issue["number"]
            title = issue["title"][:41]
            label_names = [l["name"] for l in issue.get("labels", [])]
            labels_str = ",".join(label_names)[:15] if label_names else "-"
            created = issue.get("createdAt", "")[:10]

            print(f"#{num:<6} {title:<42} {labels_str:<16} {created}")

        print("-" * 80)
        print(f"Total: {len(issues)} open issue{'s' if len(issues) != 1 else ''}")
        return 0

    # -------------------------------------------------------------------------
    # E003: archive
    # -------------------------------------------------------------------------

    def archive(self, issue_id: str) -> int:
        """Archive an issue. Closes parent + all sub-issues on GitHub."""
        if not self._check_initialized():
            return 1

        return self._archive_github(issue_id)

    def _archive_github(self, issue_id: str) -> int:
        """Close parent issue + all sub-issues on GitHub."""
        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(issue_id)
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: Invalid issue number '{issue_id}'")
            return 1

        try:
            client = self._get_github_client()
            issue = client.get_issue(issue_number)
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {e}")
            return 1

        if issue.get("state") == "closed":
            print(f"#{issue_number} is already closed.")
            return 0

        # Close all open sub-issues
        try:
            subs = client.get_sub_issues(issue_number)
            closed_count = 0
            for sub in subs:
                if sub.get("state") == "open":
                    client.close_issue(sub["number"])
                    print(f"  Closed sub-issue #{sub['number']}")
                    closed_count += 1
        except GitHubClientError as e:
            print(f"  Warning: Could not close sub-issues: {e}")
            closed_count = 0

        # Close parent
        client.close_issue(issue_number)
        print(f"  Closed parent #{issue_number}")

        # Swap label to atdd:COMPLETE
        try:
            labels = [l["name"] for l in issue.get("labels", [])]
            phase_labels = [l for l in labels if l.startswith("atdd:") and l != "atdd-issue"]
            if phase_labels:
                client.remove_label(issue_number, phase_labels)
            client.add_label(issue_number, ["atdd:COMPLETE"])
        except GitHubClientError as e:
            print(f"  Warning: Could not update labels: {e}")

        # COMPLETE is carried by the atdd:COMPLETE label (REST) + the manifest
        # archive record below (#1051) — no Projects v2 board write.

        # #1203 Phase 2: the State Store is authoritative for the work-item
        # lifecycle — record the archive there first (terminal COMPLETE phase +
        # the archived date), then mirror the manifest below. Both calls degrade
        # to a logged no-op if the store is unavailable; the GitHub close +
        # manifest record below still apply.
        self._store_set_status(issue_number, "COMPLETE")
        self._store_update_fields(issue_number, {"archived": date.today().isoformat()})

        # Update manifest
        manifest = self._load_manifest()
        for s in manifest.get("sessions", []):
            if s.get("issue_number") == issue_number:
                s["status"] = "COMPLETE"
                s["archived"] = date.today().isoformat()
                break
        self._save_manifest(manifest)
        self._commit_manifest_change(
            verb="atdd archive",
            message=f"chore(coach): archive issue #{issue_number} in manifest",
        )

        total_subs = len(subs) if subs else 0
        print(f"\nArchived #{issue_number}: closed {closed_count} sub-issues, "
              f"{total_subs} total")
        return 0

    # -------------------------------------------------------------------------
    # Gate verification helpers (used by update → COMPLETE)
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_gate_tests(body: str) -> List[Dict[str, str]]:
        """Parse gate test table rows from issue body markdown.

        Expected table format (under ## Validation → ### Gate Tests):
        | ID | Phase | Command | Expected | ATDD Validator | Status |

        Returns list of dicts with keys: id, phase, command, expected, validator, status
        """
        gates = []
        # Find the Gate Tests table — look for header row with ID|Phase|Command
        in_table = False
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                if in_table:
                    break  # End of table
                continue

            cells = [c.strip() for c in stripped.split("|")[1:-1]]  # strip empty first/last
            if len(cells) < 6:
                continue

            # Skip header and separator rows
            if cells[0] in ("ID", "") or cells[0].startswith("-"):
                if cells[0] == "ID":
                    in_table = True
                continue

            if not in_table:
                continue

            # Extract command — strip backticks
            command = cells[2].strip("`").strip()
            if not command:
                continue

            gates.append({
                "id": cells[0].strip(),
                "phase": cells[1].strip(),
                "command": command,
                "expected": cells[3].strip(),
                "validator": cells[4].strip("`").strip(),
                "status": cells[5].strip(),
            })

        return gates

    def _run_gate_tests(
        self, gates: List[Dict[str, str]], force: bool = False,
    ) -> Tuple[bool, List[str]]:
        """Run gate test commands and return (all_passed, messages).

        Each gate command is executed via subprocess. Exit code 0 = PASS.
        If force=True, logs warnings but does not block.
        """
        messages = []
        all_passed = True

        for gate in gates:
            gate_id = gate["id"]
            command = gate["command"]

            if force:
                messages.append(f"  {gate_id}: SKIPPED (--force) — {command}")
                continue

            print(f"  Running {gate_id}: {command} ...", end=" ", flush=True)

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.target_dir),
                timeout=300,  # 5 min max per gate
            )

            if result.returncode == 0:
                print("PASS")
                messages.append(f"  {gate_id}: PASS — {command}")
            else:
                print("FAIL")
                all_passed = False
                stderr_snippet = result.stderr.strip().splitlines()[-3:] if result.stderr else []
                messages.append(
                    f"  {gate_id}: FAIL (exit {result.returncode}) — {command}"
                )
                for line in stderr_snippet:
                    messages.append(f"    {line}")

        return all_passed, messages

    @staticmethod
    def _parse_artifacts(body: str) -> Dict[str, List[str]]:
        """Parse Artifacts section from issue body markdown.

        Returns dict with keys: created, modified, deleted — each a list of paths.
        Skips template placeholders like '(none yet)'.
        """
        artifacts: Dict[str, List[str]] = {"created": [], "modified": [], "deleted": []}

        # Find ## Artifacts section
        section_match = re.search(
            r"## Artifacts\s*\n(.*?)(?=\n## |\Z)",
            body,
            re.DOTALL,
        )
        if not section_match:
            return artifacts

        section = section_match.group(1)

        # Parse each subsection
        current_key = None
        for line in section.splitlines():
            stripped = line.strip()
            if stripped.startswith("### Created"):
                current_key = "created"
            elif stripped.startswith("### Modified"):
                current_key = "modified"
            elif stripped.startswith("### Deleted"):
                current_key = "deleted"
            elif stripped.startswith("- ") and current_key:
                path = stripped[2:].strip().strip("`")
                # Skip placeholders
                if path.startswith("(") or not path:
                    continue
                # Strip trailing descriptions after ' — ' or ' - '
                for sep in (" — ", " - ", " ("):
                    if sep in path:
                        path = path[:path.index(sep)].strip()
                artifacts[current_key].append(path)

        return artifacts

    def _verify_artifacts(
        self, artifacts: Dict[str, List[str]], force: bool = False,
    ) -> Tuple[bool, List[str]]:
        """Verify artifact claims against git state.

        - Created: file must exist in HEAD
        - Modified: file must have changes vs main
        - Deleted: file must NOT exist in HEAD
        """
        messages = []
        all_valid = True

        total = sum(len(v) for v in artifacts.values())
        if total == 0:
            return True, ["  No artifacts declared"]

        for path in artifacts["created"]:
            if force:
                messages.append(f"  Created:  {path} — SKIPPED (--force)")
                continue
            result = subprocess.run(
                ["git", "ls-tree", "HEAD", "--", path],
                capture_output=True, text=True, cwd=str(self.target_dir),
            )
            if result.stdout.strip():
                messages.append(f"  Created:  {path} — EXISTS")
            else:
                messages.append(f"  Created:  {path} — MISSING")
                all_valid = False

        for path in artifacts["modified"]:
            if force:
                messages.append(f"  Modified: {path} — SKIPPED (--force)")
                continue
            result = subprocess.run(
                ["git", "diff", "main...HEAD", "--", path],
                capture_output=True, text=True, cwd=str(self.target_dir),
            )
            if result.stdout.strip():
                messages.append(f"  Modified: {path} — CHANGED")
            else:
                messages.append(f"  Modified: {path} — NO CHANGES vs main")
                all_valid = False

        for path in artifacts["deleted"]:
            if force:
                messages.append(f"  Deleted:  {path} — SKIPPED (--force)")
                continue
            result = subprocess.run(
                ["git", "ls-tree", "HEAD", "--", path],
                capture_output=True, text=True, cwd=str(self.target_dir),
            )
            if not result.stdout.strip():
                messages.append(f"  Deleted:  {path} — CONFIRMED GONE")
            else:
                messages.append(f"  Deleted:  {path} — STILL EXISTS")
                all_valid = False

        return all_valid, messages

    @staticmethod
    def _parse_issue_type(body: str) -> Optional[str]:
        """Extract issue type from ## Issue Metadata table.

        Looks for ``| Type | `{type}` |`` in the metadata table.
        """
        match = re.search(r"\|\s*Type\s*\|\s*`?(\w+)`?\s*\|", body)
        return match.group(1).lower().strip() if match else None

    # Types that require a train assignment
    TRAIN_REQUIRED_TYPES = {"implementation", "migration", "refactor"}

    def _check_rebased_on_main(self) -> Tuple[bool, str]:
        """Check that current branch is rebased on origin/main.

        Returns:
            (passed, message) — passed is True if origin/main is an ancestor of HEAD.
        """
        # Fetch latest main
        fetch = subprocess.run(
            ["git", "fetch", "origin", "main"],
            capture_output=True, text=True, cwd=str(self.target_dir), timeout=30,
        )
        if fetch.returncode != 0:
            return True, "  Rebase check: SKIPPED (could not fetch origin/main)"

        # Check if origin/main is ancestor of HEAD
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
            capture_output=True, text=True, cwd=str(self.target_dir), timeout=10,
        )
        if result.returncode == 0:
            return True, "  Rebase check: PASS (branch includes origin/main)"
        else:
            return False, "  Rebase check: FAIL (branch is behind origin/main)"

    def _check_smoke_evidence_gate(
        self,
        issue_number: int,
    ) -> Tuple[bool, List[str]]:
        """COACH-RATCHET-PRES-001: gate SMOKE→REFACTOR on smoke evidence.

        When the branch reduces a ``*/presentation/*.{tsx,ts,py}`` file by
        more than 20% relative to ``origin/main``, the transition requires
        ``.atdd/smoke-evidence/<N>.yaml`` to exist. Issue #358.

        Returns:
            (passed, messages) — passed True when no presentation reduction
            is detected OR the evidence file exists.
        """
        # Lazy import keeps issue.py free of coder-side imports at module load.
        from atdd.coder.validators.presentation_ratchet import (
            collect_repo_reductions,
            has_smoke_evidence,
        )

        messages: List[str] = []
        try:
            reductions = collect_repo_reductions(
                self.target_dir,
                base_ref="origin/main",
                head_ref="HEAD",
            )
        except subprocess.CalledProcessError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            messages.append("  Smoke gate: SKIPPED (origin/main unreachable)")
            return True, messages
        except Exception as exc:  # noqa: BLE001 — fail-open on git breakage  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            messages.append(f"  Smoke gate: SKIPPED ({exc})")
            return True, messages

        if not reductions:
            messages.append("  Smoke gate: PASS (no presentation reductions >20%)")
            return True, messages

        if has_smoke_evidence(self.target_dir, issue_number):
            messages.append(
                f"  Smoke gate: PASS ({len(reductions)} presentation reduction(s); "
                f"evidence at .atdd/smoke-evidence/{issue_number}.yaml)"
            )
            return True, messages

        messages.append(
            f"  Smoke gate: FAIL ({len(reductions)} presentation reduction(s) >20%)"
        )
        for r in reductions[:5]:
            pct = round(r.reduction_ratio * 100)
            messages.append(
                f"    - {r.path}: {r.before_lines} → {r.after_lines} lines ({pct}%)"
            )
        if len(reductions) > 5:
            messages.append(f"    ... and {len(reductions) - 5} more")
        return False, messages

    def _verify_release_gate(
        self, force: bool = False,
    ) -> Tuple[bool, List[str]]:
        """Verify release gate: version bumped + tag on HEAD or ancestor.

        Reuses the same logic as test_release_versioning.py but returns
        (passed, messages) instead of raising pytest assertions.
        """
        messages = []

        if force:
            messages.append("  Release gate: SKIPPED (--force)")
            return True, messages

        # Load config
        config_path = self.target_dir / ".atdd" / "config.yaml"
        if not config_path.exists():
            messages.append("  Release gate: SKIPPED (no .atdd/config.yaml)")
            return True, messages

        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        release = config.get("release")
        if not isinstance(release, dict):
            messages.append("  Release gate: SKIPPED (no release config)")
            return True, messages

        version_file = release.get("version_file")
        if not version_file:
            messages.append("  Release gate: SKIPPED (no version_file configured)")
            return True, messages

        tag_prefix = release.get("tag_prefix", "v") or ""

        # Resolve version file path
        version_path = Path(version_file)
        if not version_path.is_absolute():
            version_path = (self.target_dir / version_path).resolve()

        if not version_path.exists():
            messages.append(f"  Version file: {version_file} — MISSING")
            return False, messages

        # Read version
        version = self._read_version_from_file(version_path)
        if not version:
            messages.append(f"  Version file: {version_file} — could not parse version")
            return False, messages

        expected_tag = f"{tag_prefix}{version}"

        # Check version changed vs main
        diff_result = subprocess.run(
            ["git", "diff", "main", "--", str(version_path)],
            capture_output=True, text=True, cwd=str(self.target_dir),
        )
        if not diff_result.stdout.strip():
            messages.append(f"  Version file: {version_file} — NOT CHANGED vs main")
            return False, messages

        messages.append(f"  Version file: {version_file} = {version} — CHANGED vs main")

        # Check tag on HEAD (fast path)
        tag_result = subprocess.run(
            ["git", "tag", "--points-at", "HEAD"],
            capture_output=True, text=True, cwd=str(self.target_dir),
        )
        tags = [t.strip() for t in tag_result.stdout.splitlines() if t.strip()]

        if expected_tag in tags:
            messages.append(f"  Tag: {expected_tag} — ON HEAD")
            return True, messages

        # Merge-commit tolerance: tag is a recent ancestor
        ancestor_result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", expected_tag, "HEAD"],
            capture_output=True, text=True, cwd=str(self.target_dir),
        )
        if ancestor_result.returncode == 0:
            count_result = subprocess.run(
                ["git", "rev-list", "--count", f"{expected_tag}..HEAD"],
                capture_output=True, text=True, cwd=str(self.target_dir),
            )
            distance = int(count_result.stdout.strip()) if count_result.returncode == 0 else -1
            if 0 < distance <= 3:
                messages.append(f"  Tag: {expected_tag} — {distance} commit(s) behind HEAD (merge tolerance)")
                return True, messages

        messages.append(f"  Tag: {expected_tag} — NOT FOUND (create: git tag {expected_tag})")
        return False, messages

    @staticmethod
    def _read_version_from_file(path: Path) -> Optional[str]:
        """Read version string from a version file (pyproject.toml, package.json, plain)."""
        if path.name == "pyproject.toml":
            text = path.read_text()
            # Lightweight regex parsing (no toml dependency needed in CLI)
            for line in text.splitlines():
                stripped = line.strip()
                match = re.match(r'version\s*=\s*["\']([^"\']+)["\']', stripped)
                if match:
                    return match.group(1).strip()
        elif path.name == "package.json":
            import json
            data = json.loads(path.read_text())
            return str(data.get("version", "")).strip() or None
        else:
            # Plain text: first semver-like string
            pattern = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                m = pattern.search(stripped)
                if m:
                    return m.group(1)
        return None

    def _validate_train_against_trains_yaml(
        self, train_value: str,
    ) -> Tuple[bool, List[str]]:
        """Cross-reference train value against _trains.yaml.

        Returns (valid, messages). If _trains.yaml doesn't exist, passes (no constraint).
        """
        messages = []
        plan_dir = self.target_dir / "plan"
        trains_file = plan_dir / "_trains.yaml"

        valid_ids: set = set()

        if trains_file.exists():
            with open(trains_file) as f:
                data = yaml.safe_load(f) or {}
            for _theme, categories in data.get("trains", {}).items():
                if isinstance(categories, dict):
                    for _cat, trains_list in categories.items():
                        if isinstance(trains_list, list):
                            for t in trains_list:
                                tid = t.get("train_id", "")
                                if tid:
                                    valid_ids.add(tid)

        trains_dir = plan_dir / "_trains"
        if trains_dir.exists():
            for f in trains_dir.glob("*.yaml"):
                valid_ids.add(f.stem)

        if not valid_ids:
            # No trains defined — skip cross-ref
            return True, []

        if train_value in valid_ids:
            messages.append(f"  Train: {train_value} — VALID (in _trains.yaml)")
            return True, messages

        messages.append(
            f"  Train: {train_value} — NOT FOUND in _trains.yaml"
        )
        return False, messages

    def _validate_pr_exists_for_branch(
        self, branch_name: str,
    ) -> Tuple[bool, List[str]]:
        """Issue #478: PR-existence check for INIT → PLANNED gate.

        Returns ``(exists, messages)``. ``exists`` is True when ``gh pr list
        --head <branch>`` returns a non-empty result. Subprocess failures
        (gh missing, timeout) fail-open with True so the gate never wedges
        a transition on local tooling problems.
        """
        messages: List[str] = []
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--head", branch_name,
                 "--state", "open", "--json", "number",
                 "--jq", ".[0].number"],
                capture_output=True, text=True, timeout=10,
                cwd=str(self.target_dir),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.debug(
                "PR-existence gate fail-open: %s",
                exc,
                extra={"branch": branch_name, "action": "fail_open"},
            )
            return True, []
        if result.returncode != 0:
            logger.debug(
                "gh pr list failed; PR-existence gate fail-open: %s",
                result.stderr.strip(),
                extra={"branch": branch_name, "action": "fail_open"},
            )
            return True, []
        pr_number = result.stdout.strip()
        if pr_number:
            messages.append(f"  PR: #{pr_number} found for branch '{branch_name}'")
            return True, messages
        return False, messages

    # -------------------------------------------------------------------------
    # E004: update
    # -------------------------------------------------------------------------

    VALID_TRANSITIONS = {
        "INIT": {"PLANNED", "BLOCKED", "OBSOLETE"},
        "PLANNED": {"RED", "BLOCKED", "OBSOLETE"},
        "RED": {"GREEN", "BLOCKED", "OBSOLETE"},
        "GREEN": {"SMOKE", "BLOCKED", "OBSOLETE"},
        "SMOKE": {"REFACTOR", "BLOCKED", "OBSOLETE"},
        "REFACTOR": {"COMPLETE", "BLOCKED", "OBSOLETE"},
        "BLOCKED": {"INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "OBSOLETE"},
        "COMPLETE": set(),
        "OBSOLETE": set(),
    }

    def update(
        self,
        issue_id: str,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        branch: Optional[str] = None,
        train: Optional[str] = None,
        feature_urn: Optional[str] = None,
        archetypes: Optional[str] = None,
        complexity: Optional[str] = None,
        force: bool = False,
    ) -> int:
        """Update issue Project fields and labels."""
        if not self._check_initialized():
            return 1

        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(issue_id)
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: Invalid issue number '{issue_id}'")
            return 1

        # Projects v2 board sync is decommissioned (#1051). The lifecycle state
        # machine runs entirely on the ``atdd:<phase>`` label (REST) plus the
        # local .atdd/manifest.yaml mirror — no GraphQL board reads or writes.
        try:
            client = self._get_github_client()
            issue = client.get_issue(issue_number)
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {e}")
            return 1

        updated = []

        # Status transition with validation
        if status:
            status = status.upper()
            current_labels = [l["name"] for l in issue.get("labels", [])]
            current_status = "UNKNOWN"
            for label in current_labels:
                if label.startswith("atdd:") and label != "atdd-issue":
                    current_status = label.split(":")[1]
                    break

            allowed = self.VALID_TRANSITIONS.get(current_status, set())
            if status not in allowed and current_status != "UNKNOWN":
                print(f"Error: Cannot transition from {current_status} to {status}")
                print(f"  Allowed: {', '.join(sorted(allowed)) or '(terminal state)'}")
                return 1

            # E008: Enforce train assignment for transitions past PLANNED
            # Train is only required for implementation/migration/refactor types.
            # Other types (cleanup, analysis, planning, tracking) are train-optional.
            issue_body = issue.get("body", "") or ""
            issue_type = self._parse_issue_type(issue_body)

            post_planned = {"RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"}
            train_required = issue_type in self.TRAIN_REQUIRED_TYPES if issue_type else True

            if status in post_planned and train_required and not train:
                # Train lineage is read from the local manifest mirror (#1051),
                # never the Projects v2 board. An absent/TBD train fails loudly;
                # a present train is cross-referenced against plan/_trains.yaml
                # below (no board fallback recovers an unknown value).
                current_train = (self._manifest_train(issue_number) or "").strip()
                if not current_train or current_train.upper() == "TBD":
                    print(f"Error: Train field required for {issue_type or 'unknown'} type before transitioning to {status}")
                    print(f"  Current Train: {current_train or '(empty)'}")
                    print( "  Fix:")
                    print( "    1. cd into the issue's worktree (find via: git worktree list | grep <branch>):")
                    print( "       cd /path/to/<feat-or-fix>-<slug>")
                    print( "    2. Pick a train_id from plan/_trains.yaml::trains[].train_id (e.g. \"0001-self-compliance-validate\")")
                    print( "    3. Run:")
                    print(f"       atdd issue {issue_id} --status {status} --train <train_id>")
                    print( "  Why train: implementation-type issues require lineage to a Train past PLANNED")
                    print( "  so cross-cutting work threads to a shared journey. (See `plan/_trains.yaml`.)")
                    return 1
                train_valid, train_messages = self._validate_train_against_trains_yaml(current_train)
                for msg in train_messages:
                    print(msg)
                if not train_valid:
                    print(f"\nError: Train '{current_train}' (from manifest) not found in _trains.yaml")
                    print(f"  Fix: Use a valid train_id or add the train to plan/_trains.yaml")
                    return 1

            # Issue #478 — PR-existence gate at INIT → PLANNED.
            # `atdd branch` defers PR creation; `atdd pr` opens it post-commit.
            # Block PLANNED transition when no PR exists for the issue's branch.
            # --force bypasses the gate with a ::warning::.
            if status == "PLANNED":
                gate_branch = branch
                if not gate_branch:
                    gate_branch = (self._manifest_branch(issue_number) or "").strip()

                if gate_branch:
                    pr_exists, pr_messages = self._validate_pr_exists_for_branch(
                        gate_branch
                    )
                    for msg in pr_messages:
                        print(msg)
                    if not pr_exists:
                        if force:
                            print(
                                "::warning::PR-existence gate bypassed (--force); "
                                f"branch '{gate_branch}' has no open PR."
                            )
                        else:
                            print(
                                f"\nError: No open PR found for branch "
                                f"'{gate_branch}' — cannot transition to PLANNED."
                            )
                            print( "  Fix:")
                            print( "    1. cd into the issue's worktree")
                            print( "       (find via: git worktree list | grep <branch>):")
                            print(f"       cd /path/to/<feat-or-fix>-<slug>")
                            print( "    2. Make at least one commit on the branch:")
                            print( "       git add <files> && git commit -m \"<message>\"")
                            print( "       git push")
                            print(f"    3. atdd pr {issue_id}")
                            print(f"    4. atdd issue {issue_id} --status PLANNED")
                            print( "  Why PR: PLANNED transition assumes the branch is reviewable;")
                            print( "          a draft PR is the canonical review surface. (See #478.)")
                            print(f"  Bypass: atdd issue {issue_id} --status PLANNED --force")
                            return 1

            # Train cross-reference: validate --train value against _trains.yaml
            # This check applies regardless of --force (identity enforcement)
            if train:
                train_valid, train_messages = self._validate_train_against_trains_yaml(train)
                for msg in train_messages:
                    print(msg)
                if not train_valid:
                    print(f"\nError: Train '{train}' not found in _trains.yaml")
                    print(f"  Fix: Use a valid train_id or add the train to plan/_trains.yaml")
                    return 1

            # COACH-RATCHET-PRES-001 (issue #358): SMOKE→REFACTOR requires
            # smoke evidence when the PR includes a presentation-layer
            # ratchet improvement >20%. The detector runs git diff against
            # origin/main; absence of evidence blocks the transition.
            if status == "REFACTOR" and not force:
                gate_ok, gate_messages = self._check_smoke_evidence_gate(issue_number)
                for msg in gate_messages:
                    print(msg)
                if not gate_ok:
                    print(f"\nError: Presentation-layer ratchet detected — smoke evidence required")
                    print(f"  Fix: atdd validate coder --smoke-required {issue_number}")
                    print(f"  Bypass: atdd update {issue_id} --status REFACTOR --force")
                    return 1

            # Gate verification: run gate commands before allowing COMPLETE
            if status == "COMPLETE":
                # Rebase check: branch must not be behind main
                if not force:
                    rebase_ok, rebase_msg = self._check_rebased_on_main()
                    if rebase_msg:
                        print(rebase_msg)
                    if not rebase_ok:
                        print(f"\nError: Branch is behind main — cannot transition to COMPLETE")
                        print(f"  Fix: git fetch origin main && git rebase origin/main")
                        print(f"  Bypass: atdd update {issue_id} --status COMPLETE --force")
                        return 1
                else:
                    print(f"  Bypassing rebase check (--force)")

                gates = self._parse_gate_tests(issue_body)

                if gates:
                    if force:
                        print(f"\n  Bypassing {len(gates)} gate tests (--force)")
                    else:
                        print(f"\nRunning {len(gates)} gate tests for #{issue_number}:")

                    all_passed, gate_messages = self._run_gate_tests(gates, force=force)

                    for msg in gate_messages:
                        print(msg)

                    if not all_passed:
                        print(f"\nError: Gate tests failed — cannot transition to COMPLETE")
                        print(f"  Fix: Resolve failing gates, then retry")
                        print(f"  Bypass: atdd update {issue_id} --status COMPLETE --force")
                        return 1

                    if not force:
                        print()  # blank line after gate results
                elif not force:
                    print(f"\n  Warning: No gate tests found in issue body")

                # Artifact verification
                artifacts = self._parse_artifacts(issue_body)
                artifact_count = sum(len(v) for v in artifacts.values())

                if artifact_count > 0:
                    if force:
                        print(f"  Bypassing artifact verification (--force)")
                    else:
                        print(f"Verifying {artifact_count} artifacts for #{issue_number}:")

                    artifacts_valid, artifact_messages = self._verify_artifacts(
                        artifacts, force=force,
                    )

                    for msg in artifact_messages:
                        print(msg)

                    if not artifacts_valid:
                        print(f"\nError: Artifact verification failed — cannot transition to COMPLETE")
                        print(f"  Fix: Update ## Artifacts section with correct paths")
                        print(f"  Bypass: atdd update {issue_id} --status COMPLETE --force")
                        return 1

                    if not force:
                        print()
                elif not force:
                    print(f"  Warning: No artifacts declared in issue body")

                # Release gate verification
                if force:
                    print(f"  Bypassing release gate (--force)")
                else:
                    print(f"Verifying release gate for #{issue_number}:")

                release_valid, release_messages = self._verify_release_gate(force=force)

                for msg in release_messages:
                    print(msg)

                if not release_valid:
                    print(f"\nError: Release gate failed — cannot transition to COMPLETE")
                    print(f"  Fix: Bump version, commit, and create tag")
                    print(f"  Bypass: atdd update {issue_id} --status COMPLETE --force")
                    return 1

                if not force:
                    print()

            # Swap phase label — the sole authoritative phase write (#1051).
            phase_labels = [l for l in current_labels if l.startswith("atdd:") and l != "atdd-issue"]
            if phase_labels:
                client.remove_label(issue_number, phase_labels)
            client.add_label(issue_number, [f"atdd:{status}"])

            # R001: mirror the transition into the local manifest so readers of
            # .atdd/manifest.yaml do not diverge from GitHub state.
            self._update_manifest_status(issue_number, status)
            updated.append(f"status: {status}")

        # Validate branch prefix (every branch = a worktree)
        if branch:
            allowed = tuple(f"{p}/" for p in ALLOWED_BRANCH_PREFIXES)
            if not any(branch.startswith(p) for p in allowed):
                print(
                    f"Error: Branch '{branch}' must start with an allowed prefix: "
                    f"{', '.join(allowed)}\n"
                    f"Each branch is a git worktree. Example: feat/my-feature"
                )
                return 1

        # Text fields are mirrored into the local manifest (#1051) — the
        # Projects v2 board that previously carried branch/train/feature/
        # archetypes is decommissioned.
        text_updates = {
            "branch": branch,
            "train": train,
            "feature_urn": feature_urn,
            "archetypes": archetypes,
        }
        manifest_text = {k: v for k, v in text_updates.items() if v}
        if manifest_text:
            self._update_manifest_fields(issue_number, manifest_text)
            for key, value in manifest_text.items():
                updated.append(f"{key}: {value}")

        if updated:
            print(f"Updated #{issue_number}:")
            for u in updated:
                print(f"  {u}")
        else:
            print("Nothing to update.")

        return 0

    # -------------------------------------------------------------------------
    # E005: close-wmbt
    # -------------------------------------------------------------------------

    def close_wmbt(self, issue_id: str, wmbt_id: str, force: bool = False) -> int:
        """Close a WMBT sub-issue by ID."""
        if not self._check_initialized():
            return 1

        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(issue_id)
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: Invalid issue number '{issue_id}'")
            return 1

        try:
            client = self._get_github_client()
            subs = client.get_sub_issues(issue_number)
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {e}")
            return 1

        # Find sub-issue matching WMBT ID
        wmbt_id_upper = wmbt_id.upper()
        target = None
        for sub in subs:
            title = sub.get("title", "")
            # Match pattern: wmbt:*:{WMBT_ID}
            if f":{wmbt_id_upper}" in title.upper():
                target = sub
                break

        if not target:
            print(f"Error: No sub-issue found for WMBT {wmbt_id_upper} in #{issue_number}")
            available = [s["title"].split(":")[-1].split(" ")[0].strip() for s in subs]
            if available:
                print(f"  Available: {', '.join(available)}")
            return 1

        if target.get("state") == "closed":
            print(f"WMBT {wmbt_id_upper} (#{target['number']}) is already closed.")
            return 0

        # Check ATDD cycle checkboxes (warn if not all checked)
        body = target.get("body", "")
        unchecked = body.count("- [ ]")
        if unchecked > 0 and not force:
            print(f"Warning: {unchecked} unchecked ATDD cycle item(s) in #{target['number']}")
            print(f"  Use --force to close anyway")
            return 1

        # Close the sub-issue
        client.close_issue(target["number"])

        # Calculate progress
        total = len(subs)
        closed = sum(1 for s in subs if s.get("state") == "closed") + 1  # +1 for the one we just closed
        print(f"Closed {target['title']}")
        print(f"  Progress: {closed}/{total}")

        return 0

    def sync(self) -> int:
        """Sync is a no-op in GitHub-only mode. Issues are the source of truth."""
        print("Sync not needed — GitHub Issues are the source of truth.")
        print("Use `atdd list` to see current issues.")
        return 0

    def reconcile(self) -> int:
        """Backfill every open GitHub atdd-issue missing from .atdd/manifest.yaml.

        Self-heal path (#775): the manifest is a derived registry; the GitHub
        issue is the source of truth. Any issue labelled `atdd-issue` that is
        open on GitHub but absent from the manifest is synthesised and appended.
        Existing entries are left untouched (idempotent).

        Returns 0 on success, 1 on hard error.
        """
        if not self.manifest_file.exists():
            print("Error: .atdd/manifest.yaml not found. Run `atdd init` first.")
            return 1

        # Fetch open atdd-issues from GitHub
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--label", "atdd-issue",
                "--state", "open",
                "--limit", "200",
                "--json", "number,title,state,createdAt,labels",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"Error: gh issue list failed: {result.stderr.strip()}")
            return 1

        try:
            gh_issues = json.loads(result.stdout) or []
        except (json.JSONDecodeError, ValueError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-19
            print(f"Error: could not parse gh output: {exc}")
            return 1

        manifest = self._load_manifest()
        sessions = manifest.get("sessions") or []
        registered = {s.get("issue_number") for s in sessions}

        added = 0
        for issue in gh_issues:
            number = issue.get("number")
            if number is None or number in registered:
                continue

            title = issue.get("title", "")
            slug_raw = re.sub(r"^\w+(?:\([^)]*\))?:\s*", "", title)
            slug_raw = re.sub(r"\s*\(#\d+\)\s*$", "", slug_raw)
            slug = re.sub(r"[^a-z0-9]+", "-", slug_raw.lower()).strip("-") or f"issue-{number}"

            status = "INIT"
            for label in issue.get("labels", []):
                name = label.get("name", "")
                if name.startswith("atdd:"):
                    status = name[5:]
                    break

            created_raw = issue.get("createdAt", "")
            created = created_raw[:10] if created_raw else str(date.today())

            session_entry = {
                "id": str(number),
                "slug": slug,
                "file": None,
                "issue_number": number,
                "type": "implementation",
                "status": status,
                "created": created,
                "archived": None,
            }
            # #1203 Phase 2: the State Store is authoritative — create the
            # backfilled work item there first (slug + github external_ref),
            # keeping the manifest session entry below as a mirror.
            self._store_create_work_item(
                number, slug, status=status,
                data={k: v for k, v in session_entry.items() if k not in ("slug", "status")},
            )
            sessions.append(session_entry)
            registered.add(number)
            added += 1
            print(f"  Backfilled: #{number} {slug}")

        if added == 0:
            print("reconcile: manifest is up-to-date — no missing issues found.")
            return 0

        manifest["sessions"] = sessions
        self._save_manifest(manifest)
        self._commit_manifest_change(
            verb="atdd issue reconcile",
            message=f"chore(coach): reconcile manifest — backfill {added} unregistered issue(s)",
            strict=False,
        )
        print(f"reconcile: added {added} issue(s) to .atdd/manifest.yaml")
        return 0

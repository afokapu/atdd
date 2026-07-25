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

# Issue type → conventional commit / branch prefix mapping, and the allowed
# branch prefixes. MOVED to the neutral ``issue_prefixes`` module by C5a (#1382)
# so branch.py/pr.py no longer hard-depend on this monolith; re-exported here
# (identical objects) so existing ``from ...issue import TYPE_TO_PREFIX`` callers
# keep working until C5b (#1309) deletes the monolith. Do not redefine here.
from atdd.coach.commands.issue_prefixes import (  # noqa: E402  (re-export, single source of truth)
    ALLOWED_BRANCH_PREFIXES,
    TYPE_TO_PREFIX,
)

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
    # No "fe" rows. GT-020/GT-021 named `test_typescript_architecture.py` and
    # `test_design_system_compliance.py`, both pruned in #1518 — core is
    # stack-agnostic and those obligations belong to `frontend.extension.vite-coder`.
    # A frontend gate row is the workspace provider's to contribute, not core's to
    # hard-code; an entry naming a validator core no longer ships would render a
    # Validation table pointing at nothing.
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


class IssueManager:
    """Manage ATDD issues via GitHub Issues and Projects v2."""

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

        # issue number -> the commit its PR landed (or None). Resolved lazily and
        # remembered, so a gate sweep over many issues does not re-ask GitHub (#1611).
        self._landed_commit_cache: Dict[int, Optional[str]] = {}

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
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

    # _load_manifest / _save_manifest are RETIRED (#1400 CORE-034, Y002). The State Store is the
    # source of truth for lifecycle state and the committed projection is what peers share; a
    # reader that fell back to `.atdd/manifest.yaml` was a second source of truth that only spoke
    # up when the first was quiet. `self.manifest_file` survives for `_commit_manifest_change`,
    # which hands the path to `git commit` and never asks the file a question.

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
        except ManifestCommitError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        """Record a successful GitHub status transition into the State Store.

        #1270 slice F: the State Store is authoritative for the work-item phase
        (#1203 Phase 2) and every reader now resolves the phase from it (slices
        A–E). The former ``.atdd/manifest.yaml`` mirror write is retired — keeping
        a mirror nothing reads in sync was dead work (and the source of the
        parallel-session clobber #1270 removes). The manifest survives only as the
        store's cold-start seed until Slice G.
        """
        self._store_set_status(issue_number, status)

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
                "State Store read unavailable; the issue resolves to nothing",
                extra={"issue": issue_number, "field": field, "error": str(exc)},
            )
            return None

    def _store_slug(self, issue_number: int) -> Optional[str]:
        """The work-item slug for *issue_number*, from the store (#1400 CORE-034)."""
        try:
            from atdd.state.work_item_reader import WorkItemReader

            with WorkItemReader(control_root=self.target_dir) as reader:
                entry = reader.session_entry(issue_number)
            return str(entry["slug"]) if entry and entry.get("slug") else None
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "State Store read unavailable; the issue resolves to no slug",
                extra={"issue": issue_number, "error": str(exc)},
            )
            return None

    def _manifest_train(self, issue_number: int) -> Optional[str]:
        """Return the train assigned to *issue_number*.

        #1270 slice D: the State Store is the sole read source (authoritative
        since #1203); the local-manifest fallback (``issues.<n>.train`` /
        ``sessions`` train) is retired. Returns None when no train is recorded.
        """
        return self._store_work_item_field(issue_number, "train")

    def _manifest_branch(self, issue_number: int) -> Optional[str]:
        """Return the branch recorded for *issue_number*.

        #1270 slice D: the State Store is the sole read source (authoritative
        since #1203); the local-manifest fallback is retired. Replaces the
        retired Projects v2 ``ATDD Branch`` read (#1051).
        """
        return self._store_work_item_field(issue_number, "branch")

    def branch_is_registered(self, branch: str) -> bool:
        """Return True if *branch*'s work item is registered — from the store alone.

        #1270 slice C: the store-backed replacement for the pre-commit hook's
        ``grep "slug:" .atdd/manifest.yaml``. Resolves the branch → slug (strips
        the ``prefix/`` segment; a work item is keyed in the store by its slug
        uid) and asks the State Store.

        #1400 CORE-034 (Y002): the manifest fallback that followed is retired. It made this
        gate answer from whichever source happened to be populated — and the two could disagree,
        which meant a branch could be "registered" to the hook and unknown to every command that
        reads the store. One source, one answer.

        Returns True when the slug is registered, OR when the store holds nothing to check
        against — mirroring the hook's historical "nothing to check ⇒ don't block" behaviour so
        a barely-initialised repo is never falsely blocked. Returns False only when the repo IS
        atdd-managed (the store holds work items) yet the slug is absent. Never raises; makes no
        GitHub calls.
        """
        slug = branch.split("/", 1)[-1] if "/" in branch else branch
        store_has_items = False
        try:
            from atdd.state.db import connect, init_state_store
            from atdd.state.manifest_import import WORK_ITEM_KIND
            from atdd.state.store import StateStore

            conn = connect(init_state_store(start=self.target_dir))
            try:
                store = StateStore(conn)
                if store.objects.get(slug) is not None:
                    return True
                store_has_items = bool(store.objects.list(kind=WORK_ITEM_KIND))
            finally:
                conn.close()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "branch-registration store read unavailable; nothing to check against",
                extra={"branch": branch, "error": str(exc)},
            )

        # Absent from a populated store → not registered; empty store → nothing to
        # check → do not block.
        return not store_has_items

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
        """Record work-item metadata (branch/train/...) into the State Store.

        #1270 slice F: the State Store is authoritative (#1203 Phase 2) and every
        reader resolves metadata from it (slices A–E). The former
        ``.atdd/manifest.yaml`` mirror write (``sessions`` + ``issues.<n>``) is
        retired — nothing reads it. The manifest survives only as the store's
        cold-start seed until Slice G.
        """
        self._store_update_fields(issue_number, fields)

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

    # -------------------------------------------------------------------------
    # sync_labels — derive label set from body metadata, apply delta
    # -------------------------------------------------------------------------

    # Phase labels the schema declares as ``exactly_one`` and swap-on-transition.
    _PHASE_LABELS = (
        "atdd:INIT", "atdd:PLANNED", "atdd:RED", "atdd:GREEN",
        "atdd:SMOKE", "atdd:REFACTOR", "atdd:COMPLETE", "atdd:BLOCKED",
    )

    # A CLOSED atdd-issue must not advertise an in-flight phase. These are
    # the non-terminal phase labels — a closed issue carrying any of them
    # (e.g. #1172 merged directly from INIT) is normalized to the terminal
    # ``atdd:COMPLETE`` by ``sync_labels``. ``atdd:COMPLETE``/``atdd:OBSOLETE``
    # are terminal and left as-is.
    _NON_TERMINAL_PHASE_LABELS = frozenset({
        "atdd:INIT", "atdd:PLANNED", "atdd:RED", "atdd:GREEN",
        "atdd:SMOKE", "atdd:REFACTOR", "atdd:BLOCKED",
    })
    _TERMINAL_PHASE_LABEL = "atdd:COMPLETE"

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

        expected.extend(self._archetype_labels(meta.get("Archetypes")))
        expected.extend(self._wagon_labels(meta.get("Wagon")))
        return expected

    @staticmethod
    def _archetype_labels(archetypes_raw: Optional[str]) -> List[str]:
        """One archetype:<id> label per comma-separated entry, backticks tolerated."""
        archetypes_raw = (archetypes_raw or "").strip()
        if not archetypes_raw or archetypes_raw.upper() == "TBD":
            return []

        labels = []
        for part in archetypes_raw.split(","):
            name = part.strip().strip("`").strip()
            if name and name.upper() != "TBD":
                labels.append(f"archetype:{name}")
        return labels

    @staticmethod
    def _wagon_labels(wagon_raw: Optional[str]) -> List[str]:
        """One wagon:<slug> label per ``wagon:X`` token in the row.

        Cross-wagon issues are first-class (Decision #5), so multiple tokens are
        accepted; backticks and descriptive trailers are tolerated. A row with
        no ``wagon:`` prefix falls back to a bare slug.
        """
        wagon_raw = (wagon_raw or "").strip()
        if not wagon_raw or wagon_raw.upper() == "TBD":
            return []

        matches = re.findall(r"wagon:([a-z][a-z0-9-]*)", wagon_raw)
        if matches:
            return [f"wagon:{slug}" for slug in matches]

        slug = wagon_raw.strip("`").strip()
        if re.fullmatch(r"[a-z][a-z0-9-]*", slug):
            return [f"wagon:{slug}"]
        return []

    def _reconcile_closed_phase_labels(self, expected: Set[str]) -> Set[str]:
        """Normalize the expected label set for a CLOSED issue.

        A closed atdd-issue must not carry a non-terminal phase label: the
        lifecycle has no legal ``INIT -> COMPLETE`` transition, so an issue
        whose implementation merged directly from INIT (e.g. #1172) gets
        ``gh issue close``d with a stale ``atdd:INIT`` label that
        misrepresents its state to any label-reader.

        Any non-terminal phase label in ``expected`` is replaced with the
        terminal ``atdd:COMPLETE``. Terminal labels (``atdd:COMPLETE``,
        ``atdd:OBSOLETE``) are left untouched. Non-phase labels
        (archetype/wagon/atdd-issue) are never affected.
        """
        stale = expected & self._NON_TERMINAL_PHASE_LABELS
        if not stale:
            return expected
        reconciled = expected - stale
        reconciled.add(self._TERMINAL_PHASE_LABEL)
        return reconciled

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

        # CLOSED issues must not advertise a non-terminal phase (#1284).
        if (issue.get("state") or "").upper() == "CLOSED":
            expected = self._reconcile_closed_phase_labels(expected)

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
        """Apply sync_labels to every ``atdd-issue`` in the repo.

        Both OPEN and CLOSED issues are visited (``state="all"``): closed
        issues can carry a stale non-terminal phase label (e.g. #1172),
        and reconciling those is the whole point of #1284 — restricting
        to open issues would never reach them.

        Sub-issues (``atdd-wmbt``) are out of scope — their label surface
        is ``atdd-wmbt`` only.

        Returns a list of ``(issue_number, delta)`` tuples so callers
        (CLI, tests) can render output. Presentation is not this method's
        responsibility — see ``_print_sync_labels_delta`` in cli.py.
        """
        client = self._get_github_client()
        issues = client.list_issues_by_label(
            "atdd-issue", include_body=False, state="all",
        )
        results: List[Tuple[int, Dict[str, List[str]]]] = []
        for issue in issues:
            number = issue.get("number")
            if not number:
                continue
            delta = self.sync_labels(int(number), dry_run=dry_run)
            results.append((int(number), delta))
        return results

    def _store_create_work_item(
        self, issue_number: int, slug: str, *, status: Optional[str], data: Dict[str, Any],
        discovered_via: str,
    ) -> bool:
        """Backfill a work item into the State Store, stamped as reconciled (#1557).

        Upserts the work item keyed by ``slug`` and links its GitHub issue number as
        the authoritative ``external_ref`` (storage APIs only — no raw SQL, within the
        #1220 boundaries; the link's ON CONFLICT keeps one ref per issue). Preserves an
        existing object's lifecycle ``state`` and merges into its ``data`` so a
        re-registration never clobbers live phase. Returns True on a store write, False
        if the store is unavailable. Never raises.

        THE INVERSION (#1557). This path used to *normalize*: a record created
        out-of-band came out the far side indistinguishable from one authored
        through ``atdd author issue``, so running the repair tool laundered the
        violation away. It now stamps ``work_item_reconciled`` — which is not in
        the sanctioned allowlist — making repair the DETECTOR. A violation can no
        longer be washed away by running the tool, because the tool is what
        records it. ``discovered_via`` is required rather than defaulted so a new
        backfill path must state what it is, not inherit reconcile's story.
        """
        try:
            from atdd.state import provenance
            from atdd.state.db import connect, init_state_store
            from atdd.state.store import StateStore
            from atdd.state.work_item_writer import create_work_item

            conn = connect(init_state_store(start=self.target_dir))
            try:
                # Shared store-first create (#1272): the same foundational writer
                # planner `atdd author issue` uses — DRY across the planner/coach
                # boundary via atdd.state, no cross-archetype import.
                create_work_item(
                    conn, slug, state=status, data=data,
                    github_number=issue_number, ref_source="atdd-issue",
                )
                provenance.record_reconciled(
                    StateStore(conn), slug, discovered_via=discovered_via,
                    payload={"issue_number": issue_number},
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
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: Invalid issue number '{issue_id}'")
            return 1

        try:
            client = self._get_github_client()
            issue = client.get_issue(issue_number)
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        # #1270 slice F: the State Store is authoritative for the terminal
        # COMPLETE/archived state; the manifest mirror write is retired (nothing
        # reads it — slices A–E). Manifest survives only as the cold-start seed.
        self._store_set_status(issue_number, "COMPLETE")
        self._store_update_fields(issue_number, {"archived": date.today().isoformat()})

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

            gate = IssueManager._gate_row(cells)
            if gate:
                gates.append(gate)

        return gates

    @staticmethod
    def _gate_row(cells: List[str]) -> Optional[Dict[str, str]]:
        """One gate-test table row; None when it declares no command."""
        # Extract command — strip backticks
        command = cells[2].strip("`").strip()
        if not command:
            return None

        return {
            "id": cells[0].strip(),
            "phase": cells[1].strip(),
            "command": command,
            "expected": cells[3].strip(),
            "validator": cells[4].strip("`").strip(),
            "status": cells[5].strip(),
        }

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

        headings = {
            "### Created": "created",
            "### Modified": "modified",
            "### Deleted": "deleted",
        }

        # Parse each subsection
        current_key = None
        for line in section_match.group(1).splitlines():
            stripped = line.strip()

            heading = next(
                (key for prefix, key in headings.items() if stripped.startswith(prefix)),
                None,
            )
            if heading:
                current_key = heading
                continue

            if not (stripped.startswith("- ") and current_key):
                continue

            path = IssueManager._artifact_path(stripped)
            if path:
                artifacts[current_key].append(path)

        return artifacts

    @staticmethod
    def _artifact_path(bullet: str) -> Optional[str]:
        """The path an artifact bullet names; None for a template placeholder."""
        path = bullet[2:].strip()
        if path.startswith("(") or not path:
            return None

        # Strip trailing descriptions after ' — ' or ' - ' BEFORE the backticks: the
        # template invites ``- `path` (why)``, and taking the backticks off first left
        # the closing one stranded on the path (#1611 / observed on #1601).
        for sep in (" — ", " - ", " ("):
            if sep in path:
                path = path[:path.index(sep)].strip()
        return path.strip("`").strip() or None

    def _landed_commit(self, issue_number: Optional[int]) -> Optional[str]:
        """The commit that carried this issue's work into main, if it already has.

        ``atdd auto-phase`` runs on ``pull_request: closed``, so by the time the
        COMPLETE gate is evaluated the work is *already* in main and the branch it
        came from is gone. Asking git "what does this branch add on top of main?" then
        has no honest answer — the answer is "nothing", for every path, always. What
        the gate actually wants to know is what the PR **landed**, and GitHub can name
        the commit that did it.

        Returns ``None`` whenever that commit cannot be established or is not present
        in this checkout — no merged PR yet, no GitHub access, a shallow clone — and
        the caller falls back to the pre-merge branch-vs-main comparison.
        """
        if not issue_number:
            return None
        if issue_number in self._landed_commit_cache:
            return self._landed_commit_cache[issue_number]

        sha: Optional[str] = None
        client = self._get_github_client()
        if client is not None:
            try:
                sha = client.get_closing_merge_commit(issue_number)
            except Exception as exc:  # noqa: BLE001 — a gate must not die on a lookup
                logger.debug(
                    "closing merge commit lookup failed",
                    extra={"issue": issue_number, "error": str(exc)},
                )
                sha = None

        # It is only useful if this checkout can see it *and* its parent — the diff
        # the merge landed is `<sha>^..<sha>`.
        if sha:
            present = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
                capture_output=True, text=True, cwd=str(self.target_dir),
            )
            parent = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"{sha}^^{{commit}}"],
                capture_output=True, text=True, cwd=str(self.target_dir),
            )
            if present.returncode != 0 or parent.returncode != 0:
                sha = None

        self._landed_commit_cache[issue_number] = sha
        return sha

    def _verify_artifacts(
        self,
        artifacts: Dict[str, List[str]],
        force: bool = False,
        issue_number: Optional[int] = None,
    ) -> Tuple[bool, List[str]]:
        """Verify artifact claims against git state.

        Before the merge the claims are read against the branch: Created/Deleted in
        ``HEAD``, Modified as ``main...HEAD``. After it — which is when auto-phase
        runs — they are read against the commit the PR landed, because ``main...HEAD``
        is empty by construction once the branch is main (#1611).

        - Created: file must exist in the landed tree
        - Modified: file must have changed in the landed commit
        - Deleted: file must NOT exist in the landed tree
        """
        total = sum(len(v) for v in artifacts.values())
        if total == 0:
            return True, ["  No artifacts declared"]

        landed = self._landed_commit(issue_number)
        all_valid = True
        messages: List[str] = []
        if landed:
            messages.append(f"  Verifying against the commit PR landed: {landed[:8]}")
        for kind in ("created", "modified", "deleted"):
            valid, group_messages = self._verify_artifact_group(
                kind, artifacts[kind], force, landed=landed,
            )
            all_valid = all_valid and valid
            messages.extend(group_messages)

        return all_valid, messages

    # kind -> (message prefix, check mode, git prints output when satisfied,
    #          satisfied word, unsatisfied word)
    #
    # "tree" asks whether the path is in a revision's tree, "diff" whether a
    # revision changed it; the revisions themselves depend on whether the work has
    # landed yet, so they are resolved per run rather than baked in here (#1611).
    _ARTIFACT_CHECKS = {
        "created": ("  Created:  ", "tree", True, "EXISTS", "MISSING"),
        "modified": ("  Modified: ", "diff", True, "CHANGED", "NO CHANGES"),
        "deleted": ("  Deleted:  ", "tree", False, "CONFIRMED GONE", "STILL EXISTS"),
    }

    @staticmethod
    def _artifact_check_argv(mode: str, landed: Optional[str]) -> List[str]:
        """The git command that answers ``mode``, at the point in history that has it."""
        if mode == "tree":
            return ["git", "ls-tree", landed or "HEAD", "--"]
        if landed:
            return ["git", "diff", f"{landed}^", landed, "--"]
        return ["git", "diff", "main...HEAD", "--"]

    def _verify_artifact_group(
        self,
        kind: str,
        paths: List[str],
        force: bool,
        landed: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """Verify one artifact group (created / modified / deleted) against git."""
        prefix, mode, expect_output, satisfied, unsatisfied = self._ARTIFACT_CHECKS[kind]
        argv = self._artifact_check_argv(mode, landed)
        against = f"in {landed[:8]}" if landed else "vs main"

        all_valid = True
        messages: List[str] = []
        for path in paths:
            if force:
                messages.append(f"{prefix}{path} — SKIPPED (--force)")
                continue

            result = subprocess.run(
                argv + [path],
                capture_output=True, text=True, cwd=str(self.target_dir),
            )
            if bool(result.stdout.strip()) == expect_output:
                messages.append(f"{prefix}{path} — {satisfied}")
            else:
                suffix = f" {against}" if mode == "diff" else ""
                messages.append(f"{prefix}{path} — {unsatisfied}{suffix}")
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
        """Check that the work is not sitting on a stale base.

        Two states satisfy that, and the gate used to recognise only the first:

        - ``origin/main`` is an ancestor of ``HEAD`` — the branch already carries
          everything main has, which is what "rebased" means before the merge;
        - ``HEAD`` is an ancestor of ``origin/main`` — the work has *landed*, so
          there is nothing to rebase onto. This is the state ``atdd auto-phase``
          runs in, on PR close, and demanding the first condition there is a race
          nobody can win: every PR that merges after this one puts main ahead of
          the commit under test, and the gate reports "behind main" for work that
          is already in main (#1611).

        Genuine divergence — unmerged commits on a stale base, so neither is an
        ancestor of the other — still fails.

        Returns:
            (passed, message)
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

        landed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"],
            capture_output=True, text=True, cwd=str(self.target_dir), timeout=10,
        )
        if landed.returncode == 0:
            return True, "  Rebase check: PASS (work is already contained in origin/main)"

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
        except subprocess.CalledProcessError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            messages.append("  Smoke gate: SKIPPED (origin/main unreachable)")
            return True, messages
        except Exception as exc:  # noqa: BLE001 — fail-open on git breakage  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        """Verify the release gate against the State Store version (#1172).

        Post-#1172 the authoritative release version lives in the State Store's
        singleton ``release`` object (``atdd state version show``), NOT a static
        ``version = "..."`` line in ``pyproject.toml``. ``pyproject.toml`` is now
        *dynamic* (``dynamic = ["version"]`` resolved by the in-tree build
        backend from the store), so it carries no static version line to parse —
        the old pyproject-read / git-diff-vs-main / git-tag checks are obsolete
        (tag + publish are operator-coordinated post-merge per
        ``CLAUDE.md::release``). The gate now PASSES when the store resolves a
        real release version and FAILS (pointing at ``atdd state version bump``)
        when only the local fallback is resolvable.

        Returns ``(passed, messages)`` instead of raising, mirroring the other
        ``_verify_*`` gate helpers.
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

        # Read the authoritative release version from the State Store (#1172).
        # ``emit`` is non-raising and returns ``LOCAL_FALLBACK_VERSION`` when no
        # release version is resolvable — the same contract as the build hook.
        from atdd.state import version as _v
        from atdd.state.db import connect, init_state_store

        try:
            db = init_state_store(start=self.target_dir)
            conn = connect(db)
            try:
                version = _v.emit(conn)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 — logged, then surfaced as a gate failure
            logger.warning(
                "release gate: State Store version read failed",
                extra={"error": str(exc), "action": "gate_fail"},
            )
            messages.append(f"  Release version: State Store read failed — {exc}")
            messages.append(
                "  Fix: seed/bump the version — "
                "atdd state version bump --class PATCH|MINOR|MAJOR"
            )
            return False, messages

        if version == _v.LOCAL_FALLBACK_VERSION:
            messages.append(
                f"  Release version: {version} (local fallback — no release "
                "version set in the State Store)"
            )
            messages.append(
                "  Fix: bump the version — "
                "atdd state version bump --class PATCH|MINOR|MAJOR"
            )
            return False, messages

        messages.append(f"  Release version: {version} (State Store SoT, #1172) — OK")
        return True, messages

    def _validate_train_against_trains_yaml(
        self, train_value: str,
    ) -> Tuple[bool, List[str]]:
        """Cross-reference train value against _trains.yaml.

        Returns (valid, messages). If _trains.yaml doesn't exist, passes (no constraint).
        """
        plan_dir = self.target_dir / "plan"
        valid_ids = self._registered_train_ids(plan_dir)

        if not valid_ids:
            # No trains defined — skip cross-ref
            return True, []

        if train_value in valid_ids:
            return True, [f"  Train: {train_value} — VALID (in _trains.yaml)"]

        return False, [f"  Train: {train_value} — NOT FOUND in _trains.yaml"]

    @staticmethod
    def _registered_train_ids(plan_dir: Path) -> set:
        """Every known train id: the _trains.yaml registry plus loose _trains/ stems."""
        valid_ids: set = set()

        trains_file = plan_dir / "_trains.yaml"
        if trains_file.exists():
            with open(trains_file) as f:
                data = yaml.safe_load(f) or {}
            valid_ids.update(IssueManager._train_ids_in_registry(data))

        trains_dir = plan_dir / "_trains"
        if trains_dir.exists():
            valid_ids.update(f.stem for f in trains_dir.glob("*.yaml"))

        return valid_ids

    @staticmethod
    def _train_ids_in_registry(data: dict) -> set:
        """Train ids inside the nested {theme: {category: [train]}} registry shape."""
        train_ids: set = set()
        for categories in data.get("trains", {}).values():
            if not isinstance(categories, dict):
                continue
            for trains_list in categories.values():
                if not isinstance(trains_list, list):
                    continue
                train_ids.update(t.get("train_id", "") for t in trains_list)

        train_ids.discard("")
        return train_ids

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

        resolved = self._resolve_issue(issue_id)
        if resolved is None:
            return 1
        issue_number, issue, client = resolved

        updated = []

        # Status transition with validation
        if status:
            status = status.upper()
            current_labels, current_status = self._read_phase_labels(issue)
            issue_body = issue.get("body", "") or ""

            if not self._transition_gates_pass(
                issue_number, issue_id, issue_body, current_status, status,
                branch, train, force,
            ):
                return 1

            # #1452: STORE FIRST, LABEL AS ITS PROJECTION. The order matters and
            # is load-bearing, not cosmetic. `atdd:<PHASE>` is a *rendering* of
            # `objects.state`, so the source of truth must move before the
            # artifact derived from it. Writing the label first is how 236 issues
            # (56%) ended up carrying a phase their store never earned: the
            # projection landed, something failed after it, and the label was
            # left asserting a transition that never happened.
            self._update_manifest_status(issue_number, status)

            # Project the store's new state onto GitHub. This is the sole
            # authoritative `atdd:*` label write in the codebase — enforced by
            # coach.issue.phase-label-projection-only.
            self._write_phase_label(client, issue_number, current_labels, status)
            updated.append(f"status: {status}")

        # Validate branch prefix (every branch = a worktree)
        if branch and not self._branch_prefix_allowed(branch):
            return 1

        updated.extend(
            self._apply_text_updates(
                issue_number, branch, train, feature_urn, archetypes
            )
        )

        if updated:
            print(f"Updated #{issue_number}:")
            for u in updated:
                print(f"  {u}")
        else:
            print("Nothing to update.")

        return 0

    def _resolve_issue(self, issue_id: str) -> Optional[Tuple[int, dict, Any]]:
        """(issue_number, issue, client). None (after printing) when it cannot be read."""
        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(issue_id)
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: Invalid issue number '{issue_id}'")
            return None

        # Projects v2 board sync is decommissioned (#1051). The lifecycle state
        # machine runs entirely on the ``atdd:<phase>`` label (REST) plus the
        # local .atdd/manifest.yaml mirror — no GraphQL board reads or writes.
        try:
            client = self._get_github_client()
            issue = client.get_issue(issue_number)
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: {e}")
            return None

        return issue_number, issue, client

    @staticmethod
    def _write_phase_label(
        client: Any, issue_number: int, current_labels: List[str], status: str
    ) -> None:
        """Swap the atdd:<phase> label — the sole authoritative phase write (#1051)."""
        phase_labels = [
            l for l in current_labels if l.startswith("atdd:") and l != "atdd-issue"
        ]
        if phase_labels:
            client.remove_label(issue_number, phase_labels)
        client.add_label(issue_number, [f"atdd:{status}"])

    @staticmethod
    def _branch_prefix_allowed(branch: str) -> bool:
        """Every branch is a git worktree, so it must carry an allowed prefix."""
        allowed = tuple(f"{p}/" for p in ALLOWED_BRANCH_PREFIXES)
        if any(branch.startswith(p) for p in allowed):
            return True

        print(
            f"Error: Branch '{branch}' must start with an allowed prefix: "
            f"{', '.join(allowed)}\n"
            f"Each branch is a git worktree. Example: feat/my-feature"
        )
        return False

    def _apply_text_updates(
        self,
        issue_number: int,
        branch: Optional[str],
        train: Optional[str],
        feature_urn: Optional[str],
        archetypes: Optional[str],
    ) -> List[str]:
        """Mirror the text fields into the local manifest; names what changed.

        Issue #1051: the Projects v2 board that previously carried branch /
        train / feature / archetypes is decommissioned.
        """
        text_updates = {
            "branch": branch,
            "train": train,
            "feature_urn": feature_urn,
            "archetypes": archetypes,
        }
        manifest_text = {k: v for k, v in text_updates.items() if v}
        if not manifest_text:
            return []

        self._update_manifest_fields(issue_number, manifest_text)
        return [f"{key}: {value}" for key, value in manifest_text.items()]

    def reproject_phase_label(self, issue_number: int) -> Optional[str]:
        """Re-render the ``atdd:<PHASE>`` label from ``objects.state`` (#1338).

        The repair counterpart of :meth:`update`. ``update`` *advances* the
        lifecycle — store first, label projected from it. This method advances
        nothing: it re-derives the projection from the store the record already
        has, for a record whose label drifted away from it.

        It is deliberately NOT a transition. ``update(status=<store phase>)``
        cannot express "make the label agree again" — the phase machine refuses
        a self-transition, which is precisely why the 236 drifted records were
        unrepairable (see #1338: ``Cannot transition from COMPLETE to COMPLETE``).

        It lives here, on ``IssueManager``, because ``issue.py`` is the sole
        path allowed to author an ``atdd:*`` label — enforced by
        ``coach.phase-label.projection-only`` (#1452). The direction of truth is
        never inverted: the store is read, never written.

        Returns the phase projected, or ``None`` when the store does not know
        this issue (which the caller must treat as "cannot decide", never as
        "no phase").
        """
        from atdd.coach.commands.auto_phase import read_store_phase

        store_phase = read_store_phase(issue_number, self.target_dir)
        if not store_phase:
            return None

        resolved = self._resolve_issue(str(issue_number))
        if resolved is None:
            return None
        _, issue, client = resolved

        current_labels, current_phase = self._read_phase_labels(issue)
        if current_phase == store_phase:
            return store_phase

        self._write_phase_label(client, issue_number, current_labels, store_phase)
        return store_phase

    # -------------------------------------------------------------------------
    # Transition gates (each prints its own diagnosis; False blocks the write)
    # -------------------------------------------------------------------------

    @staticmethod
    def _read_phase_labels(issue: dict) -> Tuple[List[str], str]:
        """(all labels, current phase). Phase is UNKNOWN when no atdd:<phase> label."""
        current_labels = [l["name"] for l in issue.get("labels", [])]
        for label in current_labels:
            if label.startswith("atdd:") and label != "atdd-issue":
                return current_labels, label.split(":")[1]
        return current_labels, "UNKNOWN"

    def _transition_gates_pass(
        self,
        issue_number: int,
        issue_id: str,
        issue_body: str,
        current_status: str,
        status: str,
        branch: Optional[str],
        train: Optional[str],
        force: bool,
    ) -> bool:
        """Every gate guarding this phase transition, in order. False = blocked."""
        if not self._gate_transition_allowed(current_status, status):
            return False

        if not self._gate_train_required(issue_number, issue_id, issue_body, status, train):
            return False

        if status == "PLANNED" and not self._gate_pr_exists(
            issue_number, issue_id, branch, force
        ):
            return False

        # Train cross-reference applies regardless of --force (identity enforcement)
        if train and not self._gate_train_crossref(train):
            return False

        if (status == "REFACTOR" and not force
                and not self._gate_smoke_evidence(issue_number, issue_id)):
            return False

        if status == "COMPLETE" and not self._gate_complete(
            issue_number, issue_id, issue_body, force
        ):
            return False

        return True

    def _gate_transition_allowed(self, current_status: str, status: str) -> bool:
        """The phase machine permits current_status -> status."""
        allowed = self.VALID_TRANSITIONS.get(current_status, set())
        if status not in allowed and current_status != "UNKNOWN":
            print(f"Error: Cannot transition from {current_status} to {status}")
            print(f"  Allowed: {', '.join(sorted(allowed)) or '(terminal state)'}")
            return False
        return True

    def _gate_train_required(
        self,
        issue_number: int,
        issue_id: str,
        issue_body: str,
        status: str,
        train: Optional[str],
    ) -> bool:
        """E008: implementation-type issues need a valid train past PLANNED.

        Other types (cleanup, analysis, planning, tracking) are train-optional.
        """
        issue_type = self._parse_issue_type(issue_body)
        post_planned = {"RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"}
        train_required = issue_type in self.TRAIN_REQUIRED_TYPES if issue_type else True

        if status not in post_planned or not train_required or train:
            return True

        # Train lineage is read from the local manifest mirror (#1051), never the
        # Projects v2 board. An absent/TBD train fails loudly; a present train is
        # cross-referenced against plan/_trains.yaml (no board fallback recovers
        # an unknown value).
        current_train = (self._manifest_train(issue_number) or "").strip()
        if not current_train or current_train.upper() == "TBD":
            self._print_train_required_help(issue_id, issue_type, status, current_train)
            return False

        train_valid, train_messages = self._validate_train_against_trains_yaml(current_train)
        for msg in train_messages:
            print(msg)
        if not train_valid:
            print(f"\nError: Train '{current_train}' (from manifest) not found in _trains.yaml")
            print(f"  Fix: Use a valid train_id or add the train to plan/_trains.yaml")
            return False
        return True

    @staticmethod
    def _print_train_required_help(
        issue_id: str, issue_type: Optional[str], status: str, current_train: str
    ) -> None:
        """Explain how to attach a train before transitioning past PLANNED."""
        for line in (
            f"Error: Train field required for {issue_type or 'unknown'} type before transitioning to {status}",
            f"  Current Train: {current_train or '(empty)'}",
            "  Fix:",
            "    1. cd into the issue's worktree (find via: git worktree list | grep <branch>):",
            "       cd /path/to/<feat-or-fix>-<slug>",
            "    2. Pick a train_id from plan/_trains.yaml::trains[].train_id (e.g. \"0001-self-compliance-validate\")",
            "    3. Run:",
            f"       atdd update {issue_id} --train <train_id>   # then: atdd coach transition {issue_id} {status}",
            "  Why train: implementation-type issues require lineage to a Train past PLANNED",
            "  so cross-cutting work threads to a shared journey. (See `plan/_trains.yaml`.)",
        ):
            print(line)

    def _gate_pr_exists(
        self, issue_number: int, issue_id: str, branch: Optional[str], force: bool
    ) -> bool:
        """Issue #478 — PR-existence gate at INIT -> PLANNED.

        ``atdd branch`` defers PR creation; ``atdd pr`` opens it post-commit. A
        PLANNED transition is blocked when the issue's branch has no open PR.
        --force bypasses the gate with a ``::warning::``.
        """
        gate_branch = branch or (self._manifest_branch(issue_number) or "").strip()
        if not gate_branch:
            return True

        pr_exists, pr_messages = self._validate_pr_exists_for_branch(gate_branch)
        for msg in pr_messages:
            print(msg)
        if pr_exists:
            return True

        if force:
            print(
                "::warning::PR-existence gate bypassed (--force); "
                f"branch '{gate_branch}' has no open PR."
            )
            return True

        self._print_pr_required_help(issue_id, gate_branch)
        return False

    @staticmethod
    def _print_pr_required_help(issue_id: str, gate_branch: str) -> None:
        """Explain how to open the PR that the PLANNED gate requires."""
        for line in (
            f"\nError: No open PR found for branch "
            f"'{gate_branch}' — cannot transition to PLANNED.",
            "  Fix:",
            "    1. cd into the issue's worktree",
            "       (find via: git worktree list | grep <branch>):",
            f"       cd /path/to/<feat-or-fix>-<slug>",
            "    2. Make at least one commit on the branch:",
            "       git add <files> && git commit -m \"<message>\"",
            "       git push",
            f"    3. atdd pr {issue_id}",
            f"    4. atdd coach transition {issue_id} PLANNED",
            "  Why PR: PLANNED transition assumes the branch is reviewable;",
            "          a draft PR is the canonical review surface. (See #478.)",
            f"  Bypass: atdd coach transition {issue_id} PLANNED --force",
        ):
            print(line)

    def _gate_train_crossref(self, train: str) -> bool:
        """The --train value names a train registered in _trains.yaml."""
        train_valid, train_messages = self._validate_train_against_trains_yaml(train)
        for msg in train_messages:
            print(msg)
        if not train_valid:
            print(f"\nError: Train '{train}' not found in _trains.yaml")
            print(f"  Fix: Use a valid train_id or add the train to plan/_trains.yaml")
            return False
        return True

    def _gate_smoke_evidence(self, issue_number: int, issue_id: str) -> bool:
        """COACH-RATCHET-PRES-001 (issue #358): SMOKE -> REFACTOR needs smoke evidence.

        Required when the PR includes a presentation-layer ratchet improvement
        >20%. The detector runs git diff against origin/main; absence of
        evidence blocks the transition.
        """
        gate_ok, gate_messages = self._check_smoke_evidence_gate(issue_number)
        for msg in gate_messages:
            print(msg)
        if not gate_ok:
            print(f"\nError: Presentation-layer ratchet detected — smoke evidence required")
            print(f"  Fix: atdd validate coder --smoke-required {issue_number}")
            print(f"  Bypass: atdd update {issue_id} --status REFACTOR --force")
            return False
        return True

    def _gate_complete(
        self, issue_number: int, issue_id: str, issue_body: str, force: bool
    ) -> bool:
        """Everything COMPLETE requires: rebase, gate tests, artifacts, release."""
        return (
            self._gate_rebased(issue_id, force)
            and self._gate_tests(issue_number, issue_id, issue_body, force)
            and self._gate_artifacts(issue_number, issue_id, issue_body, force)
            and self._gate_release(issue_number, issue_id, force)
        )

    def _gate_rebased(self, issue_id: str, force: bool) -> bool:
        """The branch is not behind main."""
        if force:
            print(f"  Bypassing rebase check (--force)")
            return True

        rebase_ok, rebase_msg = self._check_rebased_on_main()
        if rebase_msg:
            print(rebase_msg)
        if not rebase_ok:
            print(f"\nError: Branch is behind main — cannot transition to COMPLETE")
            print(f"  Fix: git fetch origin main && git rebase origin/main")
            print(f"  Bypass: atdd update {issue_id} --status COMPLETE --force")
            return False
        return True

    def _gate_tests(
        self, issue_number: int, issue_id: str, issue_body: str, force: bool
    ) -> bool:
        """The gate tests the issue body declares all pass."""
        gates = self._parse_gate_tests(issue_body)
        if not gates:
            if not force:
                print(f"\n  Warning: No gate tests found in issue body")
            return True

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
            return False

        if not force:
            print()  # blank line after gate results
        return True

    def _gate_artifacts(
        self, issue_number: int, issue_id: str, issue_body: str, force: bool
    ) -> bool:
        """The artifacts the issue body declares all exist."""
        artifacts = self._parse_artifacts(issue_body)
        artifact_count = sum(len(v) for v in artifacts.values())
        if artifact_count == 0:
            if not force:
                print(f"  Warning: No artifacts declared in issue body")
            return True

        if force:
            print(f"  Bypassing artifact verification (--force)")
        else:
            print(f"Verifying {artifact_count} artifacts for #{issue_number}:")

        artifacts_valid, artifact_messages = self._verify_artifacts(
            artifacts, force=force, issue_number=issue_number,
        )
        for msg in artifact_messages:
            print(msg)

        if not artifacts_valid:
            print(f"\nError: Artifact verification failed — cannot transition to COMPLETE")
            print(f"  Fix: Update ## Artifacts section with correct paths")
            print(f"  Bypass: atdd update {issue_id} --status COMPLETE --force")
            return False

        if not force:
            print()
        return True

    def _gate_release(self, issue_number: int, issue_id: str, force: bool) -> bool:
        """The release gate: version bumped, committed and tagged."""
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
            return False

        if not force:
            print()
        return True

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
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: Invalid issue number '{issue_id}'")
            return 1

        try:
            client = self._get_github_client()
            subs = client.get_sub_issues(issue_number)
        except (GitHubClientError, Exception) as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        """Backfill every open GitHub atdd-issue missing from the State Store.

        Self-heal path (#775): the State Store is the local registry and the
        GitHub issue is the source of truth. Any issue labelled `atdd-issue` that
        is open on GitHub but absent from the store is synthesised and created as
        a work item. Existing entries are left untouched (idempotent). #1270 Slice
        G: the ``.atdd/manifest.yaml`` mirror was deleted — the store is the sole
        registry, so no manifest read/write happens here.

        #1557: a backfill is no longer silent normalization. Each record it
        synthesises is stamped ``work_item_reconciled`` — unsanctioned provenance
        — so ``atdd validate`` reports it afterwards. Reconcile still repairs the
        registry; it just stops pretending the repair never happened.

        Returns 0 on success, 1 on hard error.
        """
        # Initialisation guard (#1270 Slice G): key on ``.atdd/config.yaml`` (the
        # control-root marker that replaced the deleted manifest). Bailing here —
        # before any gh/git call — keeps the verb hermetic in an uninitialised
        # tree and never touches live GitHub.
        if not self.config_file.exists():
            print("Error: .atdd/config.yaml not found. Run `atdd init` first.")
            return 1

        gh_issues = self._fetch_open_atdd_issues()
        if gh_issues is None:
            return 1

        registered = self._registered_issue_numbers()

        added = 0
        for issue in gh_issues:
            number = issue.get("number")
            if number is None or number in registered:
                continue

            slug = self._slug_from_title(issue.get("title", ""), number)
            status = self._phase_from_labels(issue.get("labels", []))
            created_raw = issue.get("createdAt", "")

            entry = {
                "id": str(number),
                "slug": slug,
                "file": None,
                "issue_number": number,
                "type": "implementation",
                "status": status,
                "created": created_raw[:10] if created_raw else str(date.today()),
                "archived": None,
            }
            # The State Store is the sole registry (#1270 Slice G) — create the
            # backfilled work item there (slug + github external_ref).
            self._store_create_work_item(
                number, slug, status=status,
                data={k: v for k, v in entry.items() if k not in ("slug", "status")},
                discovered_via="atdd coach reconcile",
            )
            registered.add(number)
            added += 1
            print(f"  Backfilled: #{number} {slug}  [provenance: reconciled]")

        if added == 0:
            print("reconcile: State Store is up-to-date — no missing issues found.")
            return 0

        print(f"reconcile: added {added} issue(s) to the State Store")
        print(
            f"reconcile: {added} record(s) stamped 'work_item_reconciled' — they were "
            "created outside the sanctioned authoring path and `atdd validate` will "
            "report them (#1557). Backfill repairs the registry; it does not confer "
            "provenance."
        )
        return 0

    @staticmethod
    def _fetch_open_atdd_issues() -> Optional[List[dict]]:
        """Open atdd-issues on GitHub. None (after printing) when gh fails."""
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
            return None

        try:
            return json.loads(result.stdout) or []
        except (json.JSONDecodeError, ValueError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-19
            print(f"Error: could not parse gh output: {exc}")
            return None

    def _registered_issue_numbers(self) -> set:
        """Issue numbers already registered in the State Store; empty when unreadable."""
        try:
            from atdd.state.work_item_reader import WorkItemReader

            with WorkItemReader(control_root=self.target_dir) as reader:
                return {
                    entry["issue_number"]
                    for entry in reader.all_work_items()
                    if entry.get("issue_number") is not None
                }
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-19
            logger.debug("reconcile: store read failed; treating store as empty",
                         extra={"error": str(exc)})
            return set()

    @staticmethod
    def _slug_from_title(title: str, number: int) -> str:
        """A kebab slug from an issue title, stripping the type prefix and (#N) suffix."""
        slug_raw = re.sub(r"^\w+(?:\([^)]*\))?:\s*", "", title)
        slug_raw = re.sub(r"\s*\(#\d+\)\s*$", "", slug_raw)
        return re.sub(r"[^a-z0-9]+", "-", slug_raw.lower()).strip("-") or f"issue-{number}"

    @staticmethod
    def _phase_from_labels(labels: List[dict]) -> str:
        """The atdd:<phase> a label set carries; INIT when it carries none."""
        for label in labels:
            name = label.get("name", "")
            if name.startswith("atdd:"):
                return name[5:]
        return "INIT"

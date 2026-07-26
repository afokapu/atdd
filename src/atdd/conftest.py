"""
Root conftest for unified test reporting across all test categories.
"""
import re
import subprocess
import pytest

# Activate pytester at the test-root conftest. The substrate plugin's
# integration tests (issue #411) spin up an inner pytest session via
# ``pytester.runpytest`` to verify hook behavior end-to-end. pytest 7+
# removed support for ``pytest_plugins`` in non-rootdir conftests, so the
# fixture has to be enabled here. pytester is a no-op for sessions that
# never touch the fixture.
# ``atdd.state.live_store_guard_plugin`` carries the #1582 live-State-Store
# pollution guard (G1 env neutralization, G2 sqlite3.connect trap, G3 fingerprint
# backstop). It is registered as a plugin rather than inlined here for two
# reasons: the fault-injection tests enable the SHIPPED plugin in a real child
# pytest session (``-p atdd.state.live_store_guard_plugin``) instead of
# reimplementing the fixtures, so what is proven to fire is what actually runs;
# and pytest_plugins is only honored in the rootdir conftest, which this is.
pytest_plugins = ["pytester", "atdd.state.live_store_guard_plugin"]

try:
    import pytest_html as _pytest_html_check  # noqa: F401
    _HAS_PYTEST_HTML = True
except ImportError:
    _HAS_PYTEST_HTML = False


# ---------------------------------------------------------------------------
# Repo-root core.bare + HEAD pollution guard (issue #771)
#
# Covers ALL test dirs under src/atdd — not just validators/.
# The existing session-scoped guard in coach/validators/conftest.py covers
# only that sub-directory; tests in commands/, handlers/, utils/, etc. were
# unguarded and could write core.bare=true to the shared .git/config.
#
# Per-test (function) scope lets the teardown name the exact offending test
# via request.node.nodeid and restore core.bare BEFORE asserting so the
# rest of the session runs in a clean state.
# ---------------------------------------------------------------------------

def _repo_git(*args: str) -> str:
    """Run a git command at the repo root (wherever git resolves .git from cwd)."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _restore_core_bare(value: str) -> None:
    """Restore core.bare to `value` (empty string → unset the key)."""
    if value:
        subprocess.run(
            ["git", "config", "core.bare", value],
            capture_output=True,
        )
    else:
        subprocess.run(
            ["git", "config", "--unset", "core.bare"],
            capture_output=True,
        )


@pytest.fixture(autouse=True)
def _git_repo_pollution_guard(request):
    """Per-test guard: snapshot core.bare and HEAD, restore and fail if mutated.

    Snapshots ``git config core.bare`` and ``git rev-parse HEAD`` before the
    test runs.  After the test:

    1. Reads the current values.
    2. If core.bare changed: **restores it immediately** (before asserting) so
       subsequent tests and the developer's repo are not poisoned.
    3. Asserts both values are unchanged, naming the offending test via
       ``request.node.nodeid`` so the developer can find and isolate the
       polluter.

    Any test that calls ``git config core.bare true`` (or equivalent) against
    the live repo rather than a ``tmp_path`` fixture repo will be caught,
    named, and cleaned up here (issue #771).
    """
    head_before = _repo_git("rev-parse", "HEAD")
    bare_before = _repo_git("config", "core.bare")

    yield

    bare_after = _repo_git("config", "core.bare")
    head_after = _repo_git("rev-parse", "HEAD")

    # Restore core.bare FIRST so the session continues clean even if we assert
    if bare_before != bare_after:
        _restore_core_bare(bare_before)

    assert bare_before == bare_after, (
        f"Test {request.node.nodeid!r} mutated core.bare on the active worktree.\n"
        f"  core.bare before: {bare_before!r}\n"
        f"  core.bare after:  {bare_after!r}\n"
        "core.bare has been restored automatically.\n"
        "Isolate the git config call to tmp_path: use\n"
        "  subprocess.run(['git', '-C', str(tmp_path), 'config', 'core.bare', 'true'])\n"
        "or\n"
        "  subprocess.run(['git', 'config', 'core.bare', 'true'], cwd=str(tmp_path))"
    )
    assert head_before == head_after, (
        f"Test {request.node.nodeid!r} added phantom commits to the active worktree.\n"
        f"  HEAD before: {head_before}\n"
        f"  HEAD after:  {head_after}\n"
        "A test ran git commit against the live repo rather than a tmp_path fixture.\n"
        "Find it with: git log --oneline HEAD~10..HEAD"
    )


# ---------------------------------------------------------------------------
# ATDD<N> cmux workspace leak guard (issue #771 — broadened scope)
#
# Any test that invokes `atdd coach <N>` without --dry-run will spawn a real
# ATDD<N> cmux workspace and leave it behind after the session. This session-
# scoped guard snapshots ATDD<N>-pattern workspaces before the session, detects
# any new ones after, closes them, and fails so the developer can add --dry-run.
#
# Session scope (not function) because cmux list-workspaces takes ~200ms —
# per-test overhead on 2800+ coach tests would be unacceptable.
# ---------------------------------------------------------------------------

def _list_atdd_issue_workspaces() -> dict[str, str]:
    """Return {name: ref} for ATDD<N>-prefixed cmux workspaces (issue-specific).

    Parses `cmux list-workspaces` output lines like:
      * workspace:1  ATDD  [selected]
        workspace:5  ✳ ATDD358
    Only names matching ^ATDD\\d+ are returned (not bare 'ATDD' or 'ATDD-atdd-plan-spec').
    Returns {} when cmux is unavailable or times out.
    """
    try:
        result = subprocess.run(
            ["cmux", "list-workspaces"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        workspaces: dict[str, str] = {}
        for line in result.stdout.splitlines():
            ref_match = re.search(r"(workspace:\d+)", line)
            if not ref_match:
                continue
            ref = ref_match.group(1)
            after_ref = line[ref_match.end():].strip()
            name = re.sub(r"^[*✳\s]+", "", after_ref).strip()
            name = re.sub(r"\s*\[selected\].*$", "", name).strip()
            if re.match(r"^ATDD\d+", name):
                workspaces[name] = ref
        return workspaces
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return {}


@pytest.fixture(scope="session", autouse=True)
def _cmux_workspace_leak_guard():
    """Session guard: snapshot ATDD<N> cmux workspaces; close+fail on any new ones after.

    Only fires when cmux is available. Gracefully no-ops when cmux is absent
    (CI without a multiplexer) so the guard never blocks non-local runs.
    """
    before = _list_atdd_issue_workspaces()
    yield
    after = _list_atdd_issue_workspaces()
    leaked = {k: v for k, v in after.items() if k not in before}
    if leaked:
        for ref in leaked.values():
            subprocess.run(
                ["cmux", "close-workspace", "--workspace", ref],
                capture_output=True,
            )
        pytest.fail(
            f"Test session leaked ATDD cmux workspace(s): {sorted(leaked.keys())}\n"
            "Each leaked workspace was closed automatically.\n"
            "Fix: add --dry-run to tests that invoke 'atdd coach <N>' against the live repo,\n"
            "or tear down workspaces explicitly in test teardown (issue #771)."
        )


def pytest_configure(config):
    """Add custom metadata and markers."""
    # ATDD lifecycle markers
    config.addinivalue_line("markers", "planner: Planning phase validation tests")
    config.addinivalue_line("markers", "tester: Testing phase validation tests (contracts-as-code)")
    config.addinivalue_line("markers", "coder: Coding phase validation tests")
    config.addinivalue_line("markers", "coach: Coach validation tests")
    config.addinivalue_line("markers", "e2e: End-to-end validation tests")

    # Legacy/component markers
    config.addinivalue_line("markers", "platform: Platform validation tests")
    config.addinivalue_line("markers", "github_api: Tests requiring live GitHub API access")
    config.addinivalue_line("markers", "backend: Backend Python tests")
    config.addinivalue_line("markers", "frontend: Frontend Preact/TypeScript tests")
    config.addinivalue_line("markers", "agents: Agent behavior tests")
    config.addinivalue_line("markers", "schemas: Schema validation tests")
    config.addinivalue_line("markers", "utils: Utility and runtime tests")
    config.addinivalue_line("markers", "contracts: Contract tests")
    config.addinivalue_line("markers", "telemetry: Telemetry tests")

    # Custom metadata for HTML report
    if hasattr(config, '_metadata'):
        config._metadata.update({
            "Project": "Wagons Platform",
            "Test Categories": "Platform, Backend, Agents, Schemas, Utils",
            "Environment": "Development",
        })


def pytest_collection_modifyitems(items):
    """Auto-assign category markers based on file path."""
    for item in items:
        # Get test file path
        test_path = str(item.fspath)

        # Assign ATDD lifecycle markers
        if "atdd/planner/" in test_path:
            item.add_marker(pytest.mark.planner)
        elif "atdd/tester/" in test_path:
            item.add_marker(pytest.mark.tester)
        elif "atdd/coder/" in test_path:
            item.add_marker(pytest.mark.coder)

        # Assign legacy/component markers
        elif "platform_validation" in test_path:
            item.add_marker(pytest.mark.platform)
        elif "python/" in test_path:
            item.add_marker(pytest.mark.backend)
        elif ".claude/agents/" in test_path:
            item.add_marker(pytest.mark.agents)
        elif ".claude/schemas/" in test_path:
            item.add_marker(pytest.mark.schemas)
        elif ".claude/utils/" in test_path:
            item.add_marker(pytest.mark.utils)
        elif "contracts/" in test_path:
            item.add_marker(pytest.mark.contracts)
        elif "telemetry/" in test_path:
            item.add_marker(pytest.mark.telemetry)
        elif "web/" in test_path:
            item.add_marker(pytest.mark.frontend)


# ---------------------------------------------------------------------------
# pytest-html hooks (only defined when pytest-html is installed)
# ---------------------------------------------------------------------------
if _HAS_PYTEST_HTML:
    def pytest_html_report_title(report):
        """Customize HTML report title."""
        report.title = "Wagons Platform - Comprehensive Test Report"

    def pytest_html_results_table_header(cells):
        """Add category column to results table."""
        cells.insert(1, '<th>Category</th>')

    def pytest_html_results_table_row(report, cells):
        """Add category to each test row."""
        category = "Unknown"

        if hasattr(report, 'nodeid'):
            path = report.nodeid

            # ATDD lifecycle categories
            if 'atdd/planner/' in path:
                category = '📋 Planner'
            elif 'atdd/tester/' in path:
                category = '🧪 Tester'
            elif 'atdd/coder/' in path:
                category = '⚙️ Coder'
            # Legacy categories
            elif 'platform_validation' in path:
                category = '🗺️ Platform'
            elif 'python/' in path:
                category = '🐍 Backend'
            elif '.claude/agents/' in path:
                category = '🤖 Agents'
            elif '.claude/schemas/' in path:
                category = '📋 Schemas'
            elif '.claude/utils/' in path:
                category = '🔧 Utils'
            elif 'contracts/' in path:
                category = '📄 Contracts'
            elif 'telemetry/' in path:
                category = '📊 Telemetry'
            elif 'web/' in path:
                category = '💙 Frontend'

        cells.insert(1, f'<td>{category}</td>')

    def pytest_html_results_summary(prefix, summary, postfix):
        """Add custom summary header."""
        prefix.extend([
            '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); '
            'padding: 30px; border-radius: 10px; color: white; margin: 20px 0; text-align: center;">'
            '<h1 style="margin: 0 0 15px 0; font-size: 32px;">🚀 Wagons Platform Test Suite</h1>'
            '<p style="margin: 0; opacity: 0.9; font-size: 18px;">Comprehensive validation across all components</p>'
            '<div style="margin-top: 20px; display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">'
            '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🗺️ Platform</span>'
            '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🐍 Backend</span>'
            '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🤖 Agents</span>'
            '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">📋 Schemas</span>'
            '<span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px;">🔧 Utils</span>'
            '</div>'
            '</div>'
        ])

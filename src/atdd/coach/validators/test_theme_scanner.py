"""
Platform tests: Theme scanner (plan/ tree + repo-metadata discovery).

Issue: #291 (feat(planner): support custom themes via .atdd/config.yaml)
Phase: RED — these tests FAIL on current main.
Gate: GT-050

Validates the pre-init scanner defined in Decision #7 of the issue.
The scanner walks a consumer repo BEFORE `atdd init --themes custom`
prompts and returns:
- `detected`     : distinct `theme:` values found in `plan/**/*.yaml`
                   (primary, high-confidence).
- `low_confidence`: candidate domain tokens from top-level dir names +
                    `pyproject.toml` / `package.json` keywords
                    (secondary, advisory only — must never silently
                    land in the primary list).
- `force_fits`   : wagons whose slug does not overlap with their
                   assigned theme's synonym set
                   (e.g. wagon `authenticate-users` tagged
                   `theme: commons` → flagged for operator review).

URN: test:coach:custom-themes:theme-scanner

Target module (Phase 2 / GREEN): `atdd.coach.utils.theme_scanner`
- `scan_existing_themes(repo_root: Path) -> ScanResult`
- `ScanResult` exposes `.detected`, `.low_confidence`, `.force_fits`.
"""
import pytest


# ---------------------------------------------------------------------------
# Module import guard
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_theme_scanner_module_is_importable():
    """
    SPEC-COACH-SCANNER-0001: `atdd.coach.utils.theme_scanner` exists.
    """
    from atdd.coach.utils import theme_scanner  # noqa: F401


@pytest.mark.platform
def test_scan_existing_themes_is_callable():
    """
    SPEC-COACH-SCANNER-0002: `scan_existing_themes(repo_root)` exists.
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    assert callable(scan_existing_themes)


# ---------------------------------------------------------------------------
# Helpers for fixture construction
# ---------------------------------------------------------------------------


def _write_wagon(dir_path, slug: str, theme: str) -> None:
    """Write a minimal valid wagon yaml under `dir_path`."""
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"_{dir_path.name}.yaml").write_text(
        f"wagon: {slug}\n"
        f"description: wagon fixture for scanner tests\n"
        f"theme: {theme}\n"
        f"subject: agent:{slug}\n"
        f"context: fixture\n"
        f"action: acts\n"
        f"goal: reach goal\n"
        f"outcome: outcome produced\n"
        f"produce: []\n"
        f"consume: []\n"
        f"wmbt: []\n"
    )


# ---------------------------------------------------------------------------
# Empty-repo baseline
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_scanner_returns_empty_on_greenfield_repo(tmp_path):
    """
    SPEC-COACH-SCANNER-0003: Empty repo → empty detected + low_confidence.

    Greenfield repos have no plan/ tree and minimal/no manifest. The
    scanner must not raise and must return empty lists (blind prompt
    path).
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    result = scan_existing_themes(tmp_path)

    assert list(result.detected) == []
    assert list(result.force_fits) == []


# ---------------------------------------------------------------------------
# Primary source — plan/**/*.yaml
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_scanner_detects_themes_from_plan_tree(tmp_path):
    """
    SPEC-COACH-SCANNER-0004: `theme:` values in plan/ are detected.

    Given a plan/ tree with three wagons tagged with three distinct
    themes, the scanner must return all three in `.detected` (order
    deterministic or not — only set-equality matters).
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    _write_wagon(tmp_path / "plan" / "qualify_leads", "qualify-leads", "qualification")
    _write_wagon(tmp_path / "plan" / "secure_ops", "secure-ops", "security")
    _write_wagon(tmp_path / "plan" / "manage_versions", "manage-versions", "operations")

    result = scan_existing_themes(tmp_path)

    assert set(result.detected) == {"qualification", "security", "operations"}


@pytest.mark.platform
def test_scanner_deduplicates_repeated_themes(tmp_path):
    """
    SPEC-COACH-SCANNER-0005: Repeated `theme:` values appear once.
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    _write_wagon(tmp_path / "plan" / "q1", "qualify-leads", "qualification")
    _write_wagon(tmp_path / "plan" / "q2", "extract-qualification", "qualification")
    _write_wagon(tmp_path / "plan" / "q3", "handle-webhooks", "qualification")

    result = scan_existing_themes(tmp_path)

    assert list(result.detected).count("qualification") == 1, (
        f"Scanner must dedupe themes, got: {result.detected}"
    )


@pytest.mark.platform
def test_scanner_ignores_files_outside_plan_tree(tmp_path):
    """
    SPEC-COACH-SCANNER-0006: Only `plan/**/*.yaml` is primary source.

    Random YAML files elsewhere in the repo (e.g. CI configs, GitHub
    Actions) that happen to contain a `theme:` key must NOT leak into
    the detected list.
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yaml").write_text(
        "name: ci\n"
        "theme: bogus-from-ci\n"
        "jobs: {}\n"
    )

    result = scan_existing_themes(tmp_path)

    assert "bogus-from-ci" not in result.detected, (
        f"Scanner leaked non-plan/ YAML content into detected: "
        f"{result.detected}"
    )


# ---------------------------------------------------------------------------
# Secondary source — low-confidence candidates from repo metadata
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_scanner_separates_low_confidence_from_detected(tmp_path):
    """
    SPEC-COACH-SCANNER-0007: Low-confidence candidates do not leak.

    When the scanner picks up candidate tokens from top-level dir
    names or `pyproject.toml`/`package.json` keywords, they land in
    `.low_confidence` — never in `.detected` — so the prompt can
    present them as suggestions rather than pre-selections.
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    # No plan/ tree — scanner must not hallucinate detections.
    (tmp_path / "authentication").mkdir()
    (tmp_path / "observability").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nkeywords = ["qualification", "security"]\n'
    )

    result = scan_existing_themes(tmp_path)

    assert list(result.detected) == [], (
        f"Low-confidence candidates must not leak into detected, "
        f"got: {result.detected}"
    )
    assert result.low_confidence, (
        "Expected at least one low-confidence candidate from repo metadata"
    )


@pytest.mark.platform
def test_scanner_finds_low_confidence_from_pyproject_keywords(tmp_path):
    """
    SPEC-COACH-SCANNER-0008: pyproject.toml keywords seed low-confidence.
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        'keywords = ["qualification", "operations"]\n'
    )

    result = scan_existing_themes(tmp_path)

    lc = set(result.low_confidence)
    assert "qualification" in lc or "operations" in lc, (
        f"Expected pyproject keywords in low_confidence, got: {lc}"
    )


# ---------------------------------------------------------------------------
# Force-fit heuristic
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_scanner_flags_force_fit_authenticate_users_vs_commons(tmp_path):
    """
    SPEC-COACH-SCANNER-0009: Force-fit heuristic catches the canonical case.

    Wagon slug tokens (`authenticate`, `users`) do not overlap with the
    `commons` theme's semantic synonyms. The scanner must surface this
    as a force-fit candidate so the operator can choose to re-tag.

    Reference case from issue body Problem Statement:
        > security wagons force-fit into `commons` because no default
        > theme matches "authenticate / guard / protect".
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    _write_wagon(
        tmp_path / "plan" / "authenticate_users",
        "authenticate-users",
        "commons",
    )

    result = scan_existing_themes(tmp_path)

    slugs = [ff.wagon if hasattr(ff, "wagon") else ff.get("wagon") for ff in result.force_fits]
    assert "authenticate-users" in slugs, (
        f"Force-fit heuristic must flag `authenticate-users` tagged "
        f"`commons`. force_fits returned: {result.force_fits}"
    )


@pytest.mark.platform
def test_scanner_does_not_flag_semantically_aligned_wagon(tmp_path):
    """
    SPEC-COACH-SCANNER-0010: Aligned wagon/theme pairs are NOT flagged.

    `authenticate-users` tagged `security` is a natural fit and must
    not appear in force_fits (otherwise the signal is noise).
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    _write_wagon(
        tmp_path / "plan" / "authenticate_users",
        "authenticate-users",
        "security",
    )

    result = scan_existing_themes(tmp_path)

    slugs = [ff.wagon if hasattr(ff, "wagon") else ff.get("wagon") for ff in result.force_fits]
    assert "authenticate-users" not in slugs, (
        f"Semantically aligned wagon (security) must NOT be flagged as "
        f"force-fit. force_fits returned: {result.force_fits}"
    )


# ---------------------------------------------------------------------------
# Integration — scanner output consumable by custom prompt flow
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_scan_result_is_iterable_on_all_fields(tmp_path):
    """
    SPEC-COACH-SCANNER-0011: ScanResult exposes iterable collections.

    The prompt layer iterates over `result.detected`, `result.low_confidence`,
    and `result.force_fits`. Each must be an iterable (list or tuple)
    regardless of whether detections exist.
    """
    from atdd.coach.utils.theme_scanner import scan_existing_themes

    result = scan_existing_themes(tmp_path)

    # Should not raise TypeError — each field must be iterable.
    assert list(iter(result.detected)) == list(result.detected)
    assert list(iter(result.low_confidence)) == list(result.low_confidence)
    assert list(iter(result.force_fits)) == list(result.force_fits)

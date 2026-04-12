"""
Baseline CLI Command
====================
Provides ``atdd baseline update`` and ``atdd baseline show`` for managing
ratchet baselines used by coder and tester validators.

Baseline files:
- ``.atdd/baselines/coder.yaml`` — coder validators
- ``.atdd/baselines/tester.yaml`` — tester validators

Usage::

    atdd baseline update              # Record current violation counts
    atdd baseline update --dry-run    # Show what would be written
    atdd baseline show                # Compare baseline vs current
    atdd baseline show --verbose      # Include per-validator detail
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from atdd.coach.utils.repo import find_repo_root
from atdd.coder.baselines.ratchet import RatchetBaseline, default_baseline_path
from atdd.tester.validators.conftest import tester_baseline_path


def coach_baseline_path(repo_root: Path) -> Path:
    """Return the canonical coach baseline file path."""
    return repo_root / ".atdd" / "baselines" / "coach.yaml"


# ---------------------------------------------------------------------------
# Validator registry
# ---------------------------------------------------------------------------
# Each entry maps a validator_id to a callable that accepts (repo_root) and
# returns (violation_count, violations_list).  Validators register here when
# they are retrofitted to the ratchet pattern (Phase 3).
#
# Import paths are deferred (inside the callable) to avoid import-time
# failures when the target repo has no Python/TS tree to scan.
# ---------------------------------------------------------------------------

ValidatorFn = Callable[[Path], Tuple[int, Sequence]]


def _composition_python(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_composition_completeness import (
        analyze_python_repo,
    )
    violations = analyze_python_repo(repo_root)
    return len(violations), violations


def _composition_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_composition_completeness import (
        analyze_typescript_repo,
    )
    violations = analyze_typescript_repo(repo_root)
    return len(violations), violations


def _composition_supabase(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_composition_completeness import (
        analyze_typescript_repo,
    )
    violations = analyze_typescript_repo(repo_root, stack="supabase")
    return len(violations), violations


def _dead_code_python(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_dead_code_python import (
        find_python_files,
        build_file_import_graph,
        find_reachable_files,
        find_cli_entry_points,
        resolve_module_to_file,
        is_root_file,
        build_reverse_graph,
    )
    python_files = find_python_files()
    if not python_files:
        return 0, []
    graph = build_file_import_graph(python_files)
    roots = {f for f in python_files if is_root_file(f)}
    cli_modules = find_cli_entry_points()
    all_files_set = set(python_files)
    for module in cli_modules:
        roots.update(resolve_module_to_file(module, all_files_set))
    # Composition roots mark wagon src/ as reachable
    for f in list(roots):
        if f.name == "composition.py":
            src_dir = f.parent / "src"
            if src_dir.is_dir():
                roots.update(pf for pf in python_files if str(pf).startswith(str(src_dir)))
    reachable = find_reachable_files(roots, graph)
    reverse_reachable = find_reachable_files(roots, build_reverse_graph(graph))
    all_reachable = reachable | reverse_reachable
    unreachable = [
        str(f.relative_to(repo_root))
        for f in python_files
        if f not in all_reachable and f.name != "__init__.py"
    ]
    return len(unreachable), unreachable


def _maintainability_index(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics import (
        find_python_files,
        calculate_maintainability_index,
        MIN_MAINTAINABILITY_INDEX,
        REPO_ROOT,
    )
    violations = []
    for py_file in find_python_files():
        try:
            with open(py_file, 'r') as f:
                if len(f.readlines()) < 10:
                    continue
        except Exception:
            continue
        index = calculate_maintainability_index(py_file)
        if index < MIN_MAINTAINABILITY_INDEX:
            violations.append(f"{py_file.relative_to(REPO_ROOT)} MI={index:.1f}")
    return len(violations), violations


def _code_comments(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics import (
        find_python_files,
        calculate_comment_ratio,
        MIN_COMMENT_RATIO,
        REPO_ROOT,
    )
    violations = []
    for py_file in find_python_files():
        try:
            with open(py_file, 'r') as f:
                if len(f.readlines()) < 20:
                    continue
        except Exception:
            continue
        ratio = calculate_comment_ratio(py_file)
        if ratio < MIN_COMMENT_RATIO:
            violations.append(f"{py_file.relative_to(REPO_ROOT)} {ratio*100:.1f}%")
    return len(violations), violations


def _contract_driven_http(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_contract_driven_http import (
        analyze_contract_driven_http,
    )
    return analyze_contract_driven_http(repo_root)


def _dead_code_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_dead_code_typescript import scan_dead_code_typescript
    return scan_dead_code_typescript(repo_root)


def _duplication_detector(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_duplication_detector import scan_python_duplications
    return scan_python_duplications(repo_root)


def _duplication_detector_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_duplication_detector_typescript import scan_typescript_duplications
    return scan_typescript_duplications(repo_root)


def _cyclomatic_complexity(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity import scan_cyclomatic_complexity
    return scan_cyclomatic_complexity(repo_root)


def _nesting_depth(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity import scan_nesting_depth
    return scan_nesting_depth(repo_root)


def _function_length(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity import scan_function_length
    return scan_function_length(repo_root)


def _function_parameter_count(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity import scan_function_params
    return scan_function_params(repo_root)


def _cognitive_complexity(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity import scan_cognitive_complexity
    return scan_cognitive_complexity(repo_root)


def _file_line_count(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics import scan_file_line_count
    return scan_file_line_count(repo_root)


def _code_duplication(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics import (
        find_python_files,
        find_duplicate_code_blocks,
        REPO_ROOT,
    )
    python_files = find_python_files()
    if not python_files:
        return 0, []
    duplicates = find_duplicate_code_blocks(python_files[:50])
    violations = [
        f"{f1.relative_to(REPO_ROOT)} ↔ {f2.relative_to(REPO_ROOT)} ({len(b)} lines)"
        for f1, f2, b in duplicates
    ]
    return len(duplicates), violations


def _naming_conventions(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics import (
        find_python_files,
        check_naming_consistency,
        REPO_ROOT,
    )
    violations = []
    for py_file in find_python_files():
        for v in check_naming_consistency(py_file):
            violations.append(f"{py_file.relative_to(REPO_ROOT)}: {v}")
    return len(violations), violations


def _print_in_production(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_structured_logging import scan_print_in_production
    return scan_print_in_production(repo_root)


def _structured_logging_format(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_structured_logging import scan_structured_logging
    return scan_structured_logging(repo_root)


def _sql_concatenation(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_security_patterns import scan_sql_concatenation
    return scan_sql_concatenation(repo_root)


def _missing_auth_dependency(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_security_patterns import scan_missing_auth
    return scan_missing_auth(repo_root)


def _hardcoded_secrets(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_security_patterns import scan_hardcoded_secrets
    return scan_hardcoded_secrets(repo_root)


def _ds_presentation_primitives(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_design_system_compliance import scan_ds_presentation_primitives
    return scan_ds_presentation_primitives(repo_root)


def _ds_color_tokens(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_design_system_compliance import (
        get_all_ui_files, extract_raw_color_values,
    )
    violations = []
    for f in get_all_ui_files():
        for line_num, issue in extract_raw_color_values(f)[:3]:
            try:
                rel = f.relative_to(repo_root)
            except ValueError:
                rel = f
            violations.append(f"{rel}:{line_num} {issue}")
    return len(violations), violations


def _ds_orphaned_exports(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_design_system_compliance import (
        get_design_system_exports, find_design_system_usage,
    )
    exports = get_design_system_exports()
    used = find_design_system_usage()
    all_exports = exports.get('primitives', set()) | exports.get('components', set())
    orphaned = all_exports - used - {'type', 'h', 'Fragment'}
    return len(orphaned), sorted(orphaned)


def _ds_foundations_usage(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_design_system_compliance import (
        extract_imports, PRIMITIVES_DIR, COMPONENTS_DIR,
    )
    import re as _re
    violations = []
    for category_dir in [PRIMITIVES_DIR, COMPONENTS_DIR]:
        if not category_dir.exists():
            continue
        for f in category_dir.rglob("*.tsx"):
            if f.name == "index.ts":
                continue
            try:
                content = f.read_text(encoding='utf-8')
            except Exception:
                continue
            imports = extract_imports(f)
            uses_foundations = any('../foundations' in imp or './foundations' in imp for imp in imports)
            raw_pixels = _re.findall(r":\s*['\"]?(\d{2,}px)['\"]?", content)
            if raw_pixels and not uses_foundations:
                try:
                    rel = f.relative_to(repo_root)
                except ValueError:
                    rel = f
                violations.append(f"{rel}: raw pixel values {', '.join(raw_pixels[:5])}")
    return len(violations), violations


def _ds_hierarchy_imports(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_design_system_compliance import (
        extract_imports, MAINTAIN_UX, _get_maintain_ux_files,
    )
    violations = []
    for f in _get_maintain_ux_files("primitives"):
        for imp in extract_imports(f):
            if "../components/" in imp or "../components" == imp or "../templates/" in imp or "../templates" == imp:
                try:
                    rel = f.relative_to(repo_root)
                except ValueError:
                    rel = f
                violations.append(f"{rel}: forbidden import '{imp}'")
    for f in _get_maintain_ux_files("components"):
        for imp in extract_imports(f):
            if "../templates/" in imp or "../templates" == imp:
                try:
                    rel = f.relative_to(repo_root)
                except ValueError:
                    rel = f
                violations.append(f"{rel}: forbidden import '{imp}'")
    if MAINTAIN_UX.exists():
        for ext in ("*.ts", "*.tsx"):
            for f in MAINTAIN_UX.rglob(ext):
                if ".test." in f.name or "/tests/" in str(f):
                    continue
                for imp in extract_imports(f):
                    if imp.startswith(".") or imp.startswith("@/maintain-ux"):
                        continue
                    if imp.startswith("preact") or imp.startswith("@preact"):
                        continue
                    if imp.startswith("@/") or imp.startswith("../"):
                        try:
                            rel = f.relative_to(repo_root)
                        except ValueError:
                            rel = f
                        violations.append(f"{rel}: forbidden import '{imp}'")
    return len(violations), violations


def _ds_hardcoded_tokens(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_design_system_compliance import get_all_ui_files
    import re as _re
    patterns = [
        (r'''(?:padding|margin|gap|top|bottom|left|right|width|height)\s*:\s*["'](\d+)px["']''', "Hardcoded pixel"),
        (r"""\$\{\s*(\d+)\s*\}px""", "Hardcoded pixel template"),
        (r'''borderRadius\s*:\s*["'](\d+)px["']''', "Hardcoded radius string"),
        (r"""borderRadius\s*:\s*(\d+)\s*[,}\n]""", "Hardcoded radius number"),
        (r'''(?:transition|animation(?:Duration)?)\s*:\s*["'][^"']*?(\d{2,})ms''', "Hardcoded duration"),
        (r"""(?:padding|margin|gap)\s*:\s*(\d+)\s*[,}\n]""", "Hardcoded spacing"),
    ]
    violations = []
    for f in get_all_ui_files():
        try:
            content = f.read_text(encoding='utf-8')
        except Exception:
            continue
        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.strip()
            if stripped.startswith('import') or stripped.startswith('//') or stripped.startswith('/*'):
                continue
            if 'spacing.' in line or 'radii.' in line or 'motion.' in line or 'tokens.' in line:
                continue
            for pattern, desc in patterns:
                for match in _re.finditer(pattern, line):
                    if int(match.group(1)) <= 4:
                        continue
                    try:
                        rel = f.relative_to(repo_root)
                    except ValueError:
                        rel = f
                    violations.append(f"{rel}:{i} {desc}")
    return len(violations), violations


def _ds_orphaned_ui(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_design_system_compliance import (
        get_all_ui_files, extract_imports,
    )
    import re as _re
    violations = []
    for f in get_all_ui_files():
        try:
            content = f.read_text(encoding='utf-8')
        except Exception:
            continue
        if not _re.search(r'return\s*\(?\s*<', content):
            continue
        imports = extract_imports(f)
        if not any('maintain-ux' in imp or '@maintain-ux' in imp for imp in imports):
            try:
                rel = f.relative_to(repo_root)
            except ValueError:
                rel = f
            violations.append(str(rel))
    return len(violations), violations


def _error_response_bare_string(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_error_response_compliance import scan_bare_string_errors
    return scan_bare_string_errors(repo_root)


def _error_code_format(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_error_response_compliance import scan_error_code_format
    return scan_error_code_format(repo_root)


def _query_count(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_query_count import scan_query_count
    return scan_query_count(repo_root)


def _gsap_layer_usage(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_gsap_layer_usage import scan_gsap_layer_usage
    return scan_gsap_layer_usage(repo_root)


def _gsap_commons(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_gsap_layer_usage import scan_gsap_commons
    return scan_gsap_commons(repo_root)


def _i18n_config_manifest(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_i18n_runtime import scan_i18n_config
    return scan_i18n_config(repo_root)


def _i18n_language_switcher(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_i18n_runtime import scan_language_switcher
    return scan_language_switcher(repo_root)


def _cyclomatic_complexity_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity_typescript import scan_cyclomatic_complexity_ts
    return scan_cyclomatic_complexity_ts(repo_root)


def _nesting_depth_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity_typescript import scan_nesting_depth_ts
    return scan_nesting_depth_ts(repo_root)


def _function_length_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_complexity_typescript import scan_function_length_ts
    return scan_function_length_ts(repo_root)


def _maintainability_index_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics_typescript import scan_maintainability_index_ts
    return scan_maintainability_index_ts(repo_root)


def _comment_ratio_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics_typescript import scan_comment_ratio_ts
    return scan_comment_ratio_ts(repo_root)


def _entity_cross_language(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_cross_language_consistency import scan_entity_cross_language
    return scan_entity_cross_language(repo_root)


def _enum_cross_language(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_cross_language_consistency import scan_enum_cross_language
    return scan_enum_cross_language(repo_root)


def _naming_cross_language(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_cross_language_consistency import scan_naming_cross_language
    return scan_naming_cross_language(repo_root)


def _api_contracts_cross_language(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_cross_language_consistency import scan_api_contracts_cross_language
    return scan_api_contracts_cross_language(repo_root)


VALIDATORS: Dict[str, ValidatorFn] = {
    # --- Existing ---
    "composition_completeness_python": _composition_python,
    "composition_completeness_typescript": _composition_typescript,
    "composition_completeness_supabase": _composition_supabase,
    "contract_driven_http": _contract_driven_http,
    "dead_code_python": _dead_code_python,
    "dead_code_typescript": _dead_code_typescript,
    "maintainability_index": _maintainability_index,
    "code_comments": _code_comments,
    # --- Category A: quality/style (ratcheted in #250) ---
    "duplication_detector": _duplication_detector,
    "duplication_detector_typescript": _duplication_detector_typescript,
    "cyclomatic_complexity": _cyclomatic_complexity,
    "nesting_depth": _nesting_depth,
    "function_length": _function_length,
    "function_parameter_count": _function_parameter_count,
    "cognitive_complexity": _cognitive_complexity,
    "file_line_count": _file_line_count,
    "code_duplication": _code_duplication,
    "naming_conventions": _naming_conventions,
    "print_in_production": _print_in_production,
    "structured_logging_format": _structured_logging_format,
    "sql_concatenation": _sql_concatenation,
    "missing_auth_dependency": _missing_auth_dependency,
    "hardcoded_secrets": _hardcoded_secrets,
    "ds_presentation_primitives": _ds_presentation_primitives,
    "ds_color_tokens": _ds_color_tokens,
    "ds_orphaned_exports": _ds_orphaned_exports,
    "ds_foundations_usage": _ds_foundations_usage,
    "ds_hierarchy_imports": _ds_hierarchy_imports,
    "ds_hardcoded_tokens": _ds_hardcoded_tokens,
    "ds_orphaned_ui": _ds_orphaned_ui,
    "error_response_bare_string": _error_response_bare_string,
    "error_code_format": _error_code_format,
    "query_count": _query_count,
    "gsap_layer_usage": _gsap_layer_usage,
    "gsap_commons": _gsap_commons,
    "i18n_config_manifest": _i18n_config_manifest,
    "i18n_language_switcher": _i18n_language_switcher,
    "entity_cross_language": _entity_cross_language,
    "enum_cross_language": _enum_cross_language,
    "naming_cross_language": _naming_cross_language,
    "api_contracts_cross_language": _api_contracts_cross_language,
    # --- Phase 6: TS complexity & quality (BE parity, #261) ---
    "cyclomatic_complexity_typescript": _cyclomatic_complexity_typescript,
    "nesting_depth_typescript": _nesting_depth_typescript,
    "function_length_typescript": _function_length_typescript,
    "maintainability_index_typescript": _maintainability_index_typescript,
    "comment_ratio_typescript": _comment_ratio_typescript,
}


# ---------------------------------------------------------------------------
# Tester validator registry
# ---------------------------------------------------------------------------


def _smoke_coverage_gaps(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.tester.validators.test_smoke_coverage import (
        CoverageAnalyzer,
    )
    e2e_dir = repo_root / "e2e"
    analyzer = CoverageAnalyzer(e2e_dir)
    trains, gaps, _, _ = analyzer.analyze()
    violations = [
        f"{g.train_id}: {len(g.contract_tests)} contract test(s), 0 smoke tests"
        for g in gaps
    ]
    return len(violations), violations


def _train_e2e_existence(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.tester.validators.test_train_e2e_existence import (
        E2EExistenceAnalyzer,
    )
    e2e_dir = repo_root / "e2e"
    trains_file = repo_root / "plan" / "_trains.yaml"
    analyzer = E2EExistenceAnalyzer(e2e_dir, trains_file)
    statuses = analyzer.analyze()
    violations = [
        f"{s.train_id}: no E2E tests in e2e/{s.train_id}/"
        for s in statuses
        if not s.has_tests
    ]
    return len(violations), violations


def _train_route_smoke_coverage(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.tester.validators.test_train_route_smoke_coverage import (
        scan_train_route_smoke_coverage,
    )
    return scan_train_route_smoke_coverage(repo_root)


def _train_completeness(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.tester.validators.test_train_completeness import (
        CompletenessAnalyzer,
    )
    e2e_dir = repo_root / "e2e"
    trains_file = repo_root / "plan" / "_trains.yaml"
    analyzer = CompletenessAnalyzer(e2e_dir, trains_file)
    statuses = analyzer.analyze()
    incomplete = [s for s in statuses if not s.complete]
    violations = [
        f"{s.train_id}: {s.status_label} "
        f"(e2e={s.e2e_count}, contract={s.contract_count}, smoke={s.smoke_count})"
        for s in incomplete
    ]
    return len(violations), violations


TESTER_VALIDATORS: Dict[str, ValidatorFn] = {
    "smoke_coverage_gaps": _smoke_coverage_gaps,
    "train_e2e_existence": _train_e2e_existence,
    "train_route_smoke_coverage": _train_route_smoke_coverage,
    "train_completeness": _train_completeness,
}


# ---------------------------------------------------------------------------
# Coach validator registry (github_api — requires live API access)
# ---------------------------------------------------------------------------


def _pr_phase_alignment(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coach.validators.test_pr_phase_alignment import scan_pr_phase_alignment
    return scan_pr_phase_alignment(repo_root)


def _issue_advancement(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coach.validators.test_issue_advancement import scan_issue_advancement
    return scan_issue_advancement(repo_root)


COACH_VALIDATORS: Dict[str, ValidatorFn] = {
    "pr_phase_alignment": _pr_phase_alignment,
    "issue_advancement": _issue_advancement,
}


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class BaselineCommand:
    """CLI command handler for ``atdd baseline {update,show}``."""

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root or find_repo_root()
        self.baseline = RatchetBaseline(
            default_baseline_path(self.repo_root),
        )
        self.tester_baseline = RatchetBaseline(
            tester_baseline_path(self.repo_root),
        )
        self.coach_baseline = RatchetBaseline(
            coach_baseline_path(self.repo_root),
        )

    # ---------------------------------------------------------------
    # atdd baseline update
    # ---------------------------------------------------------------

    def _run_validators(
        self,
        validators: Dict[str, ValidatorFn],
        label: str,
        verbose: bool = False,
    ) -> Tuple[Dict[str, int], List[str]]:
        """Run a set of validators and return results + errors."""
        results: Dict[str, int] = {}
        errors: List[str] = []

        print(f"  [{label}]")
        for vid, fn in sorted(validators.items()):
            try:
                count, violations = fn(self.repo_root)
                results[vid] = count
                symbol = "✓" if count == 0 else f"▸ {count}"
                print(f"    {vid}: {symbol}")
                if verbose and violations:
                    for v in violations[:5]:
                        print(f"        {v}")
                    if len(violations) > 5:
                        print(f"        ... and {len(violations) - 5} more")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"    {vid}: ERROR — {exc}")
                print(f"    {vid}: ERROR — {exc}")

        return results, errors

    def update(
        self,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> int:
        """Run all registered validators and write current counts."""
        print(f"Scanning {self.repo_root} ...\n")

        coder_results, coder_errors = self._run_validators(
            VALIDATORS, "coder", verbose,
        )
        tester_results, tester_errors = self._run_validators(
            TESTER_VALIDATORS, "tester", verbose,
        )
        coach_results, coach_errors = self._run_validators(
            COACH_VALIDATORS, "coach", verbose,
        )

        errors = coder_errors + tester_errors + coach_errors
        print()

        if errors:
            print("Errors encountered (baselines NOT updated):")
            for e in errors:
                print(e)
            return 1

        if dry_run:
            print("Dry-run — would write:\n")
            for vid, count in sorted(coder_results.items()):
                print(f"  {vid}: {count}")
            print(f"  To: {self.baseline.path}\n")
            for vid, count in sorted(tester_results.items()):
                print(f"  {vid}: {count}")
            print(f"  To: {self.tester_baseline.path}\n")
            for vid, count in sorted(coach_results.items()):
                print(f"  {vid}: {count}")
            print(f"  To: {self.coach_baseline.path}")
            return 0

        self.baseline.update(coder_results)
        print(f"Coder baseline written to {self.baseline.path}")
        self.tester_baseline.update(tester_results)
        print(f"Tester baseline written to {self.tester_baseline.path}")
        self.coach_baseline.update(coach_results)
        print(f"Coach baseline written to {self.coach_baseline.path}")
        return 0

    # ---------------------------------------------------------------
    # atdd baseline show
    # ---------------------------------------------------------------

    def _show_scope(
        self,
        baseline: RatchetBaseline,
        validators: Dict[str, ValidatorFn],
        label: str,
    ) -> List[str]:
        """Show baseline vs current for one scope. Returns errors."""
        errors: List[str] = []
        results: Dict[str, int] = {}

        for vid, fn in sorted(validators.items()):
            try:
                count, _ = fn(self.repo_root)
                results[vid] = count
            except Exception as exc:  # noqa: BLE001
                errors.append(f"  {vid}: ERROR — {exc}")

        if not baseline.exists and not results:
            return errors

        rows = baseline.show(results)

        fmt = "{:<45} {:>10} {:>10} {:>8}  {}"
        print(f"\n[{label}] {baseline.path}")
        print(fmt.format("Validator", "Baseline", "Current", "Delta", "Status"))
        print("-" * 90)

        for row in rows:
            delta_str = f"{row['delta']:+d}" if row["delta"] != 0 else "0"
            print(
                fmt.format(
                    row["validator"],
                    row["baseline"],
                    row["current"],
                    delta_str,
                    row["status"],
                )
            )

        return errors

    def show(self, verbose: bool = False) -> int:
        """Display baseline vs current violation counts."""
        if not self.baseline.exists and not self.tester_baseline.exists and not self.coach_baseline.exists:
            print(
                f"No baseline files found.\n\n"
                f"Run `atdd baseline update` to create them."
            )
            return 0

        print(f"Scanning {self.repo_root} ...")

        errors = self._show_scope(self.baseline, VALIDATORS, "coder")
        errors += self._show_scope(
            self.tester_baseline, TESTER_VALIDATORS, "tester",
        )
        errors += self._show_scope(
            self.coach_baseline, COACH_VALIDATORS, "coach",
        )

        if errors:
            print(f"\nErrors ({len(errors)}):")
            for e in errors:
                print(e)

        return 0

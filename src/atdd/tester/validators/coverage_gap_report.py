#!/usr/bin/env python3
"""
Generate detailed coverage gap report with actionable details.

Provides:
- Full list of all missing ACs (not truncated)
- Grouped by wagon
- Grouped by test category (UNIT, HTTP, GOLDEN, etc.)
- Suggested test file locations
- Coverage statistics per wagon
- Prioritization guidance
"""

import yaml
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = REPO_ROOT / "plan"
PYTHON_DIR = REPO_ROOT / "python"
LIB_DIR = REPO_ROOT / "lib"


def find_acceptance_criteria() -> Dict[str, Dict]:
    """Find all acceptance criteria definitions."""
    if not PLAN_DIR.exists():
        return {}

    acs = {}

    for yaml_file in PLAN_DIR.rglob("*.yaml"):
        if yaml_file.name.startswith('_'):
            continue

        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except Exception:
            continue

        if isinstance(data, dict) and 'acceptances' in data:
            wmbt_urn = data.get('urn', 'unknown')
            wagon_name = yaml_file.parent.name

            for acceptance in data.get('acceptances', []):
                identity = acceptance.get('identity', {})
                urn = identity.get('urn')

                if urn:
                    acs[urn] = {
                        'wagon': wagon_name,
                        'wmbt': wmbt_urn,
                        'wmbt_file': yaml_file.stem,
                        'purpose': identity.get('purpose', ''),
                        'file': str(yaml_file.relative_to(REPO_ROOT))
                    }

    return acs


def find_python_tests() -> Dict[str, List[str]]:
    """Find all Python test files and extract test function names."""
    if not PYTHON_DIR.exists():
        return {}

    tests = {}

    for test_file in PYTHON_DIR.rglob("test_*.py"):
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        test_functions = re.findall(r'def\s+(test_\w+)\s*\(', content)

        if test_functions:
            rel_path = str(test_file.relative_to(REPO_ROOT))
            tests[rel_path] = test_functions

    return tests


def extract_ac_reference_from_test_name(test_name: str) -> str | None:
    """Extract AC URN reference from test name."""
    match = re.search(r'AC[-_]([A-Z0-9]+)[-_](\d{3})', test_name.upper())
    if match:
        return f"AC-{match.group(1)}-{match.group(2)}"

    match = re.search(r'(?:test_)?ac_(\d{3})', test_name.lower())
    if match:
        return f"AC-{match.group(1)}"

    return None


def extract_ac_reference_from_docstring(file_path: str, test_name: str) -> str | None:
    """Extract AC reference from test docstring or header comments (per RED convention).

    Per RED convention v1.0+, tests SHOULD have AC URN in BOTH:
    1. Header comment: # URN: acc:...
    2. Module docstring: RED Test for acc:...

    This function accepts EITHER format for backward compatibility,
    but convention enforcement should validate BOTH are present and match.
    """
    try:
        with open(REPO_ROOT / file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    ac_from_header = None
    ac_from_docstring = None

    # Python header comment (RED convention format: # URN: acc:...)
    if file_path.endswith('.py'):
        # Check header comment
        header_comment_match = re.search(
            r'^#\s*URN:\s*(acc:[a-z\-]+:[A-Z0-9]+-[A-Z0-9]+-\d{3}(?:-[a-z\-]+)?)',
            content,
            re.MULTILINE
        )
        if header_comment_match:
            ac_from_header = header_comment_match.group(1)

        # Check module docstring
        module_docstring_match = re.search(
            r'^\s*""".*?(acc:[a-z\-]+:[A-Z0-9]+-[A-Z0-9]+-\d{3}(?:-[a-z\-]+)?)',
            content,
            re.DOTALL | re.MULTILINE
        )
        if module_docstring_match:
            ac_from_docstring = module_docstring_match.group(1)

    # Function docstring (fallback)
    if not ac_from_docstring:
        pattern = f'def {test_name}.*?"""(.*?)"""'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            docstring = match.group(1)
            ac_match = re.search(r'acc:[a-z\-]+:[A-Z0-9]+-[A-Z0-9]+-\d{3}(?:-[a-z\-]+)?', docstring)
            if ac_match:
                ac_from_docstring = ac_match.group(0)

    # Return whichever we found (prefer header for consistency)
    # Note: Ideally both should exist and match (per convention)
    return ac_from_header or ac_from_docstring


def map_tests_to_acs(python_tests: Dict[str, List[str]]) -> Dict[str, List[Tuple[str, str]]]:
    """Map tests to acceptance criteria."""
    ac_to_tests = {}

    for file_path, test_names in python_tests.items():
        for test_name in test_names:
            # Prioritize docstring extraction (has full AC URN) over test name (has partial ref)
            ac_ref = extract_ac_reference_from_docstring(file_path, test_name)

            # Fall back to test name extraction if docstring doesn't have AC URN
            if not ac_ref:
                ac_ref = extract_ac_reference_from_test_name(test_name)

            if ac_ref:
                if ac_ref not in ac_to_tests:
                    ac_to_tests[ac_ref] = []
                ac_to_tests[ac_ref].append((file_path, test_name))

    return ac_to_tests


def extract_test_category(ac_urn: str) -> str:
    """Extract test category from AC URN (e.g., UNIT, HTTP, GOLDEN)."""
    match = re.search(r'acc:[a-z\-]+:([A-Z0-9]+)-([A-Z]+)-\d{3}', ac_urn)
    if match:
        return match.group(2)
    return "UNKNOWN"


def suggest_test_location(ac_data: Dict) -> str:
    """Suggest where the test file should be created."""
    wagon = ac_data['wagon']
    wmbt_file = ac_data['wmbt_file']
    return f"python/{wagon}/test_{wmbt_file}.py"


def generate_report():
    """Generate comprehensive coverage gap report."""
    print("=" * 70)
    print("COVERAGE GAP ANALYSIS - Full Detailed Report")
    print("=" * 70)
    print()

    # Find all ACs and tests
    acs = find_acceptance_criteria()
    python_tests = find_python_tests()
    ac_to_tests = map_tests_to_acs(python_tests)

    # Find missing tests
    missing_acs = []
    for ac_urn, ac_data in acs.items():
        if ac_urn not in ac_to_tests:
            missing_acs.append((ac_urn, ac_data))

    # Calculate overall coverage
    total_acs = len(acs)
    covered_acs = total_acs - len(missing_acs)
    coverage_pct = (covered_acs / total_acs * 100) if total_acs > 0 else 0

    print(f"📊 OVERALL COVERAGE")
    print(f"   Total ACs: {total_acs}")
    print(f"   Covered: {covered_acs}")
    print(f"   Missing: {len(missing_acs)}")
    print(f"   Coverage: {coverage_pct:.1f}%")
    print()

    # Group by wagon
    print("=" * 70)
    print("📦 COVERAGE BY WAGON")
    print("=" * 70)
    print()

    wagon_coverage = defaultdict(lambda: {'total': 0, 'missing': 0, 'acs': []})

    for ac_urn, ac_data in acs.items():
        wagon = ac_data['wagon']
        wagon_coverage[wagon]['total'] += 1
        if ac_urn not in ac_to_tests:
            wagon_coverage[wagon]['missing'] += 1
            wagon_coverage[wagon]['acs'].append((ac_urn, ac_data))

    # Sort by missing count (worst first)
    sorted_wagons = sorted(
        wagon_coverage.items(),
        key=lambda x: x[1]['missing'],
        reverse=True
    )

    for wagon, stats in sorted_wagons:
        if stats['missing'] == 0:
            continue

        cov = ((stats['total'] - stats['missing']) / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"🚂 {wagon}")
        print(f"   Coverage: {cov:.1f}% ({stats['total'] - stats['missing']}/{stats['total']})")
        print(f"   Missing: {stats['missing']} ACs")
        print()

    # Group by test category
    print("=" * 70)
    print("🏷️  MISSING TESTS BY CATEGORY")
    print("=" * 70)
    print()

    category_breakdown = defaultdict(list)
    for ac_urn, ac_data in missing_acs:
        category = extract_test_category(ac_urn)
        category_breakdown[category].append((ac_urn, ac_data))

    for category in sorted(category_breakdown.keys()):
        print(f"📌 {category}: {len(category_breakdown[category])} missing")

    print()

    # Detailed breakdown
    print("=" * 70)
    print("📋 ALL MISSING ACCEPTANCE CRITERIA (Full List)")
    print("=" * 70)
    print()

    # Group by wagon for detailed output
    for wagon, stats in sorted_wagons:
        if stats['missing'] == 0:
            continue

        print(f"\n{'=' * 70}")
        print(f"WAGON: {wagon} ({stats['missing']} missing tests)")
        print(f"{'=' * 70}\n")

        # Sort by AC URN for consistency
        sorted_acs = sorted(stats['acs'], key=lambda x: x[0])

        for ac_urn, ac_data in sorted_acs:
            category = extract_test_category(ac_urn)
            test_location = suggest_test_location(ac_data)

            print(f"URN: {ac_urn}")
            print(f"  Category: {category}")
            print(f"  WMBT: {ac_data['wmbt']}")
            print(f"  Purpose: {ac_data['purpose']}")
            print(f"  Spec File: {ac_data['file']}")
            print(f"  Suggested Test: {test_location}")
            print()

    # Summary and recommendations
    print("=" * 70)
    print("💡 RECOMMENDATIONS")
    print("=" * 70)
    print()

    print("Priority Order (by missing test count):")
    for i, (wagon, stats) in enumerate(sorted_wagons[:5], 1):
        if stats['missing'] == 0:
            continue
        print(f"  {i}. {wagon}: {stats['missing']} missing tests")

    print()
    print("Next Steps:")
    print("  1. Focus on high-priority wagons first")
    print("  2. Group test creation by WMBT file (test file)")
    print("  3. Use suggested test locations above")
    print("  4. Reference spec files for AC details")
    print()


if __name__ == "__main__":
    generate_report()

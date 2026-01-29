"""
Test DTO testing patterns enforcement.

Validates conventions from:
- atdd/coder/conventions/dto.convention.yaml (lines 567-599)

Enforces:
- Integration tests MUST use ID comparison (not object identity) when asserting DTO→Entity conversions
- Pattern: assert entity.id in {dto.id for dto in dtos} ✅
- Antipattern: assert entity in dtos ❌

Rationale:
After DTO→Entity conversion via mapper, object identity fails because:
- Mapper creates new entity instances
- DTO and Entity are different types/instances
- Python 'in' operator uses __eq__ or identity
- IDs are stable across DTO/Entity boundary per contract

This pattern was discovered fixing 18 integration tests in pace-dilemmas.
All failures were caused by incorrect "assert entity in dto_list" assertions.
"""

import pytest
import ast
from pathlib import Path
from typing import List, Tuple, Set


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"
DTO_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "dto.convention.yaml"


def find_integration_test_files() -> List[Path]:
    """
    Find all integration test files in wagons.

    Integration tests are the primary location for DTO→Entity boundary testing.
    Unit tests typically work within a single layer.
    """
    if not PYTHON_DIR.exists():
        return []

    integration_tests = []
    for test_file in PYTHON_DIR.rglob("test_*.py"):
        # Skip __pycache__
        if '__pycache__' in str(test_file):
            continue

        # Only include integration test directories
        if '/integration/' in str(test_file):
            integration_tests.append(test_file)

    return integration_tests


def extract_assert_in_statements(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Extract "assert X in Y" statements using AST parsing.

    Returns:
        List of (line_number, left_expr, right_expr) tuples
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    assertions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            # Check if this is "assert X in Y" pattern
            if isinstance(node.test, ast.Compare):
                # node.test.left is the left side of comparison
                # node.test.ops contains comparison operators (e.g., [In()])
                # node.test.comparators contains right sides

                for op, comparator in zip(node.test.ops, node.test.comparators):
                    if isinstance(op, ast.In):
                        # Found "assert X in Y"
                        left_expr = ast.unparse(node.test.left)
                        right_expr = ast.unparse(comparator)
                        assertions.append((node.lineno, left_expr, right_expr))

    return assertions


def looks_like_entity_access(expr: str) -> bool:
    """
    Check if expression looks like entity attribute access.

    Examples:
        - "dilemma.fragment_a" → True
        - "result.fragment_b" → True
        - "returned_entity" → True (ambiguous, but flag it)
        - "fragments" → False
        - "dto_list" → False
    """
    # Look for attribute access with common entity field names
    entity_patterns = [
        'fragment_a', 'fragment_b',  # Dilemma entities
        'returned', 'result', 'entity',  # Common test variable names
        'selected', 'choice', 'decision',  # Domain-specific
    ]

    lower_expr = expr.lower()
    return any(pattern in lower_expr for pattern in entity_patterns)


def looks_like_dto_list(expr: str) -> bool:
    """
    Check if expression looks like a list of DTOs.

    Examples:
        - "fragments" → True
        - "dto_list" → True
        - "available" → True
        - "pool" → True
        - "result.id" → False (not a list)
    """
    # Exclude expressions with .id (those are already using ID comparison)
    if '.id' in expr:
        return False

    # Common list variable names
    list_patterns = [
        'fragments', 'dtos', 'list',
        'available', 'pool', 'choices',
        'warm_library', 'hot_pool',
    ]

    lower_expr = expr.lower()
    return any(pattern in lower_expr for pattern in list_patterns)


def is_id_comparison(left_expr: str, right_expr: str) -> bool:
    """
    Check if this is already using ID comparison (correct pattern).

    Examples of correct patterns:
        - assert entity.id in {dto.id for dto in dtos}
        - assert fragment.id in fragment_ids
        - assert result.id in [f.id for f in fragments]
    """
    # Left side should have .id
    if '.id' not in left_expr:
        return False

    # Right side should have .id (set comprehension or list comprehension)
    if '.id' in right_expr:
        return True

    # Right side might be a pre-computed ID set (e.g., fragment_ids)
    if 'id' in right_expr.lower() and ('set' in right_expr.lower() or '_ids' in right_expr.lower()):
        return True

    return False


class TestDTOTestingPatterns:
    """
    Enforce DTO testing patterns from dto.convention.yaml.

    Convention: atdd/coder/conventions/dto.convention.yaml lines 567-599
    """

    def test_integration_tests_use_id_comparison_not_object_identity(self):
        """
        ENFORCE: Integration tests MUST use ID comparison across DTO/Entity boundary

        Pattern: assert entity.id in {dto.id for dto in dtos} ✅
        Antipattern: assert entity in dtos ❌

        Convention reference: dto.convention.yaml lines 567-599

        This test scans all integration test files for "assert X in Y" patterns
        and flags potential violations where:
        - X looks like an entity (e.g., dilemma.fragment_a, returned_entity)
        - Y looks like a DTO list (e.g., fragments, dto_list)
        - Neither X nor Y use .id (meaning it's object identity, not ID comparison)
        """
        integration_tests = find_integration_test_files()

        if not integration_tests:
            pytest.skip("No integration tests found")

        violations = []

        for test_file in integration_tests:
            assertions = extract_assert_in_statements(test_file)

            for line_num, left_expr, right_expr in assertions:
                # Check if this is already using ID comparison (correct pattern)
                if is_id_comparison(left_expr, right_expr):
                    continue  # ✅ Already correct

                # Check if this looks like entity in dto_list (antipattern)
                if looks_like_entity_access(left_expr) and looks_like_dto_list(right_expr):
                    violations.append({
                        'file': test_file.relative_to(REPO_ROOT),
                        'line': line_num,
                        'assertion': f"assert {left_expr} in {right_expr}",
                        'suggestion': f"assert {left_expr}.id in {{{right_expr[0]}.id for {right_expr[0]} in {right_expr}}}"
                    })

        # Report violations with helpful message
        if violations:
            error_msg = [
                "\n❌ Found integration tests using object identity instead of ID comparison",
                "\nConvention: dto.convention.yaml lines 567-599",
                "\nPattern: After DTO→Entity conversion, use ID comparison not object identity\n"
            ]

            for v in violations:
                error_msg.append(f"\n{v['file']}:{v['line']}")
                error_msg.append(f"  ❌ Antipattern: {v['assertion']}")
                error_msg.append(f"  ✅ Fix: {v['suggestion']}")

            error_msg.append("\n\nWhy this matters:")
            error_msg.append("  - Mapper creates new entity instances")
            error_msg.append("  - Entity ≠ DTO (different types)")
            error_msg.append("  - Python 'in' uses __eq__ or identity")
            error_msg.append("  - IDs are stable across DTO/Entity boundary")

            pytest.fail('\n'.join(error_msg))

    def test_dto_convention_documents_testing_pattern(self):
        """
        META: Verify the DTO convention file documents this testing pattern.

        Ensures the convention file contains:
        - testing_patterns.dto_entity_boundary_assertions section
        - Antipattern example
        - Correct pattern example
        """
        if not DTO_CONVENTION.exists():
            pytest.skip("DTO convention file not found")

        content = DTO_CONVENTION.read_text()

        # Check for key sections
        assert 'testing_patterns' in content, \
            "DTO convention missing 'testing_patterns' section"

        assert 'dto_entity_boundary_assertions' in content, \
            "DTO convention missing 'dto_entity_boundary_assertions' pattern"

        assert 'antipattern' in content.lower(), \
            "DTO convention missing antipattern example"

        assert 'assert returned_entity in dto_list' in content or 'in dto_list' in content, \
            "DTO convention missing antipattern code example"

        assert 'assert returned_entity.id in' in content or '.id in' in content, \
            "DTO convention missing correct pattern code example"


if __name__ == '__main__':
    # Run with: pytest atdd/coder/test_dto_testing_patterns.py -v
    pytest.main([__file__, '-v'])

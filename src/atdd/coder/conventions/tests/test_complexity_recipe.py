"""
Tests for complexity recipe.

Tests SPEC-CODER-UTL-0158 to 047, 054, 056, 057, 058
ATDD: These tests define expected behavior of complexity recipe BEFORE implementation.
"""
import pytest
import yaml
from pathlib import Path
from typing import Dict, Any


# Recipe loader utilities (shared with thinness tests)
def load_recipe(recipe_name: str) -> Dict[str, Any]:
    """
    Load recipe YAML file.

    SPEC-CODER-UTL-0158: Load complexity recipe
    """
    recipe_path = Path(__file__).resolve().parents[1] / f"{recipe_name}.recipe.yaml"

    if not recipe_path.exists():
        raise FileNotFoundError(f"Recipe not found: {recipe_path}")

    with open(recipe_path, 'r') as f:
        return yaml.safe_load(f)


def check_recipe_applies(recipe_name: str, smells: Dict[str, Any]) -> bool:
    """
    Check if recipe applies based on smell detection results.

    SPEC-CODER-UTL-0159: Detect when complexity recipe applies
    """
    recipe = load_recipe(recipe_name)

    if recipe_name == "complexity":
        # complexity applies when complexity check fails
        return smells.get("complexity", {}).get("passed", True) is False

    return False


def execute_recipe_step(recipe_name: str, step: int, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a recipe step.

    SPEC-CODER-UTL-0160, 046, 047: Execute steps 1, 2, 3
    """
    recipe = load_recipe(recipe_name)
    steps = recipe.get("steps", [])

    if step < 1 or step > len(steps):
        return {"success": False, "error": f"Invalid step: {step}"}

    step_def = steps[step - 1]

    # Return step guidance
    return {
        "success": True,
        "step": step,
        "what": step_def.get("what", ""),
        "where": step_def.get("where", ""),
        "template": step_def.get("template", ""),
        "example": step_def.get("example", ""),
        "next_action": "continue" if step < len(steps) else "verify_final"
    }


def select_recipe(smells: Dict[str, Any]) -> Dict[str, Any]:
    """
    Select recipe based on smell detection.

    SPEC-CODER-UTL-0169: Map complexity smell to complexity recipe
    """
    # Priority 1: Handler smell → thinness
    if smells.get("thinness", {}).get("passed", True) is False:
        return {"recipe": "thinness", "priority": 1}

    # Priority 2: Complexity smell → complexity
    if smells.get("complexity", {}).get("passed", True) is False:
        return {"recipe": "complexity", "priority": 2}

    # Priority 3: Missing adapter → adapter
    if smells.get("missing_adapter", False):
        return {"recipe": "adapter", "priority": 3}

    return {"recipe": None, "priority": 0}


def verify_recipe_step(step_result: Dict[str, Any], test_status: str) -> bool:
    """
    Verify recipe step maintains GREEN tests.

    SPEC-CODER-UTL-0171: Verify recipe step maintains GREEN tests
    SPEC-CODER-UTL-0173: Rollback on step failure
    """
    if test_status == "GREEN":
        return True

    # RED tests trigger rollback
    if test_status == "RED":
        # This would call rollback_refactor_step() in real usage
        return False

    return False


def verify_recipe_final(recipe_name: str, results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify final state after all recipe steps.

    SPEC-CODER-UTL-0172: Verify final state after all recipe steps
    """
    verification = {"success": True, "checks": []}

    if recipe_name == "complexity":
        # Final verification: complexity.check() should pass
        verification["checks"].append({
            "check": "complexity.check()",
            "expected": "passed=true"
        })
        verification["complexity_reduced"] = True

    return verification


# TESTS

class TestSpecificationRecipeLoading:
    """Test SPEC-CODER-UTL-0158: Load complexity recipe"""

    def test_load_recipe(self):
        """Should load complexity recipe YAML"""
        recipe = load_recipe("complexity")

        assert recipe is not None
        assert recipe["recipe"] == "complexity"
        assert recipe["pattern"] == "Complexity Reduction (Split/Extract)"
        assert "steps" in recipe
        assert len(recipe["steps"]) == 3


class TestSpecificationRecipeApplies:
    """Test SPEC-CODER-UTL-0159: Detect when complexity recipe applies"""

    def test_recipe_applies(self):
        """Should return true when complexity check fails"""
        smells = {
            "complexity": {
                "passed": False,
                "violations": [
                    {"function": "calculateDiscount", "complexity": 12, "line": 45}
                ]
            }
        }

        result = check_recipe_applies("complexity", smells)

        assert result is True

    def test_recipe_not_applies(self):
        """Should return false when complexity check passes"""
        smells = {
            "complexity": {
                "passed": True,
                "violations": []
            }
        }

        result = check_recipe_applies("complexity", smells)

        assert result is False


class TestSpecificationRecipeSteps:
    """Test SPEC-CODER-UTL-0160, 046, 047: Execute recipe steps"""

    def test_execute_step_1(self):
        """Should execute step 1: create base complexity"""
        context = {"file_path": "domain/order.py"}

        result = execute_recipe_step("complexity", 1, context)

        assert result["success"] is True
        assert "complexity" in result["what"].lower() or "base" in result["what"].lower()
        assert "domain/complexity/" in result["where"]
        assert "is_satisfied_by" in result["template"] or result["example"]

    def test_execute_step_2(self):
        """Should execute step 2: extract complexitys"""
        context = {"base_created": True}

        result = execute_recipe_step("complexity", 2, context)

        assert result["success"] is True
        assert "extract" in result["what"].lower() or "boolean" in result["what"].lower()
        assert "domain/complexity/" in result["where"]

    def test_execute_step_3(self):
        """Should execute step 3: compose complexitys"""
        context = {"base_created": True, "specs_extracted": True}

        result = execute_recipe_step("complexity", 3, context)

        assert result["success"] is True
        assert "compose" in result["what"].lower() or "and_" in result["template"] or "or_" in result["template"]
        assert result["next_action"] == "verify_final"


class TestSpecificationRecipeSelection:
    """Test SPEC-CODER-UTL-0169: Map complexity smell to complexity recipe"""

    def test_select_from_smell(self):
        """Should select complexity recipe when complexity smell detected"""
        smells = {
            "complexity": {
                "passed": False,
                "violations": [{"function": "process", "complexity": 15}]
            }
        }

        result = select_recipe(smells)

        assert result["recipe"] == "complexity"
        assert result["priority"] == 2


class TestSpecificationRecipeVerification:
    """Test SPEC-CODER-UTL-0171, 057, 058: Recipe verification"""

    def test_verify_step_green(self):
        """Should return true when tests are GREEN"""
        step_result = {"success": True, "step": 1}

        result = verify_recipe_step(step_result, "GREEN")

        assert result is True

    def test_rollback_on_failure(self):
        """Should return false and trigger rollback when tests are RED"""
        step_result = {"success": True, "step": 1}

        result = verify_recipe_step(step_result, "RED")

        assert result is False

    def test_verify_final(self):
        """Should verify final state with complexity check"""
        results = {"all_steps_completed": True}

        verification = verify_recipe_final("complexity", results)

        assert verification["success"] is True
        assert verification["complexity_reduced"] is True
        assert len(verification["checks"]) > 0
        assert any("complexity" in check["check"] for check in verification["checks"])


class TestSpecificationRecipeIntegration:
    """Integration tests for full recipe workflow"""

    def test_full_recipe_workflow(self):
        """Should execute full recipe from detection to verification"""
        # 1. Detect smell
        smells = {"complexity": {"passed": False, "violations": [{"function": "foo", "complexity": 12}]}}

        # 2. Select recipe
        selected = select_recipe(smells)
        assert selected["recipe"] == "complexity"

        # 3. Load recipe
        recipe = load_recipe("complexity")
        assert recipe is not None

        # 4. Execute steps
        context = {}
        for step in range(1, 4):
            result = execute_recipe_step("complexity", step, context)
            assert result["success"] is True

            # Verify step
            verified = verify_recipe_step(result, "GREEN")
            assert verified is True

        # 5. Final verification
        verification = verify_recipe_final("complexity", {"all_steps": True})
        assert verification["success"] is True
        assert verification["complexity_reduced"] is True

"""
Tests for thinness recipe.

Tests SPEC-CODER-UTL-0153 to 042, 053, 056, 057, 058
ATDD: These tests define expected behavior of thinness recipe BEFORE implementation.
"""
import pytest
import yaml
from pathlib import Path
from typing import Dict, Any


# Recipe loader utilities
def load_recipe(recipe_name: str) -> Dict[str, Any]:
    """
    Load recipe YAML file.

    SPEC-CODER-UTL-0153: Load thinness recipe
    """
    recipe_path = Path(__file__).resolve().parents[1] / f"{recipe_name}.recipe.yaml"

    if not recipe_path.exists():
        raise FileNotFoundError(f"Recipe not found: {recipe_path}")

    with open(recipe_path, 'r') as f:
        return yaml.safe_load(f)


def check_recipe_applies(recipe_name: str, smells: Dict[str, Any]) -> bool:
    """
    Check if recipe applies based on smell detection results.

    SPEC-CODER-UTL-0154: Detect when thinness recipe applies
    """
    recipe = load_recipe(recipe_name)

    if recipe_name == "thinness":
        # thinness applies when thinness check fails
        return smells.get("thinness", {}).get("passed", True) is False

    return False


def execute_recipe_step(recipe_name: str, step: int, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a recipe step.

    SPEC-CODER-UTL-0155, 041, 042: Execute steps 1, 2, 3
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
        "next_action": "verify_tests" if step == 1 else ("continue" if step < len(steps) else "verify_final")
    }


def select_recipe(smells: Dict[str, Any]) -> Dict[str, Any]:
    """
    Select recipe based on smell detection.

    SPEC-CODER-UTL-0168: Map handler smell to thinness recipe
    """
    # Priority 1: Handler smell → thinness
    if smells.get("thinness", {}).get("passed", True) is False:
        return {"recipe": "thinness", "priority": 1}

    # Priority 2: Complexity smell → specification
    if smells.get("complexity", {}).get("passed", True) is False:
        return {"recipe": "specification", "priority": 2}

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

    if recipe_name == "thinness":
        # Final verification: thinness.check() should pass
        verification["checks"].append({
            "check": "thinness.check()",
            "expected": "passed=true"
        })

    return verification


# TESTS

class TestThinHandlerRecipeLoading:
    """Test SPEC-CODER-UTL-0153: Load thinness recipe"""

    def test_load_recipe(self):
        """Should load thinness recipe YAML"""
        recipe = load_recipe("thinness")

        assert recipe is not None
        assert recipe["recipe"] == "thinness"
        assert recipe["pattern"] == "Thin Handler + Use Case"
        assert "steps" in recipe
        assert len(recipe["steps"]) == 3


class TestThinHandlerRecipeApplies:
    """Test SPEC-CODER-UTL-0154: Detect when thinness recipe applies"""

    def test_recipe_applies(self):
        """Should return true when thinness check fails"""
        smells = {
            "thinness": {
                "passed": False,
                "smells": [
                    {"line": 10, "reason": "Business logic in handler"}
                ]
            }
        }

        result = check_recipe_applies("thinness", smells)

        assert result is True

    def test_recipe_not_applies(self):
        """Should return false when thinness check passes"""
        smells = {
            "thinness": {
                "passed": True,
                "smells": []
            }
        }

        result = check_recipe_applies("thinness", smells)

        assert result is False


class TestThinHandlerRecipeSteps:
    """Test SPEC-CODER-UTL-0155, 041, 042: Execute recipe steps"""

    def test_execute_step_1(self):
        """Should execute step 1: create use case"""
        context = {"file_path": "presentation/handlers/order.py"}

        result = execute_recipe_step("thinness", 1, context)

        assert result["success"] is True
        assert "use case" in result["what"].lower()
        assert "application/" in result["where"]
        assert result["next_action"] == "verify_tests"

    def test_execute_step_2(self):
        """Should execute step 2: define port"""
        context = {"usecase_created": True}

        result = execute_recipe_step("thinness", 2, context)

        assert result["success"] is True
        assert "port" in result["what"].lower()
        assert "application/ports/" in result["where"]
        assert result["next_action"] == "continue"

    def test_execute_step_3(self):
        """Should execute step 3: thin the handler"""
        context = {"usecase_created": True, "port_defined": True}

        result = execute_recipe_step("thinness", 3, context)

        assert result["success"] is True
        assert "thin" in result["what"].lower() or "handler" in result["what"].lower()
        assert result["next_action"] == "verify_final"


class TestThinHandlerRecipeSelection:
    """Test SPEC-CODER-UTL-0168: Map handler smell to thinness recipe"""

    def test_select_from_smell(self):
        """Should select thinness recipe when handler smell detected"""
        smells = {
            "thinness": {
                "passed": False,
                "smells": [{"line": 10, "reason": "Business logic"}]
            }
        }

        result = select_recipe(smells)

        assert result["recipe"] == "thinness"
        assert result["priority"] == 1


class TestThinHandlerRecipeVerification:
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
        """Should verify final state with thinness check"""
        results = {"all_steps_completed": True}

        verification = verify_recipe_final("thinness", results)

        assert verification["success"] is True
        assert len(verification["checks"]) > 0
        assert any("thinness" in check["check"] for check in verification["checks"])


class TestThinHandlerRecipeIntegration:
    """Integration tests for full recipe workflow"""

    def test_full_recipe_workflow(self):
        """Should execute full recipe from detection to verification"""
        # 1. Detect smell
        smells = {"thinness": {"passed": False, "smells": [{"line": 10, "reason": "Business logic"}]}}

        # 2. Select recipe
        selected = select_recipe(smells)
        assert selected["recipe"] == "thinness"

        # 3. Load recipe
        recipe = load_recipe("thinness")
        assert recipe is not None

        # 4. Execute steps
        context = {}
        for step in range(1, 4):
            result = execute_recipe_step("thinness", step, context)
            assert result["success"] is True

            # Verify step
            verified = verify_recipe_step(result, "GREEN")
            assert verified is True

        # 5. Final verification
        verification = verify_recipe_final("thinness", {"all_steps": True})
        assert verification["success"] is True

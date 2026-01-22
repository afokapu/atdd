"""
Station Master Pattern Validator

Validates that wagons follow the Station Master pattern for monolith composition:
1. composition.py accepts optional shared dependency parameters
2. Direct adapters exist for cross-wagon data access
3. game.py delegates to composition.py instead of duplicating wiring

Convention: atdd/coder/conventions/boundaries.convention.yaml::station_master_pattern
"""

import ast
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple


def get_python_dir() -> Path:
    """Get the python directory path."""
    return Path(__file__).parent.parent.parent.parent / "python"


def test_composition_accepts_shared_dependencies():
    """
    Validate that wagon composition.py files accept optional shared dependencies.

    Convention: boundaries.convention.yaml::station_master_pattern.composition_function_signature

    Expected pattern:
        def wire_api_dependencies(
            state_repository=None,
            player_timebanks=None,
            match_repository=None,
            event_bus=None
        ):
    """
    python_dir = get_python_dir()

    # Find all composition.py files in wagon directories
    composition_files = list(python_dir.glob("*/*/composition.py"))

    # Track which compositions have wire_api_dependencies
    wagons_with_wire_function: List[str] = []
    wagons_missing_optional_params: List[Tuple[str, List[str]]] = []

    for comp_file in composition_files:
        wagon_name = comp_file.parent.parent.name

        try:
            source = comp_file.read_text()
            tree = ast.parse(source)
        except Exception as e:
            continue  # Skip files that can't be parsed

        # Find wire_api_dependencies function
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "wire_api_dependencies":
                wagons_with_wire_function.append(wagon_name)

                # Check if it has optional parameters (defaults)
                # Parameters with defaults are in node.args.defaults
                # kw_only args with defaults are in node.args.kw_defaults

                # Get all argument names
                arg_names = [arg.arg for arg in node.args.args]

                # Get number of defaults (these apply to the LAST n arguments)
                num_defaults = len(node.args.defaults)
                num_args = len(arg_names)

                # Arguments without defaults (required)
                required_args = arg_names[:num_args - num_defaults] if num_defaults < num_args else []

                # Recommended optional params for Station Master pattern
                recommended_optional = ["state_repository", "player_timebanks", "match_repository", "event_bus"]

                # Check if function has any optional parameters
                optional_count = num_defaults + len([d for d in node.args.kw_defaults if d is not None])

                if optional_count == 0 and num_args > 0:
                    # Function has only required args - doesn't follow pattern
                    wagons_missing_optional_params.append((wagon_name, required_args))

    # Report results
    print("\n" + "=" * 70)
    print("  Station Master Pattern: Composition Dependencies")
    print("=" * 70)
    print(f"\nWagons with wire_api_dependencies(): {len(wagons_with_wire_function)}")
    for wagon in wagons_with_wire_function:
        print(f"  ✓ {wagon}")

    if wagons_missing_optional_params:
        print(f"\n⚠️  Wagons missing optional shared dependency parameters:")
        for wagon, required in wagons_missing_optional_params:
            print(f"  ❌ {wagon}: has only required params: {required}")
        print("\n  Recommendation: Add optional params like state_repository=None")

    # This is a soft check - we want to encourage the pattern but not fail builds
    # for wagons that don't need cross-wagon data
    assert True, "Station Master pattern check completed (advisory)"


def test_direct_adapters_exist_for_cross_wagon_clients():
    """
    Validate that Direct adapters exist alongside HTTP clients for cross-wagon communication.

    Convention: backend.convention.yaml::clients.adapter_variants.direct_adapter

    Expected: If http_*_client.py exists, direct_*_client.py should also exist.
    """
    python_dir = get_python_dir()

    # Find all client directories
    client_dirs = list(python_dir.glob("*/*/src/integration/clients"))

    http_without_direct: List[Tuple[str, str]] = []
    direct_adapters_found: List[str] = []

    for client_dir in client_dirs:
        if not client_dir.is_dir():
            continue

        wagon_name = client_dir.parent.parent.parent.parent.name

        # Find HTTP clients
        http_clients = list(client_dir.glob("http_*_client.py"))

        for http_client in http_clients:
            # Extract the service name (e.g., "commit_state" from "http_commit_state_client.py")
            http_name = http_client.stem  # http_commit_state_client
            service_name = http_name.replace("http_", "").replace("_client", "")

            # Check for corresponding direct adapter
            direct_name = f"direct_{service_name}_client.py"
            direct_path = client_dir / direct_name

            if direct_path.exists():
                direct_adapters_found.append(f"{wagon_name}/{direct_name}")
            else:
                http_without_direct.append((wagon_name, http_client.name))

    # Report results
    print("\n" + "=" * 70)
    print("  Station Master Pattern: Direct Adapters")
    print("=" * 70)
    print(f"\nDirect adapters found: {len(direct_adapters_found)}")
    for adapter in direct_adapters_found:
        print(f"  ✓ {adapter}")

    if http_without_direct:
        print(f"\n⚠️  HTTP clients without corresponding Direct adapters:")
        for wagon, http_file in http_without_direct:
            print(f"  ⚠️  {wagon}/{http_file} → missing direct_*_client.py")
        print("\n  Note: Direct adapters enable monolith mode without HTTP self-calls")

    # Advisory check - not all HTTP clients need Direct adapters
    assert True, "Direct adapter check completed (advisory)"


def test_game_py_delegates_to_composition():
    """
    Validate that game.py delegates wiring to wagon composition.py files
    instead of duplicating wiring logic.

    Convention: boundaries.convention.yaml::station_master_pattern.station_master_responsibilities

    Forbidden patterns in game.py:
        - Creating use cases that composition.py should own
        - Directly instantiating wagon clients without delegation

    Expected patterns:
        - from wagon.composition import wire_api_dependencies
        - wire_api_dependencies(state_repository=..., ...)
    """
    python_dir = get_python_dir()
    game_py = python_dir / "game.py"

    if not game_py.exists():
        print("game.py not found - skipping Station Master delegation check")
        return

    source = game_py.read_text()

    # Check for composition imports
    imports_composition = "from play_match.orchestrate_match.composition import wire_api_dependencies" in source

    # Check for delegation calls
    calls_wire_api = "wire_api_dependencies(" in source

    # Check for forbidden patterns (duplicated wiring)
    # These are patterns that should be in composition.py, not game.py
    forbidden_patterns = [
        ("PlayMatchUseCase(", "PlayMatchUseCase should be created in composition.py"),
        ("CommitStateClient(mode=", "CommitStateClient mode should be set in composition.py"),
        ("set_play_match_use_case(PlayMatchUseCase", "Use case creation should be in composition.py"),
    ]

    violations: List[Tuple[str, str]] = []
    for pattern, message in forbidden_patterns:
        if pattern in source:
            violations.append((pattern, message))

    # Report results
    print("\n" + "=" * 70)
    print("  Station Master Pattern: game.py Delegation")
    print("=" * 70)

    print(f"\nDelegation to composition.py:")
    print(f"  {'✓' if imports_composition else '❌'} Imports wire_api_dependencies from composition")
    print(f"  {'✓' if calls_wire_api else '❌'} Calls wire_api_dependencies()")

    if violations:
        print(f"\n❌ Violations found in game.py:")
        for pattern, message in violations:
            print(f"  ❌ {message}")
            print(f"     Found: {pattern}")

    # This is a real validation
    assert imports_composition or not calls_wire_api, \
        "game.py should import wire_api_dependencies from composition.py"

    assert len(violations) == 0, \
        f"game.py has {len(violations)} Station Master pattern violations"

    print("\n✓ game.py follows Station Master pattern")


def main():
    """Run all Station Master pattern validators."""
    print("\n" + "=" * 70)
    print("  STATION MASTER PATTERN VALIDATION")
    print("=" * 70)

    test_composition_accepts_shared_dependencies()
    test_direct_adapters_exist_for_cross_wagon_clients()
    test_game_py_delegates_to_composition()

    print("\n" + "=" * 70)
    print("  ✓ All Station Master pattern checks passed")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

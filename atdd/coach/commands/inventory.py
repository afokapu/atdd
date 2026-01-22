#!/usr/bin/env python3
"""
Generate comprehensive repository inventory.

Catalogs all artifacts across the ATDD lifecycle:
- Platform: .claude/ infrastructure (conventions, schemas, commands, agents, utils, actions)
- Planning: Trains, wagons, features, WMBT acceptance (C/L/E/P patterns)
- Testing: Contracts, telemetry, test files (meta + feature tests)
- Coding: Implementation files (Python, Dart, TypeScript)
- Tracking: Facts/logs, ATDD documentation

Usage:
    python atdd/inventory.py > atdd/INVENTORY.yaml
    pytest atdd/ --inventory
"""

import yaml
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any


class RepositoryInventory:
    """Generate comprehensive repository inventory."""

    def __init__(self, repo_root: Path = None):
        self.repo_root = repo_root or Path(__file__).parent.parent
        self.inventory = {
            "inventory": {
                "generated_at": datetime.now().isoformat(),
                "repository": str(self.repo_root.name),
            }
        }

    def scan_platform_infrastructure(self) -> Dict[str, Any]:
        """Scan .claude/ for platform infrastructure."""
        claude_dir = self.repo_root / ".claude"

        if not claude_dir.exists():
            return {"total": 0}

        # Conventions
        convention_files = list(claude_dir.glob("conventions/**/*.yaml"))
        convention_files.extend(claude_dir.glob("conventions/**/*.yml"))

        # Schemas
        schema_files = list(claude_dir.glob("schemas/**/*.json"))

        # Commands
        command_files = list(claude_dir.glob("commands/**/*"))
        command_files = [f for f in command_files if f.is_file()]

        # Agents
        agent_files = list(claude_dir.glob("agents/**/*.yaml"))
        agent_files.extend(claude_dir.glob("agents/**/*.json"))

        # Utils
        util_files = list(claude_dir.glob("utils/**/*"))
        util_files = [f for f in util_files if f.is_file() and f.suffix in [".yaml", ".json", ".yml"]]

        # Actions
        action_files = list(claude_dir.glob("actions/**/*.yaml"))
        action_files.extend(claude_dir.glob("actions/**/*.json"))

        return {
            "total": len(convention_files) + len(schema_files) + len(command_files) + len(agent_files) + len(util_files) + len(action_files),
            "conventions": len(convention_files),
            "schemas": len(schema_files),
            "commands": len(command_files),
            "agents": len(agent_files),
            "utils": len(util_files),
            "actions": len(action_files)
        }

    def scan_trains(self) -> Dict[str, Any]:
        """Scan plan/ for train manifests (aggregations of wagons)."""
        plan_dir = self.repo_root / "plan"

        if not plan_dir.exists():
            return {"total": 0, "trains": []}

        # Load trains registry
        trains_file = plan_dir / "_trains.yaml"
        all_trains = []

        if trains_file.exists():
            with open(trains_file) as f:
                data = yaml.safe_load(f)
                trains_data = data.get("trains", {})

                # Flatten the nested structure
                # Input: {"0-commons": {"00-commons-nominal": [train1, train2], ...}, ...}
                # Output: flat list of all trains
                for theme_key, categories in trains_data.items():
                    if isinstance(categories, dict):
                        for category_key, trains_list in categories.items():
                            if isinstance(trains_list, list):
                                all_trains.extend(trains_list)

        # Count by theme
        by_theme = defaultdict(int)
        train_ids = []

        for train in all_trains:
            train_id = train.get("train_id", "unknown")
            train_ids.append(train_id)

            # Extract theme from train_id (first digit maps to theme)
            if train_id and len(train_id) > 0 and train_id[0].isdigit():
                theme_digit = train_id[0]
                theme_map = {
                    "0": "commons", "1": "mechanic", "2": "scenario", "3": "match",
                    "4": "sensory", "5": "player", "6": "league", "7": "audience",
                    "8": "monetization", "9": "partnership"
                }
                theme = theme_map.get(theme_digit, "unknown")
                by_theme[theme] += 1

        # Find train detail files
        train_detail_files = list((plan_dir / "_trains").glob("*.yaml")) if (plan_dir / "_trains").exists() else []

        return {
            "total": len(all_trains),
            "by_theme": dict(by_theme),
            "train_ids": train_ids,
            "detail_files": len(train_detail_files)
        }

    def scan_wagons(self) -> Dict[str, Any]:
        """Scan plan/ for wagon manifests."""
        plan_dir = self.repo_root / "plan"

        if not plan_dir.exists():
            return {"total": 0, "wagons": []}

        # Load wagons registry
        wagons_file = plan_dir / "_wagons.yaml"
        wagons_data = []

        if wagons_file.exists():
            with open(wagons_file) as f:
                data = yaml.safe_load(f)
                wagons_data = data.get("wagons", [])

        # Count by status
        total = len(wagons_data)
        by_status = defaultdict(int)
        by_theme = defaultdict(int)

        for wagon in wagons_data:
            status = wagon.get("status", "unknown")
            theme = wagon.get("theme", "unknown")
            by_status[status] += 1
            by_theme[theme] += 1

        return {
            "total": total,
            "active": by_status.get("active", 0),
            "draft": by_status.get("draft", 0),
            "by_theme": dict(by_theme),
            "manifests": [w.get("manifest") for w in wagons_data]
        }

    def scan_contracts(self) -> Dict[str, Any]:
        """Scan contracts/ for contract schemas."""
        contracts_dir = self.repo_root / "contracts"

        if not contracts_dir.exists():
            return {"total": 0, "by_domain": {}}

        # Find all schema files
        schema_files = list(contracts_dir.glob("**/*.schema.json"))

        by_domain = defaultdict(list)

        for schema_file in schema_files:
            # Extract domain from path
            rel_path = schema_file.relative_to(contracts_dir)
            domain = rel_path.parts[0] if rel_path.parts else "unknown"

            # Load schema to get $id
            try:
                with open(schema_file) as f:
                    schema = json.load(f)
                    schema_id = schema.get("$id", "unknown")
                    by_domain[domain].append({
                        "path": str(rel_path),
                        "id": schema_id
                    })
            except:
                by_domain[domain].append({
                    "path": str(rel_path),
                    "id": "error"
                })

        return {
            "total": len(schema_files),
            "by_domain": {
                domain: {
                    "count": len(schemas),
                    "schemas": [s["id"] for s in schemas]
                }
                for domain, schemas in by_domain.items()
            }
        }

    def scan_telemetry(self) -> Dict[str, Any]:
        """Scan telemetry/ for signal definitions."""
        telemetry_dir = self.repo_root / "telemetry"

        if not telemetry_dir.exists():
            return {"total": 0, "by_domain": {}}

        # Find all signal files
        signal_files = list(telemetry_dir.glob("**/*.signal.yaml"))

        by_domain = defaultdict(int)

        for signal_file in signal_files:
            rel_path = signal_file.relative_to(telemetry_dir)
            domain = rel_path.parts[0] if rel_path.parts else "unknown"
            by_domain[domain] += 1

        return {
            "total": len(signal_files),
            "by_domain": dict(by_domain)
        }

    def count_test_cases_in_file(self, test_file: Path) -> int:
        """Count number of test functions/cases in a test file."""
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Count test functions (def test_* or async def test_*)
                import re
                pattern = r'^\s*(?:async\s+)?def\s+test_\w+'
                matches = re.findall(pattern, content, re.MULTILINE)
                return len(matches)
        except:
            return 0

    def scan_tests(self) -> Dict[str, Any]:
        """Scan all test files and count test cases across the repository."""

        # Meta-tests in atdd/
        atdd_dir = self.repo_root / "atdd"
        planner_tests = []
        tester_tests = []
        coder_tests = []

        if atdd_dir.exists():
            planner_tests = list((atdd_dir / "planner").glob("test_*.py")) if (atdd_dir / "planner").exists() else []
            tester_tests = list((atdd_dir / "tester").glob("test_*.py")) if (atdd_dir / "tester").exists() else []
            coder_tests = list((atdd_dir / "coder").glob("test_*.py")) if (atdd_dir / "coder").exists() else []

        # Python feature tests - look in any test/ subdirectory
        python_tests = []
        if (self.repo_root / "python").exists():
            # Find all test_*.py files within any test/ directory structure
            for test_file in (self.repo_root / "python").rglob("test_*.py"):
                # Ensure it's within a test/ directory somewhere in its path
                if "/test/" in str(test_file) or "\\test\\" in str(test_file):
                    python_tests.append(test_file)

        # TypeScript feature tests
        ts_tests = []
        if (self.repo_root / "web").exists():
            ts_tests.extend((self.repo_root / "web").glob("**/*.test.ts"))
            ts_tests.extend((self.repo_root / "web").glob("**/*.test.tsx"))
        if (self.repo_root / "supabase").exists():
            ts_tests.extend((self.repo_root / "supabase").glob("**/*.test.ts"))

        # Platform/infrastructure tests (in .claude/)
        platform_tests = []
        if (self.repo_root / ".claude").exists():
            platform_tests = list((self.repo_root / ".claude").rglob("test_*.py"))

        # Count test cases (functions) in Python test files
        planner_cases = sum(self.count_test_cases_in_file(f) for f in planner_tests)
        tester_cases = sum(self.count_test_cases_in_file(f) for f in tester_tests)
        coder_cases = sum(self.count_test_cases_in_file(f) for f in coder_tests)
        platform_cases = sum(self.count_test_cases_in_file(f) for f in platform_tests)
        python_cases = sum(self.count_test_cases_in_file(f) for f in python_tests)

        meta_files = len(planner_tests) + len(tester_tests) + len(coder_tests) + len(platform_tests)
        feature_files = len(python_tests) + len(ts_tests)

        meta_cases = planner_cases + tester_cases + coder_cases + platform_cases
        feature_cases = python_cases  # Dart/TS case counting would require parsing those languages

        return {
            "total_files": meta_files + feature_files,
            "total_cases": meta_cases + feature_cases,
            "meta_tests": {
                "files": {
                    "planner": len(planner_tests),
                    "tester": len(tester_tests),
                    "coder": len(coder_tests),
                    "platform": len(platform_tests),
                    "total": meta_files
                },
                "cases": {
                    "planner": planner_cases,
                    "tester": tester_cases,
                    "coder": coder_cases,
                    "platform": platform_cases,
                    "total": meta_cases
                }
            },
            "feature_tests": {
                "files": {
                    "python": len(python_tests),
                    "dart": len(dart_tests),
                    "typescript": len(ts_tests),
                    "total": feature_files
                },
                "cases": {
                    "python": python_cases,
                    "dart": "not_counted",
                    "typescript": "not_counted",
                    "total": feature_cases
                }
            }
        }

    def scan_features(self) -> Dict[str, Any]:
        """Scan plan/ for feature definitions."""
        plan_dir = self.repo_root / "plan"

        if not plan_dir.exists():
            return {"total": 0, "by_wagon": {}}

        # Find all feature YAML files
        feature_files = list(plan_dir.glob("**/features/*.yaml"))

        by_wagon = defaultdict(int)

        for feature_file in feature_files:
            rel_path = feature_file.relative_to(plan_dir)
            wagon = rel_path.parts[0] if rel_path.parts else "unknown"
            by_wagon[wagon] += 1

        return {
            "total": len(feature_files),
            "by_wagon": dict(by_wagon)
        }

    def scan_wmbt_acceptance(self) -> Dict[str, Any]:
        """Scan for WMBT (Write Meaningful Before Tests) acceptance files."""
        plan_dir = self.repo_root / "plan"

        if not plan_dir.exists():
            return {"total": 0, "by_category": {}, "by_wagon": {}}

        # WMBT categories: C (Contract), L (Logic), E (Edge), P (Performance)
        wmbt_patterns = {
            "contract": "C",
            "logic": "L",
            "edge": "E",
            "performance": "P"
        }

        by_category = defaultdict(int)
        by_wagon = defaultdict(lambda: defaultdict(int))
        total = 0

        for category, prefix in wmbt_patterns.items():
            # Find files matching pattern like C001.yaml, L001.yaml, etc.
            category_files = list(plan_dir.glob(f"**/{prefix}[0-9]*.yaml"))
            by_category[category] = len(category_files)
            total += len(category_files)

            # Count by wagon
            for wmbt_file in category_files:
                rel_path = wmbt_file.relative_to(plan_dir)
                wagon = rel_path.parts[0] if rel_path.parts else "unknown"
                by_wagon[wagon][category] += 1

        return {
            "total": total,
            "by_category": dict(by_category),
            "by_wagon": {
                wagon: dict(categories)
                for wagon, categories in by_wagon.items()
            }
        }

    def scan_acceptance_criteria(self) -> Dict[str, Any]:
        """Scan for acceptance criteria definitions (includes both AC-* and WMBT patterns)."""
        plan_dir = self.repo_root / "plan"

        if not plan_dir.exists():
            return {"total": 0, "by_wagon": {}}

        # Find all AC files (traditional AC-* pattern)
        ac_files = list(plan_dir.glob("**/AC-*.yaml"))

        by_wagon = defaultdict(int)

        for ac_file in ac_files:
            rel_path = ac_file.relative_to(plan_dir)
            wagon = rel_path.parts[0] if rel_path.parts else "unknown"
            by_wagon[wagon] += 1

        return {
            "total": len(ac_files),
            "by_wagon": dict(by_wagon)
        }

    def scan_facts(self) -> Dict[str, Any]:
        """Scan facts/ directory for audit logs and state tracking."""
        facts_dir = self.repo_root / "facts"

        if not facts_dir.exists():
            return {"total": 0, "files": []}

        # Find all files in facts directory
        fact_files = [f for f in facts_dir.glob("**/*") if f.is_file()]

        # Categorize by file type
        by_type = defaultdict(int)
        file_list = []

        for fact_file in fact_files:
            file_list.append(str(fact_file.relative_to(facts_dir)))
            if fact_file.suffix == ".log":
                by_type["logs"] += 1
            elif fact_file.suffix in [".yaml", ".yml"]:
                by_type["yaml"] += 1
            elif fact_file.suffix == ".json":
                by_type["json"] += 1
            else:
                by_type["other"] += 1

        return {
            "total": len(fact_files),
            "by_type": dict(by_type),
            "files": sorted(file_list)
        }

    def scan_atdd_docs(self) -> Dict[str, Any]:
        """Scan atdd/ directory for documentation and meta-files."""
        atdd_dir = self.repo_root / "atdd"

        if not atdd_dir.exists():
            return {"total": 0, "docs": []}

        # Find documentation files
        doc_patterns = ["*.md", "*.rst", "*.txt"]
        doc_files = []

        for pattern in doc_patterns:
            doc_files.extend(atdd_dir.glob(pattern))

        # Get list of doc names
        doc_names = [f.name for f in doc_files]

        return {
            "total": len(doc_files),
            "docs": sorted(doc_names)
        }

    def scan_implementations(self) -> Dict[str, Any]:
        """Scan implementation files (Python, Dart, TypeScript)."""

        # Python implementations
        python_files = []
        if (self.repo_root / "python").exists():
            python_files = [
                f for f in (self.repo_root / "python").glob("**/*.py")
                if "test" not in str(f) and "__pycache__" not in str(f)
            ]

        # TypeScript implementations
        ts_files = []
        if (self.repo_root / "supabase").exists():
            ts_files = [
                f for f in (self.repo_root / "supabase").glob("**/*.ts")
                if not f.name.endswith(".test.ts")
            ]
        if (self.repo_root / "web").exists():
            ts_files.extend([
                f for f in (self.repo_root / "web").glob("**/*.ts")
                if not f.name.endswith(".test.ts")
            ])
            ts_files.extend([
                f for f in (self.repo_root / "web").glob("**/*.tsx")
                if not f.name.endswith(".test.tsx")
            ])

        return {
            "total": len(python_files) + len(ts_files),
            "python": len(python_files),
            "typescript": len(ts_files)
        }

    def generate(self) -> Dict[str, Any]:
        """Generate complete inventory."""

        print("🔍 Scanning repository...", flush=True)

        # Platform infrastructure
        self.inventory["inventory"]["platform"] = self.scan_platform_infrastructure()
        print(f"  ✓ Found {self.inventory['inventory']['platform']['total']} platform infrastructure files")

        # Planning artifacts
        self.inventory["inventory"]["trains"] = self.scan_trains()
        print(f"  ✓ Found {self.inventory['inventory']['trains']['total']} trains")

        self.inventory["inventory"]["wagons"] = self.scan_wagons()
        print(f"  ✓ Found {self.inventory['inventory']['wagons']['total']} wagons")

        self.inventory["inventory"]["features"] = self.scan_features()
        print(f"  ✓ Found {self.inventory['inventory']['features']['total']} features")

        # Acceptance criteria (both traditional and WMBT)
        self.inventory["inventory"]["wmbt_acceptance"] = self.scan_wmbt_acceptance()
        print(f"  ✓ Found {self.inventory['inventory']['wmbt_acceptance']['total']} WMBT acceptance files")

        self.inventory["inventory"]["acceptance_criteria"] = self.scan_acceptance_criteria()
        print(f"  ✓ Found {self.inventory['inventory']['acceptance_criteria']['total']} traditional acceptance criteria")

        # Testing artifacts
        self.inventory["inventory"]["contracts"] = self.scan_contracts()
        print(f"  ✓ Found {self.inventory['inventory']['contracts']['total']} contracts")

        self.inventory["inventory"]["telemetry"] = self.scan_telemetry()
        print(f"  ✓ Found {self.inventory['inventory']['telemetry']['total']} telemetry signals")

        self.inventory["inventory"]["tests"] = self.scan_tests()
        test_files = self.inventory['inventory']['tests']['total_files']
        test_cases = self.inventory['inventory']['tests']['total_cases']
        print(f"  ✓ Found {test_files} test files with {test_cases} test cases")

        # Implementation artifacts
        self.inventory["inventory"]["implementations"] = self.scan_implementations()
        print(f"  ✓ Found {self.inventory['inventory']['implementations']['total']} implementation files")

        # Facts and documentation
        self.inventory["inventory"]["facts"] = self.scan_facts()
        print(f"  ✓ Found {self.inventory['inventory']['facts']['total']} facts/logs")

        self.inventory["inventory"]["atdd_docs"] = self.scan_atdd_docs()
        print(f"  ✓ Found {self.inventory['inventory']['atdd_docs']['total']} ATDD documentation files")

        return self.inventory


def main():
    """Generate and print inventory."""
    inventory = RepositoryInventory()
    data = inventory.generate()

    print("\n" + "=" * 60)
    print("Repository Inventory Generated")
    print("=" * 60 + "\n")

    # Output as YAML
    print(yaml.dump(data, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    main()

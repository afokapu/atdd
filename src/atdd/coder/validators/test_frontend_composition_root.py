"""
Test that the frontend train composition root class exists and exposes its
required method surface.

Validates:
- SPEC-CODER-TRAIN-0001: The file at frontend_composition_root.path exists,
  declares a class named class_name, and implements every name in
  required_methods (matched either as class methods or arrow-property methods).

Skips cleanly when .atdd/config.yaml has no frontend_composition_root key —
this keeps the validator opt-in for consumers that haven't adopted the
train_composition enforcement yet.

Convention: src/atdd/coder/conventions/frontend.convention.yaml → train_composition
Config: .atdd/config.yaml → frontend_composition_root
"""

import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config


REPO_ROOT = find_repo_root()


_CLASS_DECL_RE = re.compile(
    r"""export\s+(?:default\s+)?class\s+(?P<name>[A-Za-z_][\w]*)\b"""
)


def _extract_class_members(source: str, class_name: str) -> Set[str]:
    """Return the set of member names declared inside ``class <class_name> { ... }``.

    Members are matched as either traditional methods (``foo() { ... }``) or
    arrow-property methods (``foo = (...) => ...``). Visibility, arity, and
    return type are intentionally ignored — the goal is invariant presence,
    not signature fidelity.

    If the class is not found in ``source``, returns an empty set.
    """
    brace_start = None
    for match in _CLASS_DECL_RE.finditer(source):
        if match.group("name") != class_name:
            continue
        open_brace = source.find("{", match.end())
        if open_brace == -1:
            continue
        brace_start = open_brace
        break

    if brace_start is None:
        return set()

    depth = 0
    end = None
    for i in range(brace_start, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end is None:
        return set()

    body = source[brace_start + 1 : end]

    members: Set[str] = set()

    method_re = re.compile(
        r"""(?:^|\n)\s*(?:public\s+|private\s+|protected\s+|readonly\s+|static\s+|async\s+)*"""
        r"""(?P<name>[A-Za-z_][\w]*)\s*\("""
    )
    for m in method_re.finditer(body):
        members.add(m.group("name"))

    arrow_re = re.compile(
        r"""(?:^|\n)\s*(?:public\s+|private\s+|protected\s+|readonly\s+|static\s+|async\s+)*"""
        r"""(?P<name>[A-Za-z_][\w]*)\s*(?::\s*[^=;]+)?\s*=\s*(?:async\s*)?\("""
    )
    for m in arrow_re.finditer(body):
        members.add(m.group("name"))

    reserved = {"constructor", "if", "for", "while", "switch", "return", "throw", "new"}
    return members - reserved


def _analyze_composition_root(
    source_path: Path,
    class_name: str,
    required_methods: List[str],
) -> List[str]:
    """Return a list of SPEC-CODER-TRAIN-0001 violation messages.

    An empty list means the file passes.
    """
    violations: List[str] = []

    if not source_path.exists():
        violations.append(
            f"  SPEC-CODER-TRAIN-0001 FAIL: composition root file missing\n"
            f"    Path:      {source_path}\n"
            f"    Expected:  class {class_name} with methods {required_methods}\n"
            f"    Fix:       Create the file and declare the class per convention"
        )
        return violations

    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        violations.append(
            f"  SPEC-CODER-TRAIN-0001 FAIL: composition root file unreadable\n"
            f"    Path:      {source_path}\n"
            f"    Error:     {exc}"
        )
        return violations

    members = _extract_class_members(source, class_name)

    if not members:
        violations.append(
            f"  SPEC-CODER-TRAIN-0001 FAIL: composition root class not found\n"
            f"    Path:       {source_path}\n"
            f"    Expected:   class {class_name}\n"
            f"    Fix:        Rename the class or update class_name in .atdd/config.yaml"
        )
        return violations

    missing = [m for m in required_methods if m not in members]
    if missing:
        violations.append(
            f"  SPEC-CODER-TRAIN-0001 FAIL: composition root missing required methods\n"
            f"    Path:       {source_path}\n"
            f"    Class:      {class_name}\n"
            f"    Missing:    {missing}\n"
            f"    Found:      {sorted(members)}\n"
            f"    Fix:        Implement the missing methods or update required_methods"
        )

    return violations


def _load_composition_root_config() -> Dict:
    config = load_atdd_config(REPO_ROOT)
    return config.get("frontend_composition_root", {}) or {}


@pytest.mark.coder
def test_frontend_composition_root_matches_contract():
    """SPEC-CODER-TRAIN-0001: The configured composition root file must exist,
    declare the configured class, and implement every required method.

    Given: .atdd/config.yaml contains a frontend_composition_root block
    When:  The validator loads the referenced source file and parses it
    Then:  Missing file, missing class, or missing required methods are
           hard failures; absent configuration is a clean skip.
    """
    cfg = _load_composition_root_config()

    if not cfg or cfg.get("enabled") is False:
        pytest.skip(
            "frontend_composition_root not configured in .atdd/config.yaml "
            "(opt-in per SPEC-CODER-TRAIN-0001)"
        )

    path_value = cfg.get("path")
    class_name = cfg.get("class_name")
    required_methods = cfg.get("required_methods", [])

    if not path_value or not class_name:
        pytest.fail(
            "SPEC-CODER-TRAIN-0001 FAIL: frontend_composition_root missing "
            "required keys path and class_name"
        )

    source_path = (REPO_ROOT / path_value).resolve()
    violations = _analyze_composition_root(source_path, class_name, required_methods)

    if violations:
        pytest.fail(
            "\n\nfrontend_composition_root contract violation(s):\n\n"
            + "\n\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Unit tests for the pure helpers (run in every mode, no config required).
# ---------------------------------------------------------------------------


_POSITIVE_SOURCE = """
import { Wagon } from './wagon';

export class FrontendTrainRunner {
  private trains: Map<string, Wagon> = new Map();

  registerWagon(name: string, wagon: Wagon) {
    this.trains.set(name, wagon);
  }

  runTrain = async (id: string): Promise<void> => {
    const wagon = this.trains.get(id);
    if (wagon) {
      await wagon.render();
    }
  };

  resolveTemplate(id: string): string {
    return id;
  }
}
""".strip()


_NEGATIVE_SOURCE_RENAMED = """
export class OldTrainController {
  registerWagon() {}
  runTrain() {}
  resolveTemplate() {}
}
""".strip()


_NEGATIVE_SOURCE_MISSING_METHODS = """
export class FrontendTrainRunner {
  registerWagon() {}
}
""".strip()


def test_extract_class_members_positive():
    """Extractor finds both method-form and arrow-property members."""
    members = _extract_class_members(_POSITIVE_SOURCE, "FrontendTrainRunner")
    assert "registerWagon" in members
    assert "runTrain" in members
    assert "resolveTemplate" in members


def test_extract_class_members_renamed_class_returns_empty():
    """Extractor returns empty when the target class is not present in source."""
    members = _extract_class_members(_NEGATIVE_SOURCE_RENAMED, "FrontendTrainRunner")
    assert members == set()


def test_analyze_composition_root_reports_missing_methods(tmp_path):
    """Analyzer reports every required method missing from a present class."""
    src = tmp_path / "FrontendTrainRunner.ts"
    src.write_text(_NEGATIVE_SOURCE_MISSING_METHODS, encoding="utf-8")

    violations = _analyze_composition_root(
        src,
        class_name="FrontendTrainRunner",
        required_methods=["registerWagon", "runTrain", "resolveTemplate"],
    )

    assert len(violations) == 1
    message = violations[0]
    assert "missing required methods" in message
    assert "runTrain" in message
    assert "resolveTemplate" in message


def test_analyze_composition_root_passes_when_contract_satisfied(tmp_path):
    """Analyzer returns no violations when the class + methods are present."""
    src = tmp_path / "FrontendTrainRunner.ts"
    src.write_text(_POSITIVE_SOURCE, encoding="utf-8")

    violations = _analyze_composition_root(
        src,
        class_name="FrontendTrainRunner",
        required_methods=["registerWagon", "runTrain", "resolveTemplate"],
    )

    assert violations == []


def test_analyze_composition_root_reports_missing_file(tmp_path):
    """Analyzer reports a clear error when the source path does not exist."""
    src = tmp_path / "does_not_exist.ts"

    violations = _analyze_composition_root(
        src,
        class_name="FrontendTrainRunner",
        required_methods=["runTrain"],
    )

    assert len(violations) == 1
    assert "file missing" in violations[0]

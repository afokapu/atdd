"""Fixture: COACH-PKG-LAYOUT-001 clean shapes — package-relative resolution + suppressed sites."""

from pathlib import Path
from atdd.coach.utils.repo import find_repo_root

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


def package_relative_canonical():
    return ATDD_PKG_DIR / "coach" / "schemas" / "config.schema.json"


def package_relative_inline():
    return Path(atdd.__file__).resolve().parent / "coach" / "conventions"


def consumer_repo_path_no_src_atdd():
    return find_repo_root() / "plan" / "_trains.yaml"


def consumer_python_path():
    return find_repo_root() / "python" / "tests"


def find_repo_root_for_consumer_only():
    repo_root = find_repo_root()
    return repo_root / "contracts"


def suppressed_legitimate_use():
    return find_repo_root() / "src" / "atdd" / "coach" / "commands" / "tests"  # atdd:suppress(COACH-PKG-LAYOUT-001)

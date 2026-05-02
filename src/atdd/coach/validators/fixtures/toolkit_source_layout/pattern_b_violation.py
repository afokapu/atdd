"""Fixture: COACH-PKG-LAYOUT-002 violations — bare version("atdd") outside __init__'s try/except wrapper."""

from importlib.metadata import version
from importlib.metadata import version as pkg_version
import importlib.metadata


def bare_version_call():
    return version("atdd")


def aliased_pkg_version_call():
    return pkg_version("atdd")


def fully_qualified_call():
    return importlib.metadata.version("atdd")


def used_in_format_string():
    return f"atdd v{version('atdd')}"

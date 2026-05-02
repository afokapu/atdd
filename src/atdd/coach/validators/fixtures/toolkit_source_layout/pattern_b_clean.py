"""Fixture: COACH-PKG-LAYOUT-002 clean shapes — __version__ import + try/except wrapper + suppression."""

from importlib.metadata import PackageNotFoundError, version


def canonical_import_use():
    from atdd import __version__
    return __version__


def try_except_wrapper_pattern():
    try:
        return version("atdd")
    except PackageNotFoundError:
        return "0.0.0"


def version_for_other_package():
    return version("pytest")


def suppressed_legitimate_use():
    return version("atdd")  # atdd:suppress(COACH-PKG-LAYOUT-002)

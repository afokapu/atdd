# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-UNIT-003-no-registered-verb-reads-the-manifest
# Acceptance: acc:migrate-projection-authority:Y002-UNIT-003-no-registered-verb-reads-the-manifest
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: No registered `atdd state` verb resolves .atdd/manifest.yaml as its input — the surface the module scan cannot see, because migrate_cli opens nothing itself and delegates the read into a declared-exempt module. Refs #2023.
"""No registered verb reads the manifest (Y002-UNIT-003).

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: RED
WMBT: wmbt:migrate-projection-authority:Y002

``manifest_fallback`` scans core modules for *read sinks* — ``open``, ``safe_load``, ``glob``. It
passes :mod:`atdd.state.migrate_cli`, correctly: ``migrate_cli`` opens nothing. It calls
``migration.mint_uids(migration.manifest_path(root))``, and :mod:`atdd.state.manifest_migration` is
named in ``LEGACY_MODULES`` because "migration code reading the thing it migrates is not a fallback
— it is the exit".

That exemption was earned while there was an exit. ``.atdd/manifest.yaml`` is gone, so the two verbs
built on it cannot run: both fail with ``no legacy manifest to migrate`` against any real repo. The
guard is correct and blind at the same time — it measures read sinks, and a shipped verb can be
unrunnable without containing one.

This acceptance measures the surface the module scan cannot reach: the *registered verb set*, and
whether each verb's input can exist. Refs #2023 / #1400.
"""
from __future__ import annotations

import argparse

from atdd.state import migrate_cli

#: The verbs CORE-034 stranded: both resolve their input through ``manifest_path(root)``.
MANIFEST_VERBS = frozenset({"mint-uids", "migrate-manifest"})


def _registered_verbs() -> frozenset:
    """The verbs ``add_parsers`` actually registers on an ``atdd state`` sub-parser."""
    parser = argparse.ArgumentParser(prog="atdd state")
    sub = parser.add_subparsers(dest="op")
    migrate_cli.add_parsers(sub)
    return frozenset(sub.choices)


def test_y002_unit_003_no_registered_verb_reads_the_manifest() -> None:
    """No shipped verb takes .atdd/manifest.yaml as its input."""
    stranded = MANIFEST_VERBS & _registered_verbs()
    assert not stranded, (
        f"{sorted(stranded)} are registered but cannot run: their input .atdd/manifest.yaml was "
        "deleted by CORE-034, whose own runbook step says the readers are 'removed, not deprecated "
        "in place'"
    )


def test_y002_unit_003_the_three_verb_surfaces_agree() -> None:
    """OPS, the parser registrations, and the dispatch map name one verb set, not three."""
    registered = _registered_verbs()
    assert frozenset(migrate_cli.OPS) == registered, (
        "OPS and add_parsers disagree: "
        f"OPS-only={sorted(frozenset(migrate_cli.OPS) - registered)}, "
        f"parser-only={sorted(registered - frozenset(migrate_cli.OPS))}"
    )
    assert not MANIFEST_VERBS & frozenset(migrate_cli.OPS), (
        f"OPS still advertises {sorted(MANIFEST_VERBS & frozenset(migrate_cli.OPS))}"
    )

    # The dispatch map is the third surface. A verb it still handles is a verb still shipped,
    # whatever OPS and the parser say.
    for verb in sorted(MANIFEST_VERBS):
        args = argparse.Namespace(op=verb, root=".", mint=False, owner_actor="x", out=None)
        try:
            migrate_cli.dispatch(args)
        except KeyError:
            continue  # retired: the handler map does not know this verb
        raise AssertionError(
            f"dispatch still routes {verb!r} to a handler whose input .atdd/manifest.yaml cannot exist"
        )


def test_y002_unit_003_no_handler_calls_a_manifest_read_entry_point() -> None:
    """The module may keep the migrator's shared constant; it may not keep its read path.

    ``migrate-store`` (CORE-036, the live migration) defaults ``--owner-actor`` to
    ``migration.UNATTRIBUTED_OWNER``, and ``store_migration`` imports the same constant. So the
    import is NOT dead and deleting it outright breaks the successor. What must go is every call
    that resolves or reads the manifest: those are the readers CORE-034 said to remove.
    """
    import inspect

    source = inspect.getsource(migrate_cli)
    read_entry_points = ("migration.manifest_path(", "migration.mint_uids(", "migration.migrate(")
    still_called = [name for name in read_entry_points if name in source]
    assert not still_called, (
        f"migrate_cli still calls {still_called} — entry points whose input .atdd/manifest.yaml "
        "cannot exist. The shared constant migration.UNATTRIBUTED_OWNER is fine to keep (or to "
        "relocate); a manifest read path reached from a registered verb is not."
    )

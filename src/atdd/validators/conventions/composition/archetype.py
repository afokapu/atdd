"""Reusable graph-question archetype for the `composition` family (#1204)."""
from __future__ import annotations

import logging
from pathlib import Path

from .._support.template_contract import TemplateContract

_log = logging.getLogger(__name__)

TEMPLATES = [
    TemplateContract(
        family_id='composition',
        template_id='composed_graph_loads',
        question='Can all convention sources be loaded into one composed graph?',
        selector='all convention source files/packages',
        traversal='source files -> parse -> local graph fragments -> composed graph',
        invariant='graph construction succeeds with no parse/load errors',
        auto_capture='a new node is included if it lives in a convention source path included by the graph loader',
        failure_evidence=['source_file', 'parse_error', 'node_id_if_available', 'package_id'],
    ),
    TemplateContract(
        family_id='composition',
        template_id='composition_merge_identity',
        question='When graph fragments compose, are node identities merged, duplicated, or shadowed correctly?',
        selector='all nodes grouped by canonical id across packages/fragments',
        traversal='package graph fragments -> canonical node id -> merge policy',
        invariant='duplicate ids are either forbidden or explicitly allowed by merge/override policy',
        auto_capture='a new node is included if it declares canonical identity and package ownership',
        failure_evidence=['node_id', 'conflicting_packages', 'merge_policy', 'locations'],
    ),
    TemplateContract(
        family_id='composition',
        template_id='post_composition_edge_legality',
        question='After composition, are all edges legal under composed graph rules?',
        selector='composed_graph.edges',
        traversal='edge -> source node -> target node -> allowed edge type matrix',
        invariant='edge type is allowed between source kind/package and target kind/package',
        auto_capture='a new node is included if it participates in edges in the composed graph',
        failure_evidence=['edge_type', 'source_node', 'target_node', 'source_kind', 'target_kind', 'reason'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# ---------------------------------------------------------------------------
# Family-declared real-graph evaluators (auto-discovered by
# `_support.evaluators._real_evaluators`; we do NOT edit the shared central map).
#
# The built-in `composed_graph_loads` evaluator checks convention sources parse
# into the composed graph. The coach variant `package_data_ships_convention_nodes`
# asks the SAME composition question — "can all convention sources be loaded into
# one composed graph?" — but its load failure surfaces upstream, in the package
# data the install ships: if pyproject's `package-data` globs omit the convention
# `nodes/`, a pip-installed toolkit composes ZERO core nodes. So this family
# config-parameterizes `composed_graph_loads`: the package_data variant evaluates
# the shipping globs; every other caller delegates to the foundation parse-error
# sentinel unchanged (no behavior change for the central catch-matrix / official
# path, which call the sentinel directly).
# ---------------------------------------------------------------------------

# The convention/schema source trees the composition CLI loads. Each must be
# COVERED by pyproject's package-data, or a pip-installed toolkit composes a short
# graph — or, for the `nodes/` trees, none at all.
#
# #1474 added coder and tester. Their absence was not an oversight in the list, it
# WAS the bug: this validator has existed since #1206 and never caught #1369,
# because it only ever asked about coach and planner. The two trees that actually
# failed to ship were the two it did not name.
_REQUIRED_CONVENTION_SOURCES = (
    'coach/conventions/nodes',
    'planner/conventions/nodes',
    'coder/conventions/nodes',
    'tester/conventions/nodes',
    'planner/schemas/author',
)

# The package-data fault, named once. Narrowing the broad-ship glob to the conventions'
# own `*.yaml` stops it reaching into `nodes/` (a single `*` does not cross a directory
# separator under glob semantics), which reproduces #1369 exactly: the archetype
# conventions ship, their atomised nodes do not.
#
# It lives HERE, next to the evaluator it is the inverse of, because both the
# composition variant and the E035 staged-root guard inject it — and when it was written
# out by hand in each of them, the two copies drifted from the pyproject they anchor to.
# `mirror_file` raises when the anchor is absent, so a drifted copy does not fail
# quietly; it just fails somewhere confusing, on a test that has nothing to do with
# packaging.
PACKAGE_DATA_FAULT_ANCHOR = '"atdd" = ["**/*"]'
PACKAGE_DATA_FAULT_REPLACEMENT = '"atdd" = ["*.yaml"]'


def _pkg_dir(pkg, src_root):
    """The source dir a package-data key is resolved against.

    `''` and `'*'` mean every package; `atdd` is the root package, and this repo
    declares its data there, so both resolve to `src/atdd`.
    """
    if pkg in ('', '*', 'atdd'):
        return src_root
    return src_root / pkg.removeprefix('atdd.').replace('.', '/')


def _is_shipped(rel_path, pd, excl, src_root):
    """True iff `src_root/rel_path` is matched by package-data and not excluded.

    Mirrors setuptools' own resolution rather than string-matching the glob text.
    Asking "is this FILE shipped?" instead of "does this GLOB STRING appear?" is the
    whole point: a literal-glob check only recognises the declaration style it was
    written against, so it goes stale the moment the style changes — and it can be
    satisfied by a glob that ships nothing.

    The two halves use DIFFERENT matchers, because setuptools does:

      * include -> `glob(..., recursive=True)`  (`build_py.find_data_files`), where a
        single `*` does NOT cross a directory separator, so `["*.yaml"]` on the `atdd`
        key ships `src/atdd/*.yaml` and NOT `src/atdd/coder/conventions/nodes/*.yaml`.
      * exclude -> `fnmatch.filter`             (`build_py.exclude_data_files`), where
        `*` DOES cross separators.

    Using fnmatch for both would make `["*.yaml"]` appear to cover every nested node —
    which is exactly the false negative that would let #1369 back in.
    """
    import fnmatch
    import glob as _glob
    import os

    abs_path = os.path.realpath(src_root / rel_path)

    shipped = False
    for pkg, patterns in (pd or {}).items():
        base = _glob.escape(str(_pkg_dir(pkg, src_root)))
        for pattern in patterns or []:
            hits = _glob.glob(os.path.join(base, pattern), recursive=True)
            if any(os.path.realpath(h) == abs_path for h in hits):
                shipped = True
                break
        if shipped:
            break
    if not shipped:
        return False

    for pkg, patterns in (excl or {}).items():
        base = str(_pkg_dir(pkg, src_root))
        for pattern in patterns or []:
            if fnmatch.fnmatch(abs_path, os.path.join(base, pattern)):
                return False
    return True


def _package_data_ships_convention_nodes(graph, config=None):
    """Selector: the package-data declaration that ships convention sources.
    Traversal: pyproject.toml -> tool.setuptools.package-data -> is each real
    convention source FILE covered?
    Invariant: every convention-node/schema source the composition CLI loads is
    shipped. Evidence keys are a subset of the template `failure_evidence`."""
    import tomllib

    root = getattr(graph, 'root', None)
    if root is None:
        return []
    pyproject = root / 'pyproject.toml'
    try:
        setuptools_cfg = tomllib.loads(pyproject.read_text(encoding='utf-8'))['tool']['setuptools']
        pd = setuptools_cfg['package-data']
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        _log.debug("convention evaluator handled a recoverable error", extra={"error": str(exc)[:160]})
        return [{'source_file': 'pyproject.toml', 'package_id': None,
                 'parse_error': f'package-data unreadable: {str(exc).splitlines()[0][:120]}'}]
    excl = setuptools_cfg.get('exclude-package-data', {})

    # The DECLARATION under test comes from `graph.root` (which a fault injection
    # re-roots at a staged copy). The convention SOURCES are a fixed fact of the
    # toolkit, so they are probed in the real tree — a staged root holds only the
    # mirrored pyproject.toml, and globbing it would find no sources and pass
    # vacuously, which is how a fault-injection test quietly stops testing anything.
    src_root = root / 'src' / 'atdd'
    if not src_root.is_dir():
        src_root = Path(__file__).resolve().parents[3]  # src/atdd

    out = []
    for rel_dir in _REQUIRED_CONVENTION_SOURCES:
        source_dir = src_root / rel_dir
        if not source_dir.is_dir():
            continue  # the tree does not exist; there is nothing to ship
        # A representative real file. Coverage is a property of the declaration, so
        # one file settles it for the tree — and using a REAL file means a glob that
        # matches nothing cannot pass.
        members = sorted(p for p in source_dir.iterdir() if p.is_file())
        if not members:
            continue
        probe = members[0].relative_to(src_root)
        if not _is_shipped(probe, pd, excl, src_root):
            pkg = 'atdd.' + rel_dir.rsplit('/', 1)[0].replace('/', '.')
            out.append({'source_file': 'pyproject.toml', 'package_id': pkg,
                        'parse_error': (
                            f'package-data ships no glob covering {rel_dir}/ '
                            f'(probe: {probe.as_posix()}); a pip install composes a '
                            f'short graph or none at all'
                        )})
    return out


def _composed_graph_loads(graph, config=None):
    """Config dispatch for `composed_graph_loads` on the real composed graph.

    The `package_data_ships_convention_nodes` variant routes to the shipping-glob
    check; everything else delegates to the foundation parse-error sentinel so the
    built-in semantics are unchanged."""
    variant = (config or {}).get('variant') if isinstance(config, dict) else None
    if variant == 'package_data_ships_convention_nodes':
        return _package_data_ships_convention_nodes(graph, config)
    from .._support import sentinels as _S
    return _S.composed_graph_loads(graph).violations


REAL_EVALUATORS = {'composed_graph_loads': _composed_graph_loads}

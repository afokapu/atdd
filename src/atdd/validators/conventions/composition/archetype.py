"""Reusable graph-question archetype for the `composition` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

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

# (package_id, package-data glob) the composition CLI must have shipped to it.
_REQUIRED_PACKAGE_DATA = (
    ('atdd.coach.conventions', 'nodes/*.yaml'),
    ('atdd.planner.conventions', 'nodes/*.yaml'),
    ('atdd.planner.schemas', 'author/*.json'),
)


def _package_data_ships_convention_nodes(graph, config=None):
    """Selector: the package-data declaration that ships convention sources.
    Traversal: pyproject.toml -> tool.setuptools.package-data -> required globs.
    Invariant: every convention-node/schema glob the composition CLI loads is
    shipped. Evidence keys are a subset of the template `failure_evidence`."""
    import tomllib

    root = getattr(graph, 'root', None)
    if root is None:
        return []
    pyproject = root / 'pyproject.toml'
    try:
        pd = tomllib.loads(pyproject.read_text(encoding='utf-8'))['tool']['setuptools']['package-data']
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        return [{'source_file': 'pyproject.toml', 'package_id': None,
                 'parse_error': f'package-data unreadable: {str(exc).splitlines()[0][:120]}'}]
    out = []
    for pkg, glob in _REQUIRED_PACKAGE_DATA:
        if glob not in (pd.get(pkg) or []):
            out.append({'source_file': 'pyproject.toml', 'package_id': pkg,
                        'parse_error': f'package-data glob {glob!r} not shipped'})
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

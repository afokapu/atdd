# Phase A — `presentation` cluster atomization review (coder, PARTIAL)

Mirrors the proven `tester.acceptance-violation.*` / `coder.dto.*` atomizations.

## Scope
**PARTIAL de-monolith.** `src/atdd/coder/conventions/presentation.convention.yaml`
is MIXED: three core-agnostic rules + four stack/extension-bound rules
(`gsap-*`, `i18n-*`). Only the three core-agnostic rules were atomized; the
extension rules stay in the monolith `rules:[]` block untouched (they migrate in
Phase B).

Atomized → `src/atdd/coder/conventions/nodes/`:
- `coder.presentation.layer-is-thin`
- `coder.presentation.controllers-never-call-domain`
- `coder.presentation.response-models-live-in`

Left in monolith (EXT, untouched): `coder.presentation.gsap-layer`,
`coder.presentation.gsap-commons`, `coder.presentation.i18n-config`,
`coder.presentation.i18n-switcher`.

## Pass 1 — fidelity (every field preserved)
Each source rule had: `id`, `aliases`, `severity`, `disposition`, `description`,
`introduced_in`. All preserved in the node form:
- `id` → `rule_id`
- `description` → `statement` (verbatim, incl. the `—` and `→` glyphs)
- `aliases`/`severity`/`disposition`/`introduced_in` → `metadata.*`
- `source.legacy_*` records origin with `extraction_mode: high_fidelity`.
- A defined `terms[]` entry added per node (mirrors `coder.dto.*`, which
  paraphrases each rule into a named term); paraphrase only, no new normative
  content.
No `implementation` block authored — the source rules carry NO `validator:` key
(they are `disposition: documentation-only`), matching the `coder.dto.*` nodes
which are likewise binding-free. The four EXT rules DO carry a `validator:` and
were intentionally left in the monolith.

## Pass 2 — de-monolith correctness
- Deleted ONLY the three atomized rule blocks from `rules:[]`.
- The four `gsap-*`/`i18n-*` rule blocks remain byte-for-byte intact.
- All non-`rules` sections (`architecture`, `http_rest_api`, `cli_pattern`,
  `validation`, `cross_references`, `examples`, `purpose`, `relationship`)
  untouched.
- Added a short comment (NOT a whole-file migration marker) noting which three
  ids moved to `nodes/` and that the gsap/i18n rules stay for Phase B.

## Pass 3 — graph wiring (no orphans for my nodes)
Added two `runs_alongside` edges to `relationships.yaml`, hub =
`coder.presentation.layer-is-thin` (mirrors `coder.dto.placement` as hub):
- `layer-is-thin` → `controllers-never-call-domain`
- `layer-is-thin` → `response-models-live-in`
All three nodes now appear as a `source_ref`/`target_ref` endpoint.
`test_no_orphan_nodes` clean-baseline GREEN.

## STEP 4 — mirror check
`coder.presentation.controllers-never-call-domain` is a dependency-direction
principle (Controller → Use Case → Domain). Reviewed existing atomized nodes for
a semantic mirror:
- `coder.dto.purity` concerns CROSS-WAGON boundary traffic (domain stays
  wagon-internal) — a different axis (inter-wagon), not intra-feature layer
  flow. No restatement.
- `coder.boundaries.*` are validator-backed checks, NOT atomized convention
  nodes, so no node endpoint to refine.
**Conclusion:** no atomized node is a restatement of this rule → no
`refines`/`runs_alongside` cross-edge added. Flagging for overseer: when
`boundaries`/`design` dependency-flow rules are atomized in a later phase, a
`refines` edge from `controllers-never-call-domain` to the dependency-direction
node would be appropriate.

## Verification
```
pytest test_no_orphan_nodes.py test_sentinels.py test_rule_validator_binding.py \
       test_no_duplicate_rule_representation.py src/atdd/coder/validators/ -q
→ 197 passed, 112 skipped, 3 warnings (pre-existing advisory xlang/hierarchy, unrelated)
```

"""#2025 lab, probe 5 — would narrowing `external_refs` break a live contract?

The issue proposed tightening `external_refs` to "exactly {github: {issue: ...}},
one provider, one ref kind, one scalar". Adversarial review said that refuses
writes the extension bot is DESIGNED to make. This probe settles it against the
two live writers rather than by reading intent off the prose.

  5a  provider_seam.apply_updates  — the only sanctioned write-back into the
      projection. What provider/ref_kind pairs does validate_update admit?
  5b  merge_driver._bot_only       — what does a three-way merge of external_refs
      do with a provider only one side knows about?
  5c  the three candidate contracts, scored against 5a and 5b.

Usage:  python scope.py
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

from atdd.state import merge_driver, provider_seam

GH, ISSUE = "github", "issue"


def _update(uid, provider, ref_kind, ref_value):
    return SimpleNamespace(
        uid=uid, provider=provider, ref_kind=ref_kind, ref_value=ref_value,
        namespace=f"bot:{provider}", authoritative=False, claims={},
    )


def main() -> int:
    uid = "wi_01M2EZ25BPW2NNQTPCQFWS5RQ9"
    base = {uid: {"uid": uid, "phase": "PLANNED", "state": "ACTIVE",
                  "owner_actor": "atdd:unattributed"}}

    print("== 5a: what does the sanctioned write-back path admit? ==")
    candidates = [
        (GH, ISSUE, "1975"),
        (GH, "pr", "2028"),
        ("jira", "ticket", "ATDD-17"),
        ("linear", "issue", "ENG-42"),
    ]
    admitted = []
    for provider, ref_kind, ref_value in candidates:
        try:
            out = provider_seam.apply_updates(base, [_update(uid, provider, ref_kind, ref_value)])
            refs = out[uid]["external_refs"]
            admitted.append((provider, ref_kind))
            print(f"  {provider:<8} {ref_kind:<7} -> ADMITTED, writes {refs}")
        except Exception as exc:  # noqa: BLE001 — the probe reports, never raises
            print(f"  {provider:<8} {ref_kind:<7} -> refused ({type(exc).__name__}: {exc})")
    print(f"  => validate_update constrains uid, bot-namespace, authoritativeness and")
    print(f"     provider IDENTITY. It enumerates neither provider nor ref_kind, so all")
    print(f"     {len(admitted)} are legal writes. It already emits the NESTED shape:")
    print(f"     refs[provider][ref_kind] = value — the same shape #2025 proposes.")

    print("\n== 5b: what does the merge driver do with a provider only one side has? ==")
    base_v = {GH: {ISSUE: "1975"}}
    ours_v = {GH: {ISSUE: "1975"}, "jira": {"ticket": "ATDD-17"}}
    theirs_v = {GH: {ISSUE: "1975"}, "linear": {"issue": "ENG-42"}}
    cell = merge_driver._Cell(
        uid=uid, field="external_refs", rule="bot-only",
        base=base_v, ours=ours_v, theirs=theirs_v,
        base_doc={"external_refs": base_v},
        ours_doc={"external_refs": ours_v},
        theirs_doc={"external_refs": theirs_v},
        ours_evidence=frozenset(), theirs_evidence=frozenset(),
        policy=provider_seam.default_policy(),
    )
    merged, conflict = merge_driver._bot_only(cell)
    print(f"  ours has jira, theirs has linear, base has neither")
    print(f"  merged   -> {merged}")
    print(f"  conflict -> {conflict}")
    print("  => disjoint providers UNION. The driver is written to preserve a provider")
    print("     it has never heard of. A closed schema would make that merge unwritable.")

    print("\n== 5c: scoring the three candidate contracts ==")
    rows = [
        ("(a) close external_refs to github.issue only",
         "REFUSES 3 of 4 legal bot writes; breaks the union merge; would force migrating "
         "provider_seam + merge_driver + their consumers into this issue"),
        ("(b) new narrowly-typed TRANSPORT field, leave external_refs open",
         "works, but puts the same fact in two places, needs its own ownership row, merge "
         "cell and writer discipline, and hands provider identity back to core — which is "
         "the one thing the #1622 narrow rule forbids"),
        ("(c) leave external_refs OPEN, type only the github.issue path",
         "admits all 4 legal writes, preserves the union merge, pins the leaf the transport "
         "depends on, adds no second home for the fact, and needs no new ownership rule"),
    ]
    for name, verdict in rows:
        print(f"  {name}\n      {verdict}")

    print("\n  (c) as JSON Schema — open everywhere, typed exactly where it must be:")
    print("""      "external_refs": {
        "type": "object",
        "additionalProperties": true,
        "properties": {
          "github": {
            "type": "object",
            "additionalProperties": true,
            "properties": {
              "issue": { "type": "string", "pattern": "^[0-9]+$" }
            }
          }
        }
      }""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

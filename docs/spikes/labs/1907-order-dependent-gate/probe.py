"""SPIKE (#1907): how much of its input does the sub-issue label validator read?

The `return` is visible in the source. What is NOT visible by reading is the
consequence: whether it depends on dict ORDER — i.e. whether the same repository
passes or fails depending on which parent happens to come first.

That decides the severity. A validator that always misses everything after the
first parent is broken. A validator whose verdict depends on iteration order is
broken AND non-deterministic, which is worse: it would go green and red across
runs with no code change, and every green would be believed.
"""
import sys

def shipped(github_sub_issues):
    """The validator as it ships, reduced to its control flow."""
    for num, subs in github_sub_issues.items():
        if not subs:
            continue
        unlabeled = [f"#{s['number']}" for s in subs
                     if "atdd-wmbt" not in [l["name"] for l in s.get("labels", [])]]
        if unlabeled:
            return ("FAIL", num, unlabeled)
        return ("PASS-after-first", num, [])      # <-- the return inside the loop
    return ("PASS-no-parents", None, [])

def sub(n, labelled):
    return {"number": n, "labels": [{"name": "atdd-wmbt"}] if labelled else []}

CLEAN = [sub(10, True), sub(11, True)]
DIRTY = [sub(20, False), sub(21, False)]

cases = {
    "dirty parent FIRST":            {1: DIRTY, 2: CLEAN},
    "dirty parent SECOND":           {1: CLEAN, 2: DIRTY},
    "clean, clean, dirty":           {1: CLEAN, 2: CLEAN, 3: DIRTY},
    "first parent has NO subs":      {1: [], 2: DIRTY},
    "every parent dirty":            {1: DIRTY, 2: DIRTY},
}
print(f"{'CASE':32} {'VERDICT':18} examined  missed")
print("-" * 72)
for name, data in cases.items():
    verdict, examined, _ = shipped(data)
    total = sum(1 for v in data.values() if v)
    seen = 1 if examined is not None else 0
    dirty_total = sum(1 for v in data.values()
                      if any("atdd-wmbt" not in [l["name"] for l in s["labels"]] for s in v))
    missed = dirty_total - (1 if verdict == "FAIL" else 0)
    print(f"{name:32} {verdict:18} {seen}/{total:<7} {missed} dirty parent(s) unreported")

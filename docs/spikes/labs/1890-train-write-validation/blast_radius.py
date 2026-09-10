"""SPIKE (#4): what would each candidate write-time rule reject, on real data?

Not a reproduction — the defect is already measured (`atdd update 1888 --train
INVALID` was accepted). This answers the question that decides the FIX: how much
live data does each candidate rule invalidate?
"""
import pathlib, re, subprocess, sys, collections, yaml

REPO = pathlib.Path("/Users/alecfokapu/Github/atdd/main")

d = yaml.safe_load((REPO / "plan/_trains.yaml").read_text())
registry = {t["train_id"] for th in d["trains"].values() for r in th.values() for t in r}
loose = {p.stem for p in (REPO / "plan/_trains").glob("*.yaml") if not p.stem.startswith("_")}
known_norm = {k.removeprefix("train:") for k in (registry | loose)}

CANONICAL = re.compile(r"^train:[a-z0-9-]+:[a-z0-9-]+$")
LEGACY    = re.compile(r"^(?:train:)?[0-9]{4}-[a-z0-9-]+$")

def classify(v):
    norm = v.removeprefix("train:")
    return {
        "registered": norm in known_norm,
        "canonical":  bool(CANONICAL.match(v)),
        "legacy":     bool(LEGACY.match(v)),
    }

# every --train value the repo's OWN source passes
seen = collections.Counter()
for path in REPO.rglob("*.py"):
    if ".git" in path.parts: continue
    try: txt = path.read_text(encoding="utf-8", errors="ignore")
    except OSError: continue
    for m in re.finditer(r'"--train",\s*\n?\s*"([^"]+)"', txt):
        seen[m.group(1)] += 1

print(f"registry knows {len(known_norm)} train identities\n")
print(f"{'--train VALUE USED IN REPO SOURCE':40} {'n':>3}  registered canonical legacy")
print("-" * 82)
for v, n in seen.most_common():
    c = classify(v)
    print(f"{v:40} {n:>3}  {str(c['registered']):>10} {str(c['canonical']):>9} {str(c['legacy']):>6}")

rules = {
    "A: reject unregistered":            lambda v: not classify(v)["registered"],
    "B: reject legacy FORMAT":           lambda v: classify(v)["legacy"],
    "C: reject unregistered OR legacy":  lambda v: not classify(v)["registered"] or classify(v)["legacy"],
}
print(f"\n{'CANDIDATE RULE':36} rejects (distinct values / call sites)")
print("-" * 78)
for name, rule in rules.items():
    bad = {v: n for v, n in seen.items() if rule(v)}
    print(f"{name:36} {len(bad):>2} / {sum(bad.values()):>2}   {sorted(bad) if bad else ''}")

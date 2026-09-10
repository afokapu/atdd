"""SPIKE (#3): how many tests are permanently red on a CLEAN main, and how many
are red because the acceptance they are bound to was superseded?

Not a reproduction — the E023/E026 contradiction is already read out of the two
plan files. This asks whether that is a one-off or a CLASS, which decides whether
the fix is "retire one acceptance" or "add a validator".

Input: failure lists captured from a clean origin/main checkout.
"""
import pathlib, re, subprocess, sys, yaml, collections

REPO = pathlib.Path(sys.argv[1])
lists = [pathlib.Path(p) for p in sys.argv[2:]]

failures = []
for lst in lists:
    if lst.exists():
        failures += [ln.split("::")[0].strip() for ln in lst.read_text().splitlines() if ln.strip()]
failures = sorted(set(failures))

print(f"permanently-red test FILES on clean main: {len(failures)}\n")

# every acceptance URN declared anywhere in plan/
declared = {}
for wmbt in REPO.glob("plan/*/[A-Z]*.yaml"):
    try:
        doc = yaml.safe_load(wmbt.read_text(encoding="utf-8")) or {}
    except Exception:
        continue
    for acc in doc.get("acceptances") or []:
        urn = (acc.get("identity") or {}).get("urn")
        if urn:
            declared[urn] = wmbt.name

rows = []
for f in failures:
    path = REPO / f
    if not path.exists():
        # the failure list may carry only a basename; resolve it under the repo
        hits = list(REPO.rglob(pathlib.Path(f).name))
        if not hits:
            rows.append((f, "?", "test file not found")); continue
        path = hits[0]
    head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:12])
    m = re.search(r"#\s*Acceptance:\s*(\S+)", head)
    if not m:
        rows.append((f, "-", "no Acceptance header — bound to no plan artifact")); continue
    urn = m.group(1)
    rows.append((f, urn, "DECLARED in " + declared[urn] if urn in declared else "URN NOT DECLARED in plan/"))

print(f"{'TEST FILE':62} STATE")
print("-" * 100)
for f, urn, state in rows:
    print(f"{pathlib.Path(f).name[:60]:62} {state}")

kinds = collections.Counter(s.split(" in ")[0] for _, _, s in rows)
print("\nsummary:")
for k, v in kinds.most_common():
    print(f"  {v:>2}  {k}")

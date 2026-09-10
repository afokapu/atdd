"""SPIKE (#1893): why is each permanently-red test red?

The E023/E026 pair looked like one defect. Reading the two artifacts showed three
different causes wearing the same symptom, so this classifies all 17 rather than
generalising from the one I happened to open first.
"""
import pathlib, re, sys, collections

REPO = pathlib.Path(sys.argv[1])
names = set()
for lst in sys.argv[2:]:
    p = pathlib.Path(lst)
    if p.exists():
        names |= {pathlib.Path(ln.split("::")[0].strip()).name for ln in p.read_text().splitlines() if ln.strip()}

rows = []
for name in sorted(names):
    hits = list(REPO.rglob(name))
    if not hits:
        rows.append((name, "?", "unresolved")); continue
    text = hits[0].read_text(encoding="utf-8", errors="ignore")
    head = "\n".join(text.splitlines()[:14])
    phase = (re.search(r"#\s*Phase:\s*(\w+)", head) or [None, "-"])[1]
    body = text.lower()
    if "red state" in body or "will pass only after" in body or "drives the implementation" in body:
        why = "ABANDONED RED STUB"
    elif re.search(r"live[_ ]store|real_cli|real cli|subprocess", body) and phase.upper() == "SMOKE":
        why = "environment-coupled SMOKE"
    else:
        why = "other"
    rows.append((name, phase, why))

print(f"{'TEST':60} {'PHASE':7} WHY RED")
print("-" * 96)
for n, p, w in rows:
    print(f"{n[:58]:60} {p:7} {w}")
print("\nsummary:")
for k, v in collections.Counter(w for _, _, w in rows).most_common():
    print(f"  {v:>2}  {k}")
print("\nby declared phase:")
for k, v in collections.Counter(p for _, p, _ in rows).most_common():
    print(f"  {v:>2}  Phase: {k}")

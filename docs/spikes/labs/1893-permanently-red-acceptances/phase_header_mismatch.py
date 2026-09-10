"""SPIKE (#1893): how many test files declare a phase their acceptance does not?

An abandoned RED stub is a test still asserting the placeholder its issue used to
drive implementation, left behind after the issue completed. The mechanical
signature is a `# Phase:` header that disagrees with the phase of the acceptance
the same header names. This counts them, because two edits and a ratchet are
different fixes.
"""
import pathlib, re, sys, collections, yaml

REPO = pathlib.Path(sys.argv[1])

acc_phase = {}
for wmbt in REPO.glob("plan/*/[A-Z]*.yaml"):
    try:
        doc = yaml.safe_load(wmbt.read_text(encoding="utf-8")) or {}
    except Exception:
        continue
    for acc in doc.get("acceptances") or []:
        ident = acc.get("identity") or {}
        if ident.get("urn"):
            acc_phase[ident["urn"]] = (ident.get("phase") or "?").upper()

mismatch, matched, unbound = [], 0, 0
for test in REPO.rglob("test_*.py"):
    # build/ is a packaging artifact tree, not source; counting it would double
    # every finding and inflate the number this measurement exists to produce.
    if {".git", "build", ".tox", ".venv", "dist"} & set(test.parts):
        continue
    head = "\n".join(test.read_text(encoding="utf-8", errors="ignore").splitlines()[:14])
    m_acc = re.search(r"#\s*Acceptance:\s*(\S+)", head)
    m_ph = re.search(r"#\s*Phase:\s*(\w+)", head)
    if not (m_acc and m_ph):
        unbound += 1
        continue
    declared = acc_phase.get(m_acc.group(1))
    if declared is None:
        continue
    if declared == m_ph.group(1).upper():
        matched += 1
    else:
        mismatch.append((test.relative_to(REPO), m_ph.group(1).upper(), declared))

print(f"tests with both headers, acceptance declared : {matched + len(mismatch)}")
print(f"  header phase MATCHES acceptance            : {matched}")
print(f"  header phase DISAGREES                     : {len(mismatch)}")
print(f"tests missing a header (not counted)         : {unbound}\n")
for path, header, declared in sorted(mismatch)[:25]:
    print(f"  header={header:6} acceptance={declared:6}  {path}")
if len(mismatch) > 25:
    print(f"  ... and {len(mismatch)-25} more")
print("\nby direction:")
for k, v in collections.Counter(f"{h} -> {d}" for _, h, d in mismatch).most_common():
    print(f"  {v:>3}  test says {k}")

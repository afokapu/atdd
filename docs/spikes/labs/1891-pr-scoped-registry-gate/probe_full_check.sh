#!/usr/bin/env bash
# SPIKE (#1 / per-PR registry gate): can a gate DETECT drift, and what does it
# cost? Measured against a real checkout, drift injected for real.
set -u
BASE="$1"                       # a clean checkout of origin/main
cd "$BASE" || exit 1

echo "--- 1. clean checkout ---"
t0=$(date +%s%N); out=$(atdd registry update --check 2>&1); rc=$?; t1=$(date +%s%N)
echo "    rc=$rc   $(( (t1-t0)/1000000 ))ms   $(printf '%s' "$out" | grep -c 'in sync') mirrors in sync"

echo "--- 2. drift injected into a WAGON MANIFEST (source of truth) ---"
MAN=plan/admit_substrate/_admit_substrate.yaml
cp "$MAN" /tmp/man.bak
python3 - "$MAN" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text()
t = t.replace('  C001: "', '  C099: "LAB injected wmbt to create mirror drift"\n  C001: "', 1)
p.write_text(t)
PY
out=$(atdd registry update --check 2>&1); rc=$?
echo "    rc=$rc   detected: $(printf '%s' "$out" | grep -ci 'drift')"
printf '%s' "$out" | grep -iE "Drifted files|out of sync" | head -3 | sed 's/^/      /'

echo "--- 3. does --check WRITE anything? (it must not) ---"
if git diff --quiet -- plan/_wagons.yaml; then echo "    plan/_wagons.yaml unchanged by --check: yes"
else echo "    plan/_wagons.yaml MUTATED by --check: NO — a read-only gate that writes is not read-only"; fi

cp /tmp/man.bak "$MAN"
out=$(atdd registry update --check 2>&1); rc=$?
echo "--- 4. restored ---"; echo "    rc=$rc"
git checkout -- . 2>/dev/null

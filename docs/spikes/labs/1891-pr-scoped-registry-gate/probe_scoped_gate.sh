#!/usr/bin/env bash
# Does the SHIPPED but unwired PR-scoped gate work when invoked?
set -u
BASE="$1"; cd "$BASE" || exit 1
git checkout -q --detach origin/main 2>/dev/null; git checkout -q -- . 2>/dev/null

echo "--- CLI accepts --scope changed-files? ---"
out=$(atdd registry update --check --scope changed-files 2>&1); rc=$?
echo "    rc=$rc"; printf '%s' "$out" | grep -viE "^\s*$|upgraded" | head -3 | sed 's/^/      /'

echo "--- with drift in a wagon manifest, on a branch off main ---"
git checkout -q -b lab-drift 2>/dev/null || git checkout -q lab-drift
python3 - <<'PY'
import pathlib
p = pathlib.Path("plan/admit_substrate/_admit_substrate.yaml"); t = p.read_text()
p.write_text(t.replace('  C001: "', '  C099: "LAB injected"\n  C001: "', 1))
PY
git add -A >/dev/null 2>&1; git -c user.email=l@b -c user.name=lab commit -qm "lab: drift a wagon manifest" >/dev/null 2>&1
out=$(atdd registry update --check --scope changed-files 2>&1); rc=$?
echo "    rc=$rc  (1 = drift caught, 0 = MISSED)"
printf '%s' "$out" | grep -viE "^\s*$|upgraded" | head -4 | sed 's/^/      /'

git checkout -q --detach origin/main 2>/dev/null; git branch -qD lab-drift 2>/dev/null; git checkout -q -- . 2>/dev/null

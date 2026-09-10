"""SPIKE (#1896): how many validators go silently green when GitHub is unreachable?

`conftest.py` fixtures call pytest.skip when the API cannot be queried. A skipped
test is GREEN, so every validator depending on one reports nothing rather than
reporting that it could not check. #1892 surfaced this: validate-coach passed on
one PR and failed on the next with 14 pre-existing unlabeled issues — same code,
different API availability.

Counts the validators reachable from each fail-open fixture.
"""
import pathlib, re, sys, collections

REPO = pathlib.Path(sys.argv[1])
CONFTEST = REPO / "src/atdd/coach/validators/conftest.py"
text = CONFTEST.read_text(encoding="utf-8")

# fixtures whose body contains a skip on an API failure
failopen = []
for m in re.finditer(r"def (\w+)\(([^)]*)\):(.*?)(?=\n@pytest\.fixture|\ndef |\Z)", text, re.S):
    name, _args, body = m.groups()
    if re.search(r'pytest\.skip\(f?"Cannot (query|batch-query|verify)', body):
        failopen.append(name)

print(f"fail-open fixtures in conftest.py: {len(failopen)}")
for f in failopen:
    print(f"   {f}")

vdir = REPO / "src/atdd/coach/validators"
users = collections.Counter()
files = collections.defaultdict(set)
for test in vdir.rglob("test_*.py"):
    src = test.read_text(encoding="utf-8", errors="ignore")
    for fx in failopen:
        if re.search(rf"\b{re.escape(fx)}\b", src):
            users[fx] += len(re.findall(rf"def (test_\w+)\([^)]*\b{re.escape(fx)}\b", src))
            files[fx].add(test.name)

print(f"\n{'FIXTURE':34} {'test fns':>8}  files")
print("-" * 78)
total_files = set()
for fx in failopen:
    total_files |= files[fx]
    print(f"{fx:34} {users[fx]:>8}  {len(files[fx])}")
print(f"\ndistinct validator FILES that go green on an API failure: {len(total_files)}")
for f in sorted(total_files):
    print(f"   {f}")

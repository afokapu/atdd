#!/usr/bin/env python3
"""Apply Pass 1 fixes: add transitive deps + reword #897 Closes."""
import re, subprocess, json

# Children whose deps need #888 and #889 added explicitly
ADD_DEPS = {
    894: {"add_before": "#890",
          "addition": "#888 (Coach-core types), #889 (required-CI gates: parity + import discipline), "},
    895: {"add_before": "#893",
          "addition": "#888 (Coach-core types), #889 (required-CI gates: parity + import discipline), "},
    896: {"add_before": "#895",
          "addition": "#888 (Coach-core types), #889 (required-CI gates: parity + import discipline), "},
    897: {"add_before": "#893",
          "addition": "#888 (Coach-core types), #889 (required-CI gates: parity + import discipline), "},
}

# #897 Closes rewording
CLOSES_897_OLD = "## Closes\n\nthe migration. Mark umbrella #887 COMPLETE."
CLOSES_897_NEW = """## Closes

This is the **final child** of the umbrella. When this PR merges, all done-criteria in umbrella (see the umbrella's body, §Done criteria) should hold. The operator MUST then manually close the umbrella (no GitHub auto-close from this child — by intent, since a child should not close its own parent)."""

def fetch_body(num):
    r = subprocess.run(
        ["gh", "issue", "view", str(num), "--json", "body"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)["body"]

def write_body(num, body):
    subprocess.run(
        ["gh", "issue", "edit", str(num), "--body", body],
        check=True, capture_output=True, text=True,
    )
    print(f"  ✓ updated #{num}")

# 1. Add transitive deps to #894-#897
for num, cfg in ADD_DEPS.items():
    body = fetch_body(num)
    pattern = r"(\*\*Depends on:\*\* )(" + re.escape(cfg["add_before"]) + r")"
    new_body, n = re.subn(pattern, r"\1" + cfg["addition"] + r"\2", body, count=1)
    if n == 1:
        write_body(num, new_body)
    else:
        print(f"  ⚠ #{num}: pattern not found, skipped")

# 2. Reword #897 Closes
body = fetch_body(897)
if CLOSES_897_OLD in body:
    new_body = body.replace(CLOSES_897_OLD, CLOSES_897_NEW)
    write_body(897, new_body)
elif "the migration. Mark umbrella #887 COMPLETE" in body:
    # find and replace just that line
    new_body = body.replace("the migration. Mark umbrella #887 COMPLETE.", CLOSES_897_NEW.split("\n\n", 1)[1])
    write_body(897, new_body)
else:
    print("  ⚠ #897: Closes line not found in expected form")

print("\ndone")

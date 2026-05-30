#!/usr/bin/env python3
"""Pass 1 verification of #887 + #888-#897 structural correctness."""
import json
import re
import subprocess

ISSUES = list(range(887, 898))

# Source of truth — what the doc says
EXPECTED = {
    887: {"wave": "—", "deps": [], "blocks": [], "closes": [],
          "is_umbrella": True},
    888: {"wave": "A", "deps": [], "blocks": [889, 890, 891, 892, 893, 894, 895, 896, 897],
          "closes": []},
    889: {"wave": "B", "deps": [888], "blocks": [891, 892, 893, 894, 895, 896, 897],
          "closes": []},
    890: {"wave": "B", "deps": [888], "blocks": [894, 895],
          "closes": []},
    891: {"wave": "C", "deps": [888, 889], "blocks": [894],
          "closes": [882]},
    892: {"wave": "C", "deps": [888, 889], "blocks": [894],
          "closes": []},
    893: {"wave": "C", "deps": [888, 889], "blocks": [895, 897],
          "closes": [871, 872, 840]},
    894: {"wave": "D", "deps": [888, 889, 890, 891, 892], "blocks": [895],
          "closes": []},
    895: {"wave": "E", "deps": [888, 889, 890, 893, 894], "blocks": [896, 897],
          "closes": []},
    896: {"wave": "F", "deps": [888, 889, 895], "blocks": [],
          "closes": []},
    897: {"wave": "F", "deps": [888, 889, 893, 895], "blocks": [],
          "closes": []},
}

def fetch_issue(num):
    r = subprocess.run(
        ["gh", "issue", "view", str(num), "--json", "number,title,body,labels,state"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)

def parse_field(body, field):
    """Extract a single-line | Field | Value | row."""
    for line in body.splitlines():
        if line.strip().startswith(f"| {field} |") or line.strip().startswith(f"|{field}|"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                return parts[-2]
    return None

def has_section(body, name):
    return any(line.strip().startswith(name) for line in body.splitlines())

def extract_deps_from_body(body):
    """Find '#NNN' references in the Dependencies section."""
    deps = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("**Depends on:**"):
            # Extract from THIS line (the deps live on it, e.g. "**Depends on:** #888, #889")
            # Strip parenthetical descriptions that may contain other #refs
            value = stripped[len("**Depends on:**"):]
            # Remove parenthetical text to avoid grabbing #refs inside (descriptions)
            value_clean = re.sub(r"\([^)]*\)", "", value)
            deps.update(int(m) for m in re.findall(r"#(\d+)", value_clean))
            break
    return sorted(deps)

def extract_blocks_from_body(body):
    for line in body.splitlines():
        if line.strip().startswith("**Blocks:**"):
            return sorted(int(m) for m in re.findall(r"#(\d+)", line))
    return []

def extract_closes_from_body(body):
    """Find 'Closes' line references. Supports both '## Closes' header and inline '**Closes:**' line."""
    closes = set()

    # Pattern 1: ## Closes header section
    in_closes = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Closes"):
            in_closes = True
            continue
        if in_closes:
            if stripped.startswith("## ") or stripped.startswith("---"):
                in_closes = False
            else:
                for m in re.findall(r"(?<!\d\.)\#(\d+)", line):
                    closes.add(int(m))

    # Pattern 2: inline **Closes:** line (single line OR multi-line until next blank or **)
    in_inline_closes = False
    for line in body.splitlines():
        if re.search(r"\*\*Closes:?\*\*", line):
            in_inline_closes = True
            # also extract from same line
            value = re.sub(r"^.*\*\*Closes:?\*\*", "", line)
            for m in re.findall(r"(?<!\d\.)\#(\d+)", value):
                closes.add(int(m))
            continue
        if in_inline_closes:
            if line.strip() == "" or line.strip().startswith("**") or line.strip().startswith("##") or line.strip().startswith("---"):
                in_inline_closes = False
            else:
                for m in re.findall(r"(?<!\d\.)\#(\d+)", line):
                    closes.add(int(m))

    return sorted(closes)

def main():
    print("=" * 80)
    print("PASS 1 — STRUCTURAL VERIFICATION OF #887 + #888-#897")
    print("=" * 80)

    issues = {n: fetch_issue(n) for n in ISSUES}
    all_findings = []

    for num in ISSUES:
        issue = issues[num]
        body = issue["body"] or ""
        expected = EXPECTED[num]
        findings = []

        # 1. Branch field has no backticks
        branch = parse_field(body, "Branch")
        if branch is None:
            findings.append(f"  ❌ Branch field missing")
        elif "`" in branch:
            findings.append(f"  ❌ Branch has backticks: {branch!r}")
        elif num != 887 and not branch.startswith("feat/"):
            findings.append(f"  ⚠  Branch doesn't start with feat/: {branch!r}")

        # 2. Train field set
        train = parse_field(body, "Train")
        if train is None:
            findings.append(f"  ❌ Train field missing")
        elif train.upper() == "TBD":
            findings.append(f"  ⚠  Train still TBD")

        # 3. Type field
        itype = parse_field(body, "Type")
        if itype is None:
            findings.append(f"  ❌ Type field missing")

        # 4. Graph Context section present
        if not has_section(body, "### Graph Context"):
            findings.append(f"  ❌ ### Graph Context section missing")

        # 5. For children: Parent reference to #887
        if num != 887:
            if "#887" not in body:
                findings.append(f"  ❌ No reference to umbrella #887")
            if "docs/coach-decomposition.md" not in body:
                findings.append(f"  ❌ No reference to source-of-truth doc")

        # 6. Dependencies match
        if num != 887:
            actual_deps = extract_deps_from_body(body)
            expected_deps = expected["deps"]
            if set(actual_deps) != set(expected_deps):
                findings.append(f"  ❌ Deps mismatch: actual={actual_deps}, expected={expected_deps}")

        # 7. Closes matches
        actual_closes = extract_closes_from_body(body)
        expected_closes = expected["closes"]
        if set(actual_closes) != set(expected_closes):
            findings.append(f"  ⚠  Closes mismatch: actual={actual_closes}, expected={expected_closes}")

        # 8. Labels include atdd-issue + atdd:INIT
        label_names = {l["name"] for l in issue["labels"]}
        if "atdd-issue" not in label_names:
            findings.append(f"  ❌ Missing label: atdd-issue")
        if "atdd:INIT" not in label_names:
            findings.append(f"  ⚠  Label not atdd:INIT: {label_names}")

        # Report
        title = issue["title"][:60]
        marker = "✓" if not findings else "✗"
        print(f"\n{marker} #{num} [{expected['wave']}] {title}")
        for f in findings:
            print(f)
            all_findings.append((num, f.strip()))

    # Cross-graph check: each child's "blocks" claim should be the set of children that list it as dep
    print("\n" + "=" * 80)
    print("DEPENDENCY GRAPH COHERENCE")
    print("=" * 80)
    actual_inbound = {n: set() for n in ISSUES}
    for n in ISSUES:
        if n == 887:
            continue
        body = issues[n]["body"] or ""
        for dep in extract_deps_from_body(body):
            if dep in actual_inbound:
                actual_inbound[dep].add(n)

    graph_issues = []
    for n in ISSUES:
        expected_blocks = set(EXPECTED[n]["blocks"])
        actual = actual_inbound[n]
        if expected_blocks != actual:
            graph_issues.append(
                f"  ⚠  #{n} expected to block {sorted(expected_blocks)}, actually blocks {sorted(actual)}"
            )

    if not graph_issues:
        print("  ✓ Forward (deps) and inverse (blocks) graphs are consistent")
    else:
        for g in graph_issues:
            print(g)
            all_findings.append((0, g.strip()))

    # Closes-target existence check
    print("\n" + "=" * 80)
    print("CLOSES TARGET CHECK (do the referenced issues exist?)")
    print("=" * 80)
    seen_closes = set()
    for n in ISSUES:
        for c in EXPECTED[n]["closes"]:
            seen_closes.add(c)
    for c in seen_closes:
        try:
            r = subprocess.run(["gh", "issue", "view", str(c), "--json", "state,title"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                d = json.loads(r.stdout)
                print(f"  ✓ #{c} exists: [{d['state']}] {d['title'][:55]}")
            else:
                print(f"  ❌ #{c} NOT FOUND")
                all_findings.append((0, f"closes target #{c} does not exist"))
        except Exception as e:
            print(f"  ❌ #{c} lookup failed: {e}")

    print("\n" + "=" * 80)
    print(f"SUMMARY: {len(all_findings)} finding(s)")
    print("=" * 80)
    for num, f in all_findings:
        prefix = f"#{num}" if num else "graph"
        print(f"  [{prefix}] {f}")

if __name__ == "__main__":
    main()

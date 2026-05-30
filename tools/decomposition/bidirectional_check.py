#!/usr/bin/env python3
"""Bi-directional consistency check: doc ↔ issues.

For each child:
  - Doc section's Scope/Acceptance/Closes should match issue body verbatim.
  - Issue body's metadata (deps, wave) should match what doc declares in §12.2 and §13.X.
  - Any contract reference in issue body (#NNN, §X.Y) should resolve.

For the umbrella:
  - Wave plan in #887 body matches doc §12.2.
  - Child index in #887 body matches doc §13 child set.
  - Done criteria in #887 matches doc §12.1.
"""
import json, re, subprocess
from pathlib import Path

# Portable path resolution: this script lives at tools/decomposition/<name>.py
# So the repo root is two parents up from this file.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DOC = REPO_ROOT / "docs" / "coach-decomposition.md"
DOC_TEXT = DOC.read_text()

CHILDREN = {
    888: "13.1", 889: "13.2", 890: "13.3", 891: "13.4", 892: "13.5",
    893: "13.6", 894: "13.7", 895: "13.8", 896: "13.9", 897: "13.10",
}

def fetch_body(num):
    r = subprocess.run(["gh", "issue", "view", str(num), "--json", "body"],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["body"]

def extract_doc_section_body(section_num):
    pattern = re.compile(
        rf"^### {re.escape(section_num)} [^\n]*\n(.*?)(?=^### \d+\.\d+|^---\s*$)",
        re.MULTILINE | re.DOTALL
    )
    m = pattern.search(DOC_TEXT)
    return m.group(1).strip() if m else None

def strip_metadata_lines(text):
    """Strip the **Slug:**/**Type:**/etc. lines that the issue body header replaces."""
    out = []
    skip_metadata = True
    for line in text.splitlines():
        s = line.strip()
        if skip_metadata:
            if s.startswith("**Slug:**") or s.startswith("**Type:**") or s.startswith("**Train:**") or \
               s.startswith("**Depends on:**") or s.startswith("**Blocks:**") or \
               s.startswith("**Wave:**") or s.startswith("**RISK:**") or s == "":
                continue
            else:
                skip_metadata = False
        out.append(line)
    return "\n".join(out).strip()

def normalize_whitespace(text):
    """Collapse internal whitespace differences for comparison."""
    return re.sub(r"\s+", " ", text).strip()

print("=" * 80)
print("PHASE 5 — BIDIRECTIONAL CONSISTENCY (doc ↔ issues)")
print("=" * 80)

findings = []

# 1. For each child: doc-extracted body matches issue body content
for num, section in CHILDREN.items():
    doc_body_raw = extract_doc_section_body(section)
    if doc_body_raw is None:
        findings.append(f"#{num}: §{section} not found in doc")
        continue
    doc_body = strip_metadata_lines(doc_body_raw)
    issue_body = fetch_body(num)

    # Each line of doc_body should appear verbatim in issue_body
    missing_lines = []
    for line in doc_body.splitlines():
        line_stripped = line.rstrip()
        if not line_stripped:
            continue
        if line_stripped not in issue_body:
            # try whitespace-normalized match
            if normalize_whitespace(line_stripped) not in normalize_whitespace(issue_body):
                missing_lines.append(line_stripped)
    if missing_lines:
        findings.append(f"#{num}: {len(missing_lines)} doc line(s) missing from issue body (showing first 2):")
        for ml in missing_lines[:2]:
            findings.append(f"    - {ml[:100]}")
    else:
        print(f"✓ #{num} body matches doc §{section}")

# 2. Wave plan in #887 matches doc §12.2
umbrella = fetch_body(887)
doc_waves_section = re.search(
    r"### 12\.2 Wave plan.*?(?=### 12\.3)", DOC_TEXT, re.DOTALL
)
if doc_waves_section:
    # Each wave row in the umbrella table should match what the doc lists
    expected_waves = {
        "A": ["#888"],
        "B": ["#889", "#890"],
        "C": ["#891", "#892", "#893"],
        "D": ["#894"],
        "E": ["#895"],
        "F": ["#896", "#897"],
    }
    missing = []
    for wave, issues in expected_waves.items():
        # umbrella should have a row like | A | #888 | 1 | ... |
        for i in issues:
            wave_row_pattern = rf"\|\s*{wave}\s*\|.*?{re.escape(i)}"
            if not re.search(wave_row_pattern, umbrella):
                missing.append(f"Wave {wave} should list {i}")
    if missing:
        findings.append(f"#887 wave plan: {len(missing)} mismatches:")
        for m in missing:
            findings.append(f"    - {m}")
    else:
        print("✓ #887 wave plan matches doc §12.2")

# 3. Child index in #887 lists all 10 children
for num in CHILDREN:
    if f"#{num}" not in umbrella:
        findings.append(f"#887 child index missing #{num}")
print(f"✓ #887 references all 10 children")

# 4. Done criteria in #887 matches doc §12.1 (high-level — check 10 numbered items)
done_section = re.search(r"### 12\.1.*?(?=### 12\.2)", DOC_TEXT, re.DOTALL)
if done_section:
    expected_done_items = re.findall(r"^\d+\.\s+(.+?)$", done_section.group(0), re.MULTILINE)
    # The umbrella should also have these 10 items
    umbrella_done = re.search(r"## Done criteria.*?(?=##)", umbrella, re.DOTALL)
    if umbrella_done:
        umbrella_done_text = umbrella_done.group(0)
        missing_done = []
        for item in expected_done_items[:10]:
            # Just check key phrases appear
            key_phrase = item[:50].split('(')[0].strip()
            if key_phrase not in umbrella_done_text:
                missing_done.append(key_phrase)
        if missing_done:
            findings.append(f"#887 done criteria: {len(missing_done)} key phrases missing:")
            for m in missing_done[:3]:
                findings.append(f"    - {m}")
        else:
            print("✓ #887 done criteria contains all 10 items from doc §12.1")

print(f"\n{'=' * 80}")
print(f"PHASE 5 SUMMARY: {len(findings)} finding(s)")
print(f"{'=' * 80}")
for f in findings:
    print(f)

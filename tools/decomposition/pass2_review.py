#!/usr/bin/env python3
"""Pass 2: extract Scope and Acceptance sections from each child for content review."""
import json, re, subprocess

ISSUES = list(range(888, 898))

def fetch(num):
    r = subprocess.run(["gh", "issue", "view", str(num), "--json", "title,body"],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)

def extract_section(body, name):
    """Find ## name section OR inline **name:** block."""
    lines = body.splitlines()
    out = []
    capture = False
    for line in lines:
        s = line.strip()
        if s.startswith(f"## {name}") or s.startswith(f"**{name}:**") or s.startswith(f"**{name}**"):
            capture = True
            # capture content on same line after marker
            if "**" in s:
                tail = re.sub(rf"^\*\*{re.escape(name)}:?\*\*\s*", "", s)
                if tail:
                    out.append(tail)
            continue
        if capture and (s.startswith("## ") or s.startswith("**") or s.startswith("---")):
            break
        if capture:
            out.append(line)
    return "\n".join(out).strip()

def check_acceptance(text):
    """Heuristic checks on acceptance criteria."""
    issues = []
    bullets = [l for l in text.splitlines() if l.strip().startswith("- ")]
    if len(bullets) == 0:
        issues.append("no bulleted criteria")

    vague_terms = ["clean", "good", "proper", "appropriate", "reasonable", "etc.", "and so on", "as needed"]
    for b in bullets:
        bl = b.lower()
        for v in vague_terms:
            # check word-boundary to avoid false matches like "clean" matching "cleans"
            if re.search(rf"\b{re.escape(v)}\b", bl):
                issues.append(f"vague term {v!r}: {b.strip()[:80]}")
        # Each bullet SHOULD have a binary signal (command, test, file existence, label change)
        binary_signals = ["pass", "succeed", "fail", "exist", " is ", "equals", "match",
                          "return", "contain", "set to", "=", "≥", "≤", "<", ">",
                          "no ", "all ", "every ", "100%", "0 ", "zero", "merge", "close",
                          "green", "assert", "document", "without", "implements",
                          "writes", "produce", "≥90%", "passes", "trigger"]
        if not any(sig in bl for sig in binary_signals):
            issues.append(f"no binary signal: {b.strip()[:80]}")
    return issues

def check_scope(text):
    issues = []
    if "TBD" in text or "tbd" in text.lower():
        issues.append(f"contains TBD")
    if " etc." in text.lower() or " ...etc" in text.lower():
        issues.append(f"uses etc.")
    # Section refs should look like §X.Y
    section_refs = re.findall(r"§\d+\.?\d*", text)
    return issues, section_refs

print("=" * 80)
print("PASS 2 — CONTENT REVIEW (acceptance testability + scope clarity)")
print("=" * 80)

all_findings = []

for num in ISSUES:
    d = fetch(num)
    body = d["body"]
    title = d["title"][:60]

    scope = extract_section(body, "Scope")
    acceptance = extract_section(body, "Acceptance")

    scope_issues, refs = check_scope(scope)
    acc_issues = check_acceptance(acceptance)

    findings = []
    findings.extend([f"scope: {s}" for s in scope_issues])
    findings.extend([f"acceptance: {s}" for s in acc_issues])

    marker = "✓" if not findings else "✗"
    print(f"\n{marker} #{num} {title}")
    if refs:
        print(f"    refs: {sorted(set(refs))}")
    for f in findings:
        print(f"    ⚠ {f}")
        all_findings.append((num, f))

print(f"\n{'=' * 80}")
print(f"SUMMARY: {len(all_findings)} content finding(s)")
for num, f in all_findings:
    print(f"  [#{num}] {f}")

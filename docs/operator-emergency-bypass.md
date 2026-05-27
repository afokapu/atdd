# Operator Emergency Bypass

> **Operator-only.** This document is not for agents. Agents must follow
> the normal ATDD lifecycle. Do not share bypass instructions with agents
> via CLAUDE.md or any other agent context file.

## When to use

Use only when a post-commit or pre-push validator blocks work that is
genuinely urgent (e.g. security hotfix, broken CI, infrastructure outage)
and there is no time to fix the validator failure first.

## The only supported bypass path

```
atdd emergency --reason '<reason>'
```

This creates `.atdd/EMERGENCY_BYPASS` with a **5-minute TTL**.
All gated hooks check for this file; if it exists and is not expired,
they exit 0 without running validator logic.

After 5 minutes the file expires automatically. No cleanup is needed.

## Example

```bash
atdd emergency --reason "security hotfix for CVE-2026-XXXX — validators offline"
git commit -m "fix(security): patch CVE-2026-XXXX"
```

## What is NOT supported

- Environment variables: all `ATDD_SKIP_*` vars were retired (E026/E030, 2026-05-26).
  Setting them has no effect.
- `--no-verify` on git hooks: the pre-push Layer 1 hook enforces this guard
  and blocks pushes that attempt to bypass it.

## Audit trail

The `atdd emergency` command logs the reason and timestamp to
`.atdd/runtime/emergency_bypass.log` for post-incident review.

## After the emergency

Once the urgent work is merged, open a follow-up issue to fix the root
cause of the validator failure. Do not leave `.atdd/EMERGENCY_BYPASS` in
the repo; it is gitignored and expires on its own.

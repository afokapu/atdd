"""SPIKE (#1895): are 'no such issue' and 'GitHub refused' actually separable?

`_fetch_issue` returns None for both, and the caller prints "could not fetch
issue #N" and exits 1 — so a rate limit reads as a missing issue and sends the
operator to look for an issue that is sitting there fine.

Measured today against the real API: both exit 1, and their stderr differs
unmistakably. This checks that a classifier over stderr separates every
real-world condition, using a stub that replays the captured strings.
"""
import os, subprocess, sys

MODES = ["ok", "not_found", "rate_limit", "secondary", "auth", "network", "server", "garbage"]
BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")

print(f"{'MODE':12} {'rc':>3}  {'stderr / stdout (first 62 chars)'}")
print("-" * 88)
for mode in MODES:
    env = {**os.environ, "PATH": BIN + os.pathsep + os.environ["PATH"], "LAB_GH_MODE": mode}
    r = subprocess.run(["gh", "issue", "view", "1", "--json", "number"],
                       capture_output=True, text=True, env=env)
    blob = (r.stderr or r.stdout).strip().replace("\n", " ")
    print(f"{mode:12} {r.returncode:>3}  {blob[:62]}")

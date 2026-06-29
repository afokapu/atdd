"""RED fixture: two DB calls inside loops. The detector emits ONE raw violation —
the second call carries an inline `# noqa: N+1` DETECTION exemption (core parity)
and is NOT emitted. Strict disposition turns the one raw violation into FAIL.

  - repo.find_one(i) inside a for loop          -> emitted (violation)
  - repo.find_one(j) inside a for loop, noqa'd   -> NOT emitted (detection exemption)
"""


def load_users(repo, ids):
    results = []
    for i in ids:
        results.append(repo.find_one(i))   # N+1 -> violation
    return results


def load_orders(repo, ids):
    results = []
    for j in ids:
        results.append(repo.find_one(j))  # noqa: N+1
    return results

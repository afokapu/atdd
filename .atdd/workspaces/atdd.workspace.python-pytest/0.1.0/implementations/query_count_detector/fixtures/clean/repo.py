"""GREEN fixture: queries are batched OUTSIDE loops -> RAW = [] -> strict PASS."""


def load_users(repo, ids):
    # One batched query, not one-per-item.
    users = repo.find_many(ids)
    results = []
    for user in users:
        results.append(user.name)  # no DB call inside the loop
    return results

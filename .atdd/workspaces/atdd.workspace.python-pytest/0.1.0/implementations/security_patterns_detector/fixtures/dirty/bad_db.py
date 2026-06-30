"""Dirty: SQL built by string concatenation passed to a sink -> sql-injection."""


def fetch_user(cursor, name):
    # ❌ "SELECT ..." + name concatenation reaching .execute()
    cursor.execute("SELECT * FROM users WHERE name = '" + name + "'")
    return cursor.fetchone()

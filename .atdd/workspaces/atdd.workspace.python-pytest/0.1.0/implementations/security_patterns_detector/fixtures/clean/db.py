"""Clean: parameterized queries — static SQL string + bound parameters."""


def fetch_user(cursor, user_id):
    # Static constant query + bound parameter — not a dynamic string, not flagged.
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()


def insert_user(cursor, name):
    cursor.execute("INSERT INTO users (name) VALUES (?)", (name,))

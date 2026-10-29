import sqlite3


def find_user(name: str):
    connection = sqlite3.connect("users.db")
    cursor = connection.cursor()
    # Expected: PY-SQL-001
    return cursor.execute("SELECT * FROM users WHERE name = '" + name + "'").fetchall()


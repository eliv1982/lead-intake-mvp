import os
import sqlite3
from pathlib import Path


DB_PATH = Path("data/leads.db")


def init_db() -> None:
    """Create SQLite database and leads table if they do not exist."""
    os.makedirs(DB_PATH.parent, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                name TEXT,
                contact TEXT NOT NULL,
                source TEXT,
                comment TEXT
            )
            """
        )
        connection.commit()


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with rows as dictionaries."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

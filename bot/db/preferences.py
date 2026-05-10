"""SQLite persistence layer for user preferences (provider selections)."""

import asyncio
import sqlite3
from pathlib import Path

_DB_PATH = Path("data/preferences.db")
_lock = asyncio.Lock()


def init_preferences_db() -> None:
    """Create tables if they don't exist. Called once on startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id  INTEGER NOT NULL,
                key      TEXT    NOT NULL,
                value    TEXT    NOT NULL,
                PRIMARY KEY (user_id, key)
            );
        """)
        con.commit()
    finally:
        con.close()


async def get_preference(user_id: int, key: str) -> str | None:
    """Return preference value, or None if not set."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            row = con.execute(
                "SELECT value FROM user_preferences WHERE user_id = ? AND key = ?",
                (user_id, key),
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()


async def set_preference(user_id: int, key: str, value: str) -> None:
    """Set or update a preference."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            con.execute(
                "INSERT OR REPLACE INTO user_preferences (user_id, key, value) VALUES (?, ?, ?)",
                (user_id, key, value),
            )
            con.commit()
        finally:
            con.close()


async def get_all_preferences(user_id: int) -> dict[str, str]:
    """Return all preferences for a user as {key: value}."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            rows = con.execute(
                "SELECT key, value FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return dict(rows)
        finally:
            con.close()

"""SQLite persistence layer for user credits."""

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bot.config import settings

_DB_PATH = Path(f"data/credits_{settings.bot_env}.db")
_lock = asyncio.Lock()


def init_db() -> None:
    """Create tables if they don't exist. Called once on startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            balance    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            delta      INTEGER NOT NULL,
            reason     TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        );
    """)
    con.commit()
    con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_balance(user_id: int) -> int | None:
    """Return balance, or None if user doesn't exist."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        row = con.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        con.close()
        return row[0] if row else None


async def create_user(user_id: int, initial_balance: int, reason: str) -> int:
    """Insert a new user with initial_balance. Returns final balance."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        now = _now()
        con.execute(
            "INSERT INTO users (user_id, balance, created_at) VALUES (?, ?, ?)",
            (user_id, initial_balance, now),
        )
        if initial_balance != 0:
            con.execute(
                "INSERT INTO transactions (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
                (user_id, initial_balance, reason, now),
            )
        con.commit()
        con.close()
        return initial_balance


async def add_credits(user_id: int, delta: int, reason: str) -> int:
    """Add delta credits to user and log transaction. Returns new balance."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        now = _now()
        con.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
        con.execute(
            "INSERT INTO transactions (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, delta, reason, now),
        )
        con.commit()
        row = con.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        con.close()
        return row[0]


async def deduct_credits(user_id: int, delta: int, reason: str) -> int:
    """Deduct delta credits (delta should be positive). Returns new balance."""
    return await add_credits(user_id, -delta, reason)

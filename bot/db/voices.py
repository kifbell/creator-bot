"""SQLite persistence layer for saved voice descriptions and audio samples."""

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path("data/voices.db")
_lock = asyncio.Lock()


def init_voices_db() -> None:
    """Create tables if they don't exist. Called once on startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS voice_descriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT    NOT NULL,
                description TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vd_user_name
                ON voice_descriptions(user_id, name);

            CREATE TABLE IF NOT EXISTS voice_samples (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                name       TEXT    NOT NULL,
                file_path  TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vs_user_name
                ON voice_samples(user_id, name);
        """)
        con.commit()
    finally:
        con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Voice descriptions ───────────────────────────────────────────────

async def save_voice_description(user_id: int, name: str, description: str) -> int:
    """Save a voice description. Returns the row id."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            cur = con.execute(
                "INSERT INTO voice_descriptions (user_id, name, description, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, name, description, _now()),
            )
            con.commit()
            return cur.lastrowid
        finally:
            con.close()


async def list_voice_descriptions(user_id: int) -> list[tuple[int, str, str]]:
    """Return [(id, name, description), ...] ordered newest-first."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            return con.execute(
                "SELECT id, name, description FROM voice_descriptions "
                "WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        finally:
            con.close()


async def get_voice_description(user_id: int, voice_id: int) -> tuple[str, str] | None:
    """Return (name, description) or None."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            return con.execute(
                "SELECT name, description FROM voice_descriptions WHERE id = ? AND user_id = ?",
                (voice_id, user_id),
            ).fetchone()
        finally:
            con.close()


async def delete_voice_description(user_id: int, voice_id: int) -> None:
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            con.execute(
                "DELETE FROM voice_descriptions WHERE id = ? AND user_id = ?",
                (voice_id, user_id),
            )
            con.commit()
        finally:
            con.close()


# ── Voice samples ────────────────────────────────────────────────────

async def save_voice_sample(user_id: int, name: str, file_path: str) -> int:
    """Save a voice sample reference. Returns the row id."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            cur = con.execute(
                "INSERT INTO voice_samples (user_id, name, file_path, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, name, file_path, _now()),
            )
            con.commit()
            return cur.lastrowid
        finally:
            con.close()


async def list_voice_samples(user_id: int) -> list[tuple[int, str, str]]:
    """Return [(id, name, file_path), ...] ordered newest-first."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            return con.execute(
                "SELECT id, name, file_path FROM voice_samples "
                "WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        finally:
            con.close()


async def get_voice_sample(user_id: int, voice_id: int) -> tuple[str, str] | None:
    """Return (name, file_path) or None."""
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            return con.execute(
                "SELECT name, file_path FROM voice_samples WHERE id = ? AND user_id = ?",
                (voice_id, user_id),
            ).fetchone()
        finally:
            con.close()


async def delete_voice_sample(user_id: int, voice_id: int) -> None:
    async with _lock:
        con = sqlite3.connect(_DB_PATH)
        try:
            con.execute(
                "DELETE FROM voice_samples WHERE id = ? AND user_id = ?",
                (voice_id, user_id),
            )
            con.commit()
        finally:
            con.close()

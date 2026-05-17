"""SQLite persistence layer for user credits."""

import asyncio
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from bot.config import settings
from bot.db.connection import connect

_DB_PATH = Path(f"data/credits_{settings.bot_env}.db")
_lock = asyncio.Lock()
_logger = logging.getLogger(__name__)


def init_db() -> None:
    """Create tables if they don't exist. Called once on startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(_DB_PATH)) as con:
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

            CREATE TABLE IF NOT EXISTS pending_payments (
                payment_id  TEXT    PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                provider    TEXT    NOT NULL,
                amount_rub  INTEGER NOT NULL,
                credits     INTEGER NOT NULL,
                status      TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_payments_user
                ON pending_payments(user_id, status);
        """)
        con.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_balance(user_id: int) -> int | None:
    """Return balance, or None if user doesn't exist."""
    async with connect(_DB_PATH, _lock) as con:
        row = con.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row[0] if row else None


async def create_user(user_id: int, initial_balance: int, reason: str) -> int:
    """Idempotent: insert user only if not already present. Safe under concurrency.
    Returns the user's current balance (initial_balance for new users, existing for returning)."""
    async with connect(_DB_PATH, _lock) as con:
        now = _now()
        cursor = con.execute(
            "INSERT OR IGNORE INTO users (user_id, balance, created_at) VALUES (?, ?, ?)",
            (user_id, initial_balance, now),
        )
        inserted = cursor.rowcount > 0
        if inserted and initial_balance != 0:
            con.execute(
                "INSERT INTO transactions (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
                (user_id, initial_balance, reason, now),
            )
        con.commit()
        row = con.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if inserted:
            _logger.info("user_created user_id=%s balance=%s", user_id, initial_balance)
        return row[0] if row else initial_balance


async def add_credits(user_id: int, delta: int, reason: str) -> int:
    """Add delta credits to user and log transaction. Returns new balance."""
    async with connect(_DB_PATH, _lock) as con:
        now = _now()
        con.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
        con.execute(
            "INSERT INTO transactions (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, delta, reason, now),
        )
        con.commit()
        row = con.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        # None guard mirrors peer functions (create_user, credit_pending_payment).
        # Currently unreachable because every caller precedes with ensure_user(),
        # but defends against future callers that skip that step.
        return row[0] if row else delta


async def deduct_credits(user_id: int, delta: int, reason: str) -> int:
    """Deduct delta credits (delta should be positive). Returns new balance."""
    return await add_credits(user_id, -delta, reason)


async def check_and_deduct_credits(user_id: int, amount: int, reason: str) -> bool:
    """Atomically check balance and deduct. Returns False if insufficient funds."""
    async with connect(_DB_PATH, _lock) as con:
        row = con.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None or row[0] < amount:
            _logger.info(
                "credit_deduct_denied user_id=%s amount=%s reason=%s balance=%s",
                user_id, amount, reason, row[0] if row else None,
            )
            return False
        now = _now()
        con.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        con.execute(
            "INSERT INTO transactions (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, -amount, reason, now),
        )
        con.commit()
        _logger.info(
            "credit_deducted user_id=%s amount=%s reason=%s new_balance=%s",
            user_id, amount, reason, row[0] - amount,
        )
        return True


# ── Pending payments ──────────────────────────────────────────────────

async def record_pending_payment(
    payment_id: str,
    user_id: int,
    provider: str,
    amount_rub: int,
    credits: int,
) -> None:
    """Insert a new pending payment row (status='pending')."""
    async with connect(_DB_PATH, _lock) as con:
        now = _now()
        con.execute(
            "INSERT INTO pending_payments "
            "(payment_id, user_id, provider, amount_rub, credits, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (payment_id, user_id, provider, amount_rub, credits, now, now),
        )
        con.commit()
        _logger.info(
            "payment_recorded payment_id=%s user_id=%s provider=%s amount_rub=%s credits=%s",
            payment_id, user_id, provider, amount_rub, credits,
        )


async def mark_payment_status(payment_id: str, status: str) -> None:
    """Set status to one of: 'pending' | 'succeeded' | 'canceled'.
    Does NOT modify users.balance — use credit_pending_payment() for crediting."""
    async with connect(_DB_PATH, _lock) as con:
        con.execute(
            "UPDATE pending_payments SET status = ?, updated_at = ? WHERE payment_id = ?",
            (status, _now(), payment_id),
        )
        con.commit()
        _logger.info("payment_status_updated payment_id=%s status=%s", payment_id, status)


async def get_pending_payment_for_user(user_id: int) -> dict | None:
    """Return the most recent pending payment for a user (status='pending'), or None.
    Used by the Resume Payment UX in topup."""
    async with connect(_DB_PATH, _lock) as con:
        row = con.execute(
            "SELECT payment_id, provider, amount_rub, credits, created_at "
            "FROM pending_payments WHERE user_id = ? AND status = 'pending' "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "payment_id": row[0],
            "provider": row[1],
            "amount_rub": row[2],
            "credits": row[3],
            "created_at": row[4],
        }


async def get_pending_payment(payment_id: str) -> dict | None:
    """Return a pending payment by id (any status), or None."""
    async with connect(_DB_PATH, _lock) as con:
        row = con.execute(
            "SELECT payment_id, user_id, provider, amount_rub, credits, status, created_at "
            "FROM pending_payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "payment_id": row[0],
            "user_id": row[1],
            "provider": row[2],
            "amount_rub": row[3],
            "credits": row[4],
            "status": row[5],
            "created_at": row[6],
        }


async def credit_pending_payment(payment_id: str) -> tuple[bool, int]:
    """Atomic: if pending_payments.status='succeeded', mark 'credited',
    update users.balance, insert transactions row — all in one transaction.
    Transaction `reason` is sourced from the row's `provider` column,
    so Mock and YooKassa payments are recorded correctly.
    Returns (was_credited_now, new_balance). Returns (False, 0) if not eligible."""
    async with connect(_DB_PATH, _lock) as con:
        row = con.execute(
            "SELECT user_id, credits, provider FROM pending_payments "
            "WHERE payment_id = ? AND status = 'succeeded'",
            (payment_id,),
        ).fetchone()
        if row is None:
            return (False, 0)
        user_id, credits, provider = row
        now = _now()
        reason = f"topup_{provider}"
        con.execute(
            "UPDATE pending_payments SET status = 'credited', updated_at = ? WHERE payment_id = ?",
            (now, payment_id),
        )
        con.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (credits, user_id),
        )
        con.execute(
            "INSERT INTO transactions (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, credits, reason, now),
        )
        con.commit()
        new_balance_row = con.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        new_balance = new_balance_row[0] if new_balance_row else credits
        _logger.info(
            "payment_credited payment_id=%s user_id=%s credits=%s provider=%s new_balance=%s",
            payment_id, user_id, credits, provider, new_balance,
        )
        return (True, new_balance)

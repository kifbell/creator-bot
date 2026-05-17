"""Shared SQLite connection context manager.

Acquires the module's async lock, opens a connection, yields it, and
guarantees both lock release and close() on exit — so callers don't need
to write try/finally in every DB function.

Synchronous init functions use ``contextlib.closing(sqlite3.connect(...))``
from stdlib for the same lifecycle guarantee without the async lock.
"""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator


@asynccontextmanager
async def connect(
    db_path: Path, lock: asyncio.Lock
) -> AsyncIterator[sqlite3.Connection]:
    async with lock:
        con = sqlite3.connect(db_path)
        try:
            yield con
        finally:
            con.close()

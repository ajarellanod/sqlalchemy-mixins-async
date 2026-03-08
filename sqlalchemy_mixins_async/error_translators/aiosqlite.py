from __future__ import annotations

"""
Integrity translation for the `sqlite+aiosqlite` SQLAlchemy dialect.

`aiosqlite` wraps SQLite's native `sqlite3` exceptions, so translation is
based on the underlying `sqlite3.IntegrityError`.
"""

import sqlite3

from ..errors import AlreadyExistsError, MissingReferenceError
from .base import iter_error_chain


def translate_aiosqlite_integrity_error(error):
    for current in iter_error_chain(error):
        if not isinstance(current, sqlite3.IntegrityError):
            continue
        message = str(current).lower()
        if "unique constraint failed" in message:
            return AlreadyExistsError(str(current))
        if "foreign key constraint failed" in message:
            return MissingReferenceError(str(current))
    return None

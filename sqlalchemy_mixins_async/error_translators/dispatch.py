from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from ..errors import DatabaseConstraintError
from .asyncpg import translate_asyncpg_integrity_error
from .aiomysql import translate_aiomysql_integrity_error
from .aiosqlite import translate_aiosqlite_integrity_error


TRANSLATORS = (
    translate_asyncpg_integrity_error,
    translate_aiomysql_integrity_error,
    translate_aiosqlite_integrity_error,
)


def translate_integrity_error(error: IntegrityError) -> IntegrityError | DatabaseConstraintError:
    """Dispatch integrity-error translation across supported async drivers."""
    for translator in TRANSLATORS:
        translated = translator(error)
        if translated is not None:
            return translated
    return error

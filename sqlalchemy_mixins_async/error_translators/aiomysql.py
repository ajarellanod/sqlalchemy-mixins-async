from __future__ import annotations

"""
Integrity translation for the `mysql+aiomysql` SQLAlchemy dialect.

`aiomysql` surfaces MySQL constraint failures via PyMySQL-style exceptions,
so this translator inspects those underlying driver error codes.
"""

try:
    from pymysql.constants import ER  # type: ignore[import-untyped]
    from pymysql.err import IntegrityError as MySQLIntegrityError  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    ER = None
    MySQLIntegrityError = None

from ..errors import AlreadyExistsError, MissingReferenceError
from .base import iter_error_chain


MYSQL_UNIQUE_CODES = {1062}
MYSQL_FOREIGN_KEY_CODES = {1216, 1217, 1451, 1452}


def translate_aiomysql_integrity_error(error):
    if MySQLIntegrityError is None or ER is None:
        return None

    foreign_key_codes = MYSQL_FOREIGN_KEY_CODES | {
        ER.NO_REFERENCED_ROW_2,
        ER.ROW_IS_REFERENCED_2,
    }

    for current in iter_error_chain(error):
        if not isinstance(current, MySQLIntegrityError):
            continue
        code = current.args[0] if current.args else None
        if code in MYSQL_UNIQUE_CODES or code == ER.DUP_ENTRY:
            return AlreadyExistsError(str(current))
        if code in foreign_key_codes:
            return MissingReferenceError(str(current))
    return None

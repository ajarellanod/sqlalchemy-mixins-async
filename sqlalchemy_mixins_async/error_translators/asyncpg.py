from __future__ import annotations

try:
    from asyncpg.exceptions import ForeignKeyViolationError, UniqueViolationError
except ImportError:  # pragma: no cover
    ForeignKeyViolationError = UniqueViolationError = None

from ..errors import AlreadyExistsError, MissingReferenceError
from .base import iter_error_chain


def translate_asyncpg_integrity_error(error):
    if UniqueViolationError is None or ForeignKeyViolationError is None:
        return None

    for current in iter_error_chain(error):
        if isinstance(current, UniqueViolationError):
            return AlreadyExistsError(str(current))
        if isinstance(current, ForeignKeyViolationError):
            return MissingReferenceError(str(current))
    return None

from __future__ import annotations


class DatabaseConstraintError(RuntimeError):
    """Base class for translated database constraint failures."""


class AlreadyExistsError(DatabaseConstraintError):
    """Raised when a unique constraint is violated."""


class MissingReferenceError(DatabaseConstraintError):
    """Raised when a foreign key points to a missing row."""

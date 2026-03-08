from .activerecord import ActiveRecordMixin, ModelNotFoundError
from .eagerload import JOINED, SELECTIN, SUBQUERY, EagerLoadMixin, eager_expr
from .errors import AlreadyExistsError, DatabaseConstraintError, MissingReferenceError
from .inspection import InspectionMixin
from .query import QueryMixin, and_, apply_query, or_
from .repr import ReprMixin
from .serialize import SerializeMixin
from .session import NoSessionError, SessionMixin
from .timestamp import TimestampsMixin


class AllFeaturesMixin(ActiveRecordMixin, QueryMixin, ReprMixin, SerializeMixin):
    __abstract__ = True
    __repr__ = ReprMixin.__repr__


class FastAPIMixin(ActiveRecordMixin, QueryMixin, ReprMixin):
    """No SerializeMixin, as it's not needed for FastAPI."""

    __abstract__ = True
    __repr__ = ReprMixin.__repr__


__all__ = [
    "ActiveRecordMixin",
    "AllFeaturesMixin",
    "FastAPIMixin",
    "AlreadyExistsError",
    "DatabaseConstraintError",
    "EagerLoadMixin",
    "eager_expr",
    "InspectionMixin",
    "JOINED",
    "ModelNotFoundError",
    "MissingReferenceError",
    "NoSessionError",
    "ReprMixin",
    "SELECTIN",
    "SerializeMixin",
    "SessionMixin",
    "and_",
    "apply_query",
    "or_",
    "QueryMixin",
    "SUBQUERY",
    "TimestampsMixin",
]

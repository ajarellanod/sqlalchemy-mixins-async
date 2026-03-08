from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import joinedload, selectinload, subqueryload

JOINED = "joined"
SELECTIN = "selectin"
SUBQUERY = "subquery"


def eager_expr(schema: dict | None):
    """Translate a nested loader schema into SQLAlchemy loader options."""
    return _eager_expr_from_schema(schema or {})


def _create_eager_load_option(path, join_method: str):
    if join_method == JOINED:
        return joinedload(path)
    if join_method == SELECTIN:
        return selectinload(path)
    if join_method == SUBQUERY:
        return subqueryload(path)
    raise ValueError(f"Bad join method `{join_method}` in `{path}`")


def _eager_expr_from_schema(schema: dict) -> list:
    result = []
    for path, value in schema.items():
        if isinstance(value, tuple):
            join_method, inner_schema = value
            result.append(
                _create_eager_load_option(path, join_method).options(
                    *_eager_expr_from_schema(inner_schema)
                )
            )
        elif isinstance(value, dict):
            result.append(
                _create_eager_load_option(path, SELECTIN).options(
                    *_eager_expr_from_schema(value)
                )
            )
        else:
            result.append(_create_eager_load_option(path, value))
    return result


class EagerLoadMixin:
    """Convenience builders for eager-loading statements."""

    __abstract__ = True

    @classmethod
    def select_stmt(cls) -> Select:
        return select(cls)

    @classmethod
    def with_(cls, schema: dict) -> Select:
        """Build a `Select` with nested eager-loading options from a schema.

        Use this when you need a full loading plan, especially for nested
        relationships or when different relationships should use different
        loading strategies. For simple one-level eager loading, prefer
        `with_joined()`, `with_selectin()`, or `with_subquery()`.
        """
        return cls.select_stmt().options(*eager_expr(schema))

    @classmethod
    def with_joined(cls, *paths) -> Select:
        """Build a `Select` using `joinedload` for the given relationships.

        Use this when each parent row points to a single related row, or when
        the related data set is small enough that loading everything in one SQL
        query is cheaper than issuing follow-up queries.
        """
        return cls.select_stmt().options(*[joinedload(path) for path in paths])

    @classmethod
    def with_selectin(cls, *paths) -> Select:
        """Build a `Select` using `selectinload` for the given relationships.

        Use this as the default choice for collections. It loads the parent rows
        first, then fetches related rows in a separate query with an `IN (...)`
        clause, which usually avoids the row explosion caused by large joins.
        """
        return cls.select_stmt().options(*[selectinload(path) for path in paths])

    @classmethod
    def with_subquery(cls, *paths) -> Select:
        """Build a `Select` using `subqueryload` for the given relationships.

        Use this only for specific query shapes where it performs better than
        `selectinload`, or when you need it for compatibility with existing
        loading behavior. It is usually not the default choice.
        """
        return cls.select_stmt().options(*[subqueryload(path) for path in paths])

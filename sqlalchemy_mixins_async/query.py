from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import Select, asc, desc, extract, inspect, select
from sqlalchemy.orm import aliased, contains_eager
from sqlalchemy.sql import operators

from .eagerload import EagerLoadMixin, _eager_expr_from_schema
from .inspection import InspectionMixin
from .utils import classproperty

RELATION_SPLITTER = "___"
OPERATOR_SPLITTER = "__"
DESC_PREFIX = "-"


@dataclass(frozen=True)
class AliasInfo:
    alias: Any
    relationship: Any


def and_(*filters):
    """Build an explicit AND group for nested query filters."""
    return {operators.and_: list(filters)}


def or_(*filters):
    """Build an explicit OR group for nested query filters."""
    return {operators.or_: list(filters)}


def _flatten_where_keys(where):
    """Yield filter keys from nested boolean filter groups."""
    if isinstance(where, Mapping):
        for key, value in where.items():
            if callable(key):
                yield from _flatten_where_keys(value)
            else:
                yield key
    elif isinstance(where, Sequence) and not isinstance(where, (str, bytes)):
        for item in where:
            yield from _flatten_where_keys(item)
    else:
        raise TypeError(f"Unsupported type in where: {type(where)!r}")


def _get_root_entity(stmt: Select):
    """Resolve the root ORM entity from a statement when it is not provided."""
    for description in stmt.column_descriptions:
        entity = description.get("entity")
        if entity is not None:
            return entity
    raise ValueError(f"Cannot get a root entity from `{stmt}`")


def _entity_class(entity):
    return inspect(entity).mapper.class_


def _parse_path_and_make_aliases(
    entity, entity_path: str, attrs: list[str], aliases
) -> None:
    """Build aliased joins required by relation-path filters and sorts."""
    relations: dict[str, list[str]] = {}
    entity_cls = _entity_class(entity)

    for attr in attrs:
        if RELATION_SPLITTER not in attr:
            continue
        relation_name, nested_attr = attr.split(RELATION_SPLITTER, 1)
        relations.setdefault(relation_name, []).append(nested_attr)

    for relation_name, nested_attrs in relations.items():
        path = (
            f"{entity_path}{RELATION_SPLITTER}{relation_name}"
            if entity_path
            else relation_name
        )
        if relation_name not in entity_cls.relations:
            raise KeyError(
                f"Incorrect path `{path}`: {entity_cls} doesnt have `{relation_name}` relationship"
            )
        relationship = getattr(entity, relation_name)
        alias = aliased(relationship.property.mapper.class_)
        aliases[path] = AliasInfo(alias=alias, relationship=relationship)
        _parse_path_and_make_aliases(alias, path, nested_attrs, aliases)


def _build_contains_eager_options(aliases: OrderedDict[str, AliasInfo]) -> list:
    """Mirror relation-path joins into eager-loading hints for loaded entities."""
    options = []
    for path in aliases:
        chain = path.split(RELATION_SPLITTER)
        current = None
        for index in range(len(chain)):
            sub_path = RELATION_SPLITTER.join(chain[: index + 1])
            sub_info = aliases[sub_path]
            if current is None:
                current = contains_eager(sub_info.relationship, alias=sub_info.alias)
            else:
                current = current.contains_eager(
                    sub_info.relationship, alias=sub_info.alias
                )
        if current is not None:
            options.append(current)
    return options


def _normalize_order_by(order_by) -> list[str]:
    return list(order_by or [])


def _collect_query_attrs(where, order_by: list[str]) -> list[str]:
    if not where:
        return [attr.lstrip(DESC_PREFIX) for attr in order_by]
    return list(_flatten_where_keys(where)) + [
        attr.lstrip(DESC_PREFIX) for attr in order_by
    ]


def _build_where_clauses(root_entity, aliases, where):
    if not where:
        return []

    def recurse_where(current_where):
        if isinstance(current_where, Mapping):
            for attr, value in current_where.items():
                if callable(attr):
                    yield attr(*recurse_where(value))
                    continue
                if RELATION_SPLITTER in attr:
                    relation_path, attr_name = attr.rsplit(RELATION_SPLITTER, 1)
                    entity, mapper_class = (
                        aliases[relation_path].alias,
                        _entity_class(aliases[relation_path].alias),
                    )
                else:
                    entity, mapper_class = root_entity, _entity_class(root_entity)
                    attr_name = attr
                try:
                    yield from mapper_class.filter_expr(entity, **{attr_name: value})
                except KeyError as exc:
                    raise KeyError(f"Incorrect filter path `{attr}`: {exc}") from exc
        elif isinstance(current_where, Sequence) and not isinstance(
            current_where, (str, bytes)
        ):
            for item in current_where:
                yield from recurse_where(item)

    return list(recurse_where(where))


def _apply_order_by(stmt: Select, root_entity, aliases, order_by: list[str]) -> Select:
    for attr in order_by:
        if RELATION_SPLITTER in attr.lstrip(DESC_PREFIX):
            prefix = DESC_PREFIX if attr.startswith(DESC_PREFIX) else ""
            clean_attr = attr.lstrip(DESC_PREFIX)
            relation_path, attr_name = clean_attr.rsplit(RELATION_SPLITTER, 1)
            entity = aliases[relation_path].alias
            mapper_class = _entity_class(entity)
            attr_name = prefix + attr_name
        else:
            entity = root_entity
            mapper_class = _entity_class(root_entity)
            attr_name = attr
        try:
            stmt = stmt.order_by(*mapper_class.order_expr(entity, attr_name))
        except KeyError as exc:
            raise KeyError(f"Incorrect order path `{attr}`: {exc}") from exc
    return stmt


def apply_query(
    stmt: Select,
    *,
    model=None,
    where: dict | list | None = None,
    order_by=None,
    load: dict | None = None,
) -> Select:
    """Apply the Django-like filter/order DSL to a SQLAlchemy `Select`."""
    root_entity = model or _get_root_entity(stmt)
    where = where or {}
    order_by = _normalize_order_by(order_by)

    attrs = _collect_query_attrs(where, order_by)
    aliases: OrderedDict[str, AliasInfo] = OrderedDict()
    _parse_path_and_make_aliases(root_entity, "", attrs, aliases)

    for info in aliases.values():
        stmt = stmt.outerjoin(info.alias, info.relationship)

    stmt = stmt.filter(*_build_where_clauses(root_entity, aliases, where))
    stmt = _apply_order_by(stmt, root_entity, aliases, order_by)

    if aliases:
        stmt = stmt.options(*_build_contains_eager_options(aliases))
    if load:
        stmt = stmt.options(*_eager_expr_from_schema(load))

    return stmt


class QueryMixin(InspectionMixin, EagerLoadMixin):
    """Statement builders for Django-like filtering and relation-path sorting."""

    __abstract__ = True

    _operators: dict[str, Callable[..., Any]] = {
        "isnull": lambda c, v: (c is None) if v else (c is not None),
        "exact": operators.eq,
        "ne": operators.ne,
        "gt": operators.gt,
        "ge": operators.ge,
        "lt": operators.lt,
        "le": operators.le,
        "in": operators.in_op,
        "notin": operators.notin_op,
        "between": lambda c, v: c.between(v[0], v[1]),
        "like": operators.like_op,
        "ilike": operators.ilike_op,
        "startswith": operators.startswith_op,
        "istartswith": lambda c, v: c.ilike(v + "%"),
        "endswith": operators.endswith_op,
        "iendswith": lambda c, v: c.ilike("%" + v),
        "contains": lambda c, v: c.ilike(f"%{v}%"),
        "year": lambda c, v: extract("year", c) == v,
        "year_ne": lambda c, v: extract("year", c) != v,
        "year_gt": lambda c, v: extract("year", c) > v,
        "year_ge": lambda c, v: extract("year", c) >= v,
        "year_lt": lambda c, v: extract("year", c) < v,
        "year_le": lambda c, v: extract("year", c) <= v,
        "month": lambda c, v: extract("month", c) == v,
        "month_ne": lambda c, v: extract("month", c) != v,
        "month_gt": lambda c, v: extract("month", c) > v,
        "month_ge": lambda c, v: extract("month", c) >= v,
        "month_lt": lambda c, v: extract("month", c) < v,
        "month_le": lambda c, v: extract("month", c) <= v,
        "day": lambda c, v: extract("day", c) == v,
        "day_ne": lambda c, v: extract("day", c) != v,
        "day_gt": lambda c, v: extract("day", c) > v,
        "day_ge": lambda c, v: extract("day", c) >= v,
        "day_lt": lambda c, v: extract("day", c) < v,
        "day_le": lambda c, v: extract("day", c) <= v,
    }

    @classproperty
    def filterable_attributes(cls) -> list[str]:
        return cls.relations + cls.columns + cls.hybrid_properties + cls.hybrid_methods

    @classproperty
    def sortable_attributes(cls) -> list[str]:
        return cls.columns + cls.hybrid_properties

    @classmethod
    def filter_expr(cls, mapper_or_alias=None, **filters) -> list:
        """Translate simple field filters into SQLAlchemy expressions."""
        mapper = mapper_or_alias or cls
        expressions = []
        valid_attributes = cls.filterable_attributes

        for attr, value in filters.items():
            if attr in cls.hybrid_methods:
                expressions.append(getattr(cls, attr)(value, mapper=mapper))
                continue

            if OPERATOR_SPLITTER in attr:
                attr_name, op_name = attr.rsplit(OPERATOR_SPLITTER, 1)
                if op_name not in cls._operators:
                    raise KeyError(
                        f"Expression `{attr}` has incorrect operator `{op_name}`"
                    )
                op = cls._operators[op_name]
            else:
                attr_name, op = attr, operators.eq

            if attr_name not in valid_attributes:
                raise KeyError(
                    f"Expression `{attr}` has incorrect attribute `{attr_name}`"
                )

            expressions.append(op(getattr(mapper, attr_name), value))

        return expressions

    @classmethod
    def order_expr(cls, mapper_or_alias=None, *columns: str) -> list:
        """Translate sortable field names into SQLAlchemy order expressions."""
        mapper = mapper_or_alias or cls
        expressions = []
        for attr in columns:
            fn, attr_name = (
                (desc, attr[1:]) if attr.startswith(DESC_PREFIX) else (asc, attr)
            )
            if attr_name not in cls.sortable_attributes:
                raise KeyError(f"Cant order {cls} by {attr_name}")
            expressions.append(fn(getattr(mapper, attr_name)))
        return expressions

    @classmethod
    def select_stmt(cls) -> Select:
        return select(cls)

    @classmethod
    def query(cls, where=None, order_by=None, load=None) -> Select:
        """Build a `Select` for this model using the query DSL."""
        return apply_query(
            cls.select_stmt(), model=cls, where=where, order_by=order_by, load=load
        )

    @classmethod
    def where(cls, **filters) -> Select:
        """Shortcut for `query(where=...)`."""
        return cls.query(where=filters)

    @classmethod
    def order_by(cls, *columns: str) -> Select:
        """Shortcut for `query(order_by=...)`."""
        return cls.query(order_by=columns)

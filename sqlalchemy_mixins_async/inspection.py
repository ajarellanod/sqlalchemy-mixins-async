from __future__ import annotations

from typing import Any, cast

from sqlalchemy import inspect
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import RelationshipProperty

from .utils import classproperty


class InspectionMixin:
    __abstract__ = True

    @classproperty
    def columns(cls) -> list[str]:
        inspected = cast(Any, inspect(cls))
        return list(inspected.columns.keys())

    @classproperty
    def primary_keys_full(cls):
        mapper = cast(Any, inspect(cls)).mapper
        return [mapper.get_property_by_column(column) for column in mapper.primary_key]

    @classproperty
    def primary_keys(cls) -> list[str]:
        return [pk.key for pk in cls.primary_keys_full]

    @classproperty
    def relations(cls) -> list[str]:
        mapper = cast(Any, inspect(cls)).mapper
        return [
            attr.key
            for attr in mapper.attrs
            if isinstance(attr, RelationshipProperty)
        ]

    @classproperty
    def settable_relations(cls) -> list[str]:
        return [name for name in cls.relations if not getattr(cls, name).property.viewonly]

    @classproperty
    def hybrid_properties(cls) -> list[str]:
        descriptors = cast(Any, inspect(cls)).all_orm_descriptors
        return [
            descriptor.__name__
            for descriptor in descriptors
            if isinstance(descriptor, hybrid_property)
        ]

    @classproperty
    def hybrid_methods_full(cls) -> dict[str, hybrid_method]:
        descriptors = cast(Any, inspect(cls)).all_orm_descriptors
        return {
            descriptor.func.__name__: descriptor
            for descriptor in descriptors
            if type(descriptor) is hybrid_method
        }

    @classproperty
    def hybrid_methods(cls) -> list[str]:
        return list(cls.hybrid_methods_full.keys())

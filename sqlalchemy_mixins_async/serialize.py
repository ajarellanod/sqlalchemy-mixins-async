from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import inspect as sa_inspect

from .inspection import InspectionMixin


class SerializeMixin(InspectionMixin):
    """
    Lightweight serialization helpers for ORM entities.

    The serializer is intentionally conservative for async ORM usage:
    unloaded relationships are skipped by default to avoid implicit I/O.
    For richer API payloads, using this mixin as a source for a Pydantic schema
    is usually a better fit than exposing the raw dictionary directly.
    """

    __abstract__ = True

    def to_dict(
        self,
        *,
        nested: bool = False,
        hybrid_attributes: bool = False,
        exclude: Iterable[str] | None = None,
        include: Iterable[str] | None = None,
        include_relationships: Iterable[str] | None = None,
        only_loaded: bool = True,
        max_depth: int | None = 1,
    ) -> dict[str, Any]:
        """Serialize the instance to a dictionary without forcing implicit async loads."""
        return self._serialize(
            nested=nested,
            hybrid_attributes=hybrid_attributes,
            exclude=set(exclude or []),
            include=set(include) if include is not None else None,
            include_relationships=set(include_relationships)
            if include_relationships is not None
            else None,
            only_loaded=only_loaded,
            max_depth=max_depth,
            seen=set(),
        )

    def to_schema(self, schema_type, **kwargs):
        """
        Serialize the instance and pass the payload into a schema class.

        Supports Pydantic v2 via `model_validate()` and v1 via `parse_obj()`.
        """
        payload = self.to_dict(**kwargs)
        if hasattr(schema_type, "model_validate"):
            return schema_type.model_validate(payload)
        if hasattr(schema_type, "parse_obj"):
            return schema_type.parse_obj(payload)
        raise TypeError("schema_type must expose model_validate() or parse_obj()")

    def _serialize(
        self,
        *,
        nested: bool,
        hybrid_attributes: bool,
        exclude: set[str],
        include: set[str] | None,
        include_relationships: set[str] | None,
        only_loaded: bool,
        max_depth: int | None,
        seen: set[tuple[type, tuple[Any, ...] | None]],
    ) -> dict[str, Any]:
        state = cast(Any, sa_inspect(self))
        unloaded = set(state.unloaded) if only_loaded else set()
        identity_key = (type(self), state.identity)
        result: dict[str, Any] = {}

        if identity_key in seen:
            return result
        seen.add(identity_key)

        columns = [
            column
            for column in self.columns
            if column not in exclude and (include is None or column in include)
        ]
        for key in columns:
            if key in unloaded:
                continue
            result[key] = getattr(self, key)

        if hybrid_attributes:
            for key in self.hybrid_properties:
                if key not in exclude and (include is None or key in include):
                    result[key] = getattr(self, key)

        if nested and (max_depth is None or max_depth > 0):
            remaining_depth = None if max_depth is None else max_depth - 1
            relations = include_relationships or set(self.relations)
            for key in relations:
                if key not in self.relations or key in exclude or key in unloaded:
                    continue
                obj = getattr(self, key)
                if isinstance(obj, SerializeMixin):
                    result[key] = obj._serialize(
                        nested=True,
                        hybrid_attributes=hybrid_attributes,
                        exclude=exclude,
                        include=None,
                        include_relationships=None,
                        only_loaded=only_loaded,
                        max_depth=remaining_depth,
                        seen=seen,
                    )
                elif isinstance(obj, Iterable):
                    result[key] = [
                        item._serialize(
                            nested=True,
                            hybrid_attributes=hybrid_attributes,
                            exclude=exclude,
                            include=None,
                            include_relationships=None,
                            only_loaded=only_loaded,
                            max_depth=remaining_depth,
                            seen=seen,
                        )
                        for item in obj
                        if isinstance(item, SerializeMixin)
                    ]

        seen.remove(identity_key)
        return result

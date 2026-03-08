from __future__ import annotations

from typing import Any, cast

from sqlalchemy import delete as sqlalchemy_delete, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from .error_translators import translate_integrity_error
from .inspection import InspectionMixin
from .session import SessionMixin
from .utils import classproperty


class ModelNotFoundError(ValueError):
    """Raised when a model cannot be found by a lookup helper."""


class ActiveRecordMixin(InspectionMixin, SessionMixin):
    """Async CRUD helpers built on top of `AsyncSession` and `Select`."""

    __abstract__ = True

    @classmethod
    def select_stmt(cls):
        """Return the base `Select` statement for this model."""
        return select(cls)

    @classmethod
    def _get_primary_key_column(cls):
        """Return the single supported primary-key column or raise clearly."""
        primary_keys = list(sa_inspect(cls).primary_key)
        if not primary_keys:
            raise InvalidRequestError(f"Model {cls.__name__} does not have a primary key.")
        if len(primary_keys) > 1:
            raise InvalidRequestError(
                f"Model {cls.__name__} has a composite primary key, which is not supported."
            )
        return primary_keys[0]

    @classproperty
    def settable_attributes(cls) -> list[str]:
        """Attributes accepted by `fill()` and CRUD helpers."""
        return cls.columns + cls.hybrid_properties + cls.settable_relations

    def fill(self, **kwargs):
        """Populate the instance with validated settable attributes."""
        for name, value in kwargs.items():
            if name not in self.settable_attributes:
                raise KeyError(f"Attribute '{name}' doesn't exist")
            setattr(self, name, value)
        return self

    async def _finalize_write(
        self,
        session: AsyncSession | None = None,
        *,
        commit: bool | None = None,
        refresh: bool = True,
        refresh_relationships: list[str] | None = None,
    ):
        """Apply flush/commit policy for a model write and refresh the instance."""
        state = cast(Any, sa_inspect(self))
        if state.session is not None and session is None:
            raise RuntimeError(
                "The instance is already attached to a session. Pass session= explicitly."
            )

        async with self.__class__.session_scope(session) as (active_session, owns_session):
            if state.session is None:
                active_session.add(self)

            should_commit = owns_session if commit is None else commit
            try:
                if should_commit:
                    await active_session.commit()
                else:
                    await active_session.flush()
                if refresh:
                    await active_session.refresh(self, attribute_names=refresh_relationships)
                return self
            except IntegrityError as error:
                await active_session.rollback()
                translated = translate_integrity_error(error)
                if translated is error:
                    raise
                raise translated from error

    async def save(
        self,
        *,
        session: AsyncSession | None = None,
        commit: bool | None = None,
        refresh: bool = True,
        refresh_relationships: list[str] | None = None,
    ):
        """Persist the current instance using the resolved session policy."""
        return await self._finalize_write(
            session=session,
            commit=commit,
            refresh=refresh,
            refresh_relationships=refresh_relationships,
        )

    @classmethod
    async def create(
        cls,
        *,
        session: AsyncSession | None = None,
        commit: bool | None = None,
        refresh: bool = True,
        refresh_relationships: list[str] | None = None,
        **kwargs,
    ):
        """Create, persist, and optionally refresh a new model instance."""
        instance = cls().fill(**kwargs)
        return await instance.save(
            session=session,
            commit=commit,
            refresh=refresh,
            refresh_relationships=refresh_relationships,
        )

    async def update(
        self,
        *,
        session: AsyncSession | None = None,
        commit: bool | None = None,
        refresh: bool = True,
        refresh_relationships: list[str] | None = None,
        **kwargs,
    ):
        """Apply updates to the instance and persist them."""
        self.fill(**kwargs)
        return await self.save(
            session=session,
            commit=commit,
            refresh=refresh,
            refresh_relationships=refresh_relationships,
        )

    async def delete(self, *, session: AsyncSession | None = None, commit: bool | None = None) -> None:
        """Delete the current instance using the resolved session policy."""
        async with self.__class__.session_scope(session) as (active_session, owns_session):
            should_commit = owns_session if commit is None else commit
            state = cast(Any, sa_inspect(self))
            if state.session is None:
                attached = await active_session.merge(self)
            else:
                attached = self
            try:
                await active_session.delete(attached)
                if should_commit:
                    await active_session.commit()
                else:
                    await active_session.flush()
            except IntegrityError as error:
                await active_session.rollback()
                translated = translate_integrity_error(error)
                if translated is error:
                    raise
                raise translated from error

    @classmethod
    async def destroy(
        cls, *ids: Any, session: AsyncSession | None = None, commit: bool | None = None
    ) -> None:
        """Bulk-delete by primary key values."""
        primary_key = cls._get_primary_key_column()
        stmt = sqlalchemy_delete(cls).where(primary_key.in_(ids))
        async with cls.session_scope(session) as (active_session, owns_session):
            should_commit = owns_session if commit is None else commit
            try:
                await active_session.execute(stmt)
                if should_commit:
                    await active_session.commit()
                else:
                    await active_session.flush()
            except IntegrityError as error:
                await active_session.rollback()
                translated = translate_integrity_error(error)
                if translated is error:
                    raise
                raise translated from error

    @classmethod
    async def all(cls, *, session: AsyncSession | None = None, stmt=None) -> list:
        """Load all rows for the model or for a provided statement."""
        resolved_stmt = cls.select_stmt() if stmt is None else stmt
        scalars = await cls.scalars(resolved_stmt, session=session)
        return list(scalars.unique().all())

    @classmethod
    async def first(cls, *, session: AsyncSession | None = None, stmt=None):
        """Load the first row for the model or for a provided statement."""
        resolved_stmt = cls.select_stmt() if stmt is None else stmt
        scalars = await cls.scalars(resolved_stmt, session=session)
        return scalars.first()

    @classmethod
    async def find(cls, id_, *, session: AsyncSession | None = None):
        """Load one row by primary key."""
        cls._get_primary_key_column()
        async with cls.session_scope(session) as (active_session, _):
            return await active_session.get(cls, id_)

    @classmethod
    async def find_or_fail(cls, id_, *, session: AsyncSession | None = None):
        """Load one row by primary key or raise `ModelNotFoundError`."""
        result = await cls.find(id_, session=session)
        if result is None:
            raise ModelNotFoundError(f"{cls.__name__} with id '{id_}' was not found")
        return result

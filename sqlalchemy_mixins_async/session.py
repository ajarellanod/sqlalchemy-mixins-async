from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .utils import classproperty


class NoSessionError(RuntimeError):
    pass


class SessionMixin:
    """Async session utilities shared by the higher-level mixins."""

    __abstract__ = True
    _sessionmaker: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def set_sessionmaker(cls, sessionmaker: async_sessionmaker[AsyncSession] | None) -> None:
        """Bind or clear the default async sessionmaker for this model hierarchy."""
        cls._sessionmaker = sessionmaker

    @classproperty
    def sessionmaker(cls) -> async_sessionmaker[AsyncSession]:
        """Return the configured sessionmaker or raise if the model is unbound."""
        if cls._sessionmaker is None:
            raise NoSessionError(
                "No async sessionmaker configured. Call set_sessionmaker() first."
            )
        return cls._sessionmaker

    @classmethod
    @asynccontextmanager
    async def session_scope(
        cls, session: AsyncSession | None = None
    ) -> AsyncIterator[tuple[AsyncSession, bool]]:
        """
        Yield an active session and whether this mixin owns it.

        When `session` is passed the caller owns transaction boundaries.
        Otherwise a new session is created from the bound sessionmaker.
        """
        if session is not None:
            yield session, False
            return

        async with cls.sessionmaker() as managed_session:
            yield managed_session, True

    @classmethod
    async def execute(cls, stmt, *, session: AsyncSession | None = None):
        """Execute a statement inside the resolved async session."""
        async with cls.session_scope(session) as (active_session, _):
            return await active_session.execute(stmt)

    @classmethod
    async def scalars(cls, stmt, *, session: AsyncSession | None = None):
        """Execute a statement and return the scalar stream."""
        async with cls.session_scope(session) as (active_session, _):
            return await active_session.scalars(stmt)

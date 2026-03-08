from __future__ import annotations

import unittest

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool
from testcontainers.core.container import Reaper

from sqlalchemy_mixins_async import ActiveRecordMixin, AlreadyExistsError, QueryMixin


def postgres_container():
    from testcontainers.postgres import PostgresContainer

    return PostgresContainer("postgres:16", driver="asyncpg")


def mysql_container():
    from testcontainers.mysql import MySqlContainer

    return MySqlContainer("mysql:8.0", dialect="aiomysql")


def build_backend_test(container_factory, expect_translated_error: bool):
    class BackendIntegrationTest(unittest.IsolatedAsyncioTestCase):
        container_context = None
        database_url: str | None = None
        unavailable_reason: str | None = None

        @classmethod
        def setUpClass(cls):
            super().setUpClass()
            try:
                cls.container_context = container_factory()
                container = cls.container_context.__enter__()
                cls.database_url = container.get_connection_url()
            except Exception as error:  # pragma: no cover - environment dependent
                cls.unavailable_reason = f"{container_factory.__name__} unavailable: {error}"

        @classmethod
        def tearDownClass(cls):
            if cls.container_context is not None:
                cls.container_context.__exit__(None, None, None)
            Reaper.delete_instance()
            super().tearDownClass()

        async def asyncSetUp(self):
            if self.__class__.unavailable_reason:
                self.skipTest(self.__class__.unavailable_reason)

            self.engine = create_async_engine(self.__class__.database_url, poolclass=NullPool)
            self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

            class Base(AsyncAttrs, DeclarativeBase):
                pass

            class BaseModel(Base, ActiveRecordMixin, QueryMixin):
                __abstract__ = True

            class Account(BaseModel):
                __tablename__ = "accounts"

                id: Mapped[int] = mapped_column(primary_key=True)
                email: Mapped[str] = mapped_column(String(255), unique=True)

            self.Base = Base
            self.BaseModel = BaseModel
            self.Account = Account
            self.BaseModel.set_sessionmaker(self.sessionmaker)

            async with self.engine.begin() as conn:
                await conn.run_sync(self.Base.metadata.drop_all)
                await conn.run_sync(self.Base.metadata.create_all)

        async def asyncTearDown(self):
            self.BaseModel.set_sessionmaker(None)
            await self.engine.dispose()

        async def test_crud_roundtrip(self):
            account = await self.Account.create(email="a@example.com")
            loaded = await self.Account.find(account.id)
            self.assertEqual(loaded.email, "a@example.com")

        async def test_unique_constraint_behavior(self):
            await self.Account.create(email="dup@example.com")
            if expect_translated_error:
                with self.assertRaises(AlreadyExistsError):
                    await self.Account.create(email="dup@example.com")
            else:
                with self.assertRaises(Exception):
                    await self.Account.create(email="dup@example.com")

    return BackendIntegrationTest


TestAsyncpgIntegration = build_backend_test(postgres_container, expect_translated_error=True)

TestAiomysqlIntegration = build_backend_test(mysql_container, expect_translated_error=False)

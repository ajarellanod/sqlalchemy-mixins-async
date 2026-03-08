from __future__ import annotations

import sqlite3
import unittest

from asyncpg.exceptions import ForeignKeyViolationError, UniqueViolationError
from sqlalchemy import ForeignKey, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy_mixins_async import (
    ActiveRecordMixin,
    AlreadyExistsError,
    MissingReferenceError,
    QueryMixin,
    SerializeMixin,
)
from sqlalchemy_mixins_async.error_translators import translate_integrity_error


class Base(AsyncAttrs, DeclarativeBase):
    pass


class BaseModel(Base, ActiveRecordMixin, QueryMixin, SerializeMixin):
    __abstract__ = True


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    posts: Mapped[list["Post"]] = relationship(back_populates="user", lazy="selectin")


class Post(BaseModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(back_populates="posts", lazy="selectin")


class DummySchema:
    @classmethod
    def model_validate(cls, payload):
        return {"schema": cls.__name__, "payload": payload}


class TestSerializeAndErrors(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        BaseModel.set_sessionmaker(self.sessionmaker)

        self.user = await User.create(name="Bill")
        self.post = await Post.create(body="hello", user_id=self.user.id)

    async def asyncTearDown(self):
        BaseModel.set_sessionmaker(None)
        await self.engine.dispose()

    async def test_to_dict_skips_unloaded_relationships_by_default(self):
        async with self.sessionmaker() as session:
            post = await Post.find(self.post.id, session=session)
            session.expire(post, ["user"])
            payload = post.to_dict(nested=True)
            self.assertNotIn("user", payload)

    async def test_to_schema_uses_schema_adapter(self):
        payload = self.user.to_schema(DummySchema)
        self.assertEqual(payload["schema"], "DummySchema")
        self.assertEqual(payload["payload"]["name"], "Bill")

    async def test_integrity_error_translation(self):
        unique_error = IntegrityError("stmt", {}, Exception("outer"))
        unique_error.orig.__cause__ = UniqueViolationError("duplicate")
        translated = translate_integrity_error(unique_error)
        self.assertIsInstance(translated, AlreadyExistsError)

        fk_error = IntegrityError("stmt", {}, Exception("outer"))
        fk_error.orig.__cause__ = ForeignKeyViolationError("missing")
        translated = translate_integrity_error(fk_error)
        self.assertIsInstance(translated, MissingReferenceError)

    async def test_sqlite_integrity_error_translation(self):
        unique_error = IntegrityError(
            "stmt", {}, sqlite3.IntegrityError("UNIQUE constraint failed: users.name")
        )
        translated = translate_integrity_error(unique_error)
        self.assertIsInstance(translated, AlreadyExistsError)

        fk_error = IntegrityError(
            "stmt", {}, sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        )
        translated = translate_integrity_error(fk_error)
        self.assertIsInstance(translated, MissingReferenceError)

    async def test_mysql_integrity_error_translation_with_test_double(self):
        class FakeMySQLIntegrityError(Exception):
            pass

        from sqlalchemy_mixins_async.error_translators import (
            aiomysql as mysql_translator,
        )

        original_error_cls = mysql_translator.MySQLIntegrityError
        original_er = mysql_translator.ER
        try:

            class FakeER:
                DUP_ENTRY = 1062
                NO_REFERENCED_ROW_2 = 1452
                ROW_IS_REFERENCED_2 = 1451

            mysql_translator.MySQLIntegrityError = FakeMySQLIntegrityError
            mysql_translator.ER = FakeER

            unique_error = IntegrityError(
                "stmt", {}, FakeMySQLIntegrityError(1062, "Duplicate entry")
            )
            translated = translate_integrity_error(unique_error)
            self.assertIsInstance(translated, AlreadyExistsError)

            fk_error = IntegrityError(
                "stmt", {}, FakeMySQLIntegrityError(1452, "Cannot add child row")
            )
            translated = translate_integrity_error(fk_error)
            self.assertIsInstance(translated, MissingReferenceError)
        finally:
            mysql_translator.MySQLIntegrityError = original_error_cls
            mysql_translator.ER = original_er

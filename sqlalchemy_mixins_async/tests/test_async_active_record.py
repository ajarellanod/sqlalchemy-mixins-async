from __future__ import annotations

import unittest

from sqlalchemy import ForeignKey, String, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy_mixins_async import (
    ActiveRecordMixin,
    ModelNotFoundError,
    NoSessionError,
    QueryMixin,
)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class BaseModel(Base, ActiveRecordMixin, QueryMixin):
    __abstract__ = True


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    posts: Mapped[list["Post"]] = relationship(back_populates="user", lazy="selectin")


class Post(BaseModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(String(200))
    archived: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(back_populates="posts", lazy="selectin")

    @hybrid_property
    def public(self) -> bool:
        return not self.archived

    @public.setter
    def public(self, value: bool) -> None:
        self.archived = not value

    @public.expression
    def public(cls):
        return ~cls.archived

    @hybrid_method
    def has_user_name(self, value: str, mapper=None):
        mapper = mapper or self.__class__
        return mapper.user.has(User.name == value)


class Composite(BaseModel):
    __tablename__ = "composites"

    left_id: Mapped[int] = mapped_column(primary_key=True)
    right_id: Mapped[int] = mapped_column(primary_key=True)


class TestAsyncActiveRecord(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        BaseModel.set_sessionmaker(self.sessionmaker)

    async def asyncTearDown(self):
        BaseModel.set_sessionmaker(None)
        await self.engine.dispose()

    async def test_requires_async_sessionmaker(self):
        BaseModel.set_sessionmaker(None)
        with self.assertRaises(NoSessionError):
            _ = BaseModel.sessionmaker

    async def test_create_find_update_delete_with_internal_session(self):
        user = await User.create(name="Bill")
        self.assertIsNotNone(user.id)

        found = await User.find(user.id)
        self.assertEqual(found.name, "Bill")

        await found.update(name="Billy")
        updated = await User.find(user.id)
        self.assertEqual(updated.name, "Billy")

        await updated.delete()
        self.assertIsNone(await User.find(user.id))

    async def test_external_session_flushes_by_default(self):
        async with self.sessionmaker() as session:
            async with session.begin():
                user = await User.create(session=session, name="Ana")
                self.assertIsNotNone(user.id)

                fetched = await User.find(user.id, session=session)
                self.assertEqual(fetched.name, "Ana")

                await fetched.update(session=session, name="Anita")
                self.assertEqual(
                    (await User.find(user.id, session=session)).name, "Anita"
                )

        persisted = await User.find(user.id)
        self.assertEqual(persisted.name, "Anita")

    async def test_find_or_fail_and_fill_validation(self):
        user = User()
        with self.assertRaises(KeyError):
            user.fill(unknown="value")

        with self.assertRaises(ModelNotFoundError):
            await User.find_or_fail(999)

    async def test_composite_primary_key_is_not_supported(self):
        with self.assertRaises(InvalidRequestError):
            await Composite.find((1, 2))

    async def test_session_bound_instance_requires_explicit_session(self):
        async with self.sessionmaker() as session:
            async with session.begin():
                user = User(name="Bound")
                session.add(user)
                await session.flush()
                with self.assertRaises(RuntimeError):
                    await user.save()

    async def test_select_helpers_accept_custom_statement(self):
        await User.create(name="Bill")
        await User.create(name="Bianca")
        stmt = select(User).where(User.name.like("Bi%")).order_by(User.name)
        users = await User.all(stmt=stmt)
        self.assertEqual([user.name for user in users], ["Bianca", "Bill"])

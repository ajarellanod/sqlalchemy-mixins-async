from __future__ import annotations

import unittest

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy_mixins_async import (
    JOINED,
    SELECTIN,
    ActiveRecordMixin,
    QueryMixin,
    apply_query,
    or_,
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
    comments: Mapped[list["Comment"]] = relationship(back_populates="post", lazy="selectin")

    @hybrid_property
    def public(self) -> bool:
        return not self.archived

    @public.expression
    def public(cls):
        return ~cls.archived

    @hybrid_method
    def is_public(self, value: bool, mapper=None):
        mapper = mapper or self.__class__
        return mapper.public == value


class Comment(BaseModel):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(String(200))
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))

    post: Mapped[Post] = relationship(back_populates="comments", lazy="selectin")


class TestAsyncQuery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        BaseModel.set_sessionmaker(self.sessionmaker)

        self.bill = await User.create(name="Bill")
        self.bianca = await User.create(name="Bianca")
        self.p1 = await Post.create(body="keep me", user_id=self.bill.id, archived=False)
        self.p2 = await Post.create(body="archive me", user_id=self.bill.id, archived=True)
        self.p3 = await Post.create(body="bianca post", user_id=self.bianca.id, archived=False)
        await Comment.create(body="first", post_id=self.p1.id)
        await Comment.create(body="second", post_id=self.p3.id)

    async def asyncTearDown(self):
        BaseModel.set_sessionmaker(None)
        await self.engine.dispose()

    async def test_where_and_sort_return_select_statements(self):
        stmt = Post.where(user___name__like="Bia%", public=True)
        self.assertIsInstance(stmt, sa.Select)

        results = await Post.all(stmt=stmt)
        self.assertEqual([post.id for post in results], [self.p3.id])

        ordered = await Post.all(stmt=Post.order_by("user___name", "-id"))
        self.assertEqual([post.id for post in ordered], [self.p3.id, self.p2.id, self.p1.id])

    async def test_query_supports_nested_filter_groups(self):
        stmt = Post.query(
            where=or_(
                {"user___name": "Bianca"},
                {"body__contains": "keep"},
            ),
            order_by=("id",),
        )
        results = await Post.all(stmt=stmt)
        self.assertEqual([post.id for post in results], [self.p1.id, self.p3.id])

    async def test_apply_query_accepts_existing_select(self):
        base_stmt = select(Post)
        stmt = apply_query(base_stmt, model=Post, where={"comments___body__contains": "first"})
        results = await Post.all(stmt=stmt)
        self.assertEqual([post.id for post in results], [self.p1.id])

    async def test_query_accepts_load_parameter(self):
        stmt = User.query(load={User.posts: SELECTIN})
        users = await User.all(stmt=stmt)
        loaded = next(user for user in users if user.id == self.bill.id)
        self.assertEqual(len(loaded.posts), 2)

    async def test_loader_helpers_return_select(self):
        joined_stmt = Post.with_joined(Post.user)
        selectin_stmt = User.with_({User.posts: {Post.comments: JOINED}})
        self.assertIsInstance(joined_stmt, sa.Select)
        self.assertIsInstance(selectin_stmt, sa.Select)

        users = await User.all(stmt=User.with_({User.posts: {Post.comments: SELECTIN}}))
        loaded = next(user for user in users if user.id == self.bill.id)
        self.assertEqual(len(loaded.posts), 2)
        self.assertEqual(loaded.posts[0].comments[0].body, "first")

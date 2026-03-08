from __future__ import annotations

import unittest

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy_mixins_async import (
    AllFeaturesMixin,
    FastAPIMixin,
    SUBQUERY,
    TimestampsMixin,
    and_,
    apply_query,
    eager_expr,
)
from sqlalchemy_mixins_async.utils import get_relations, path_to_relations_list


class Base(AsyncAttrs, DeclarativeBase):
    pass


class BaseModel(Base, AllFeaturesMixin, TimestampsMixin):
    __abstract__ = True


class User(BaseModel):
    __tablename__ = "users"
    __repr_attrs__ = ["name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    posts: Mapped[list["Post"]] = relationship(back_populates="user", lazy="selectin")


class Post(BaseModel):
    __tablename__ = "posts"
    __repr_attrs__ = ["title"]
    __repr_max_length__ = 5

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(String(200))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship(back_populates="posts", lazy="selectin")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post", lazy="selectin")

    @hybrid_property
    def preview(self) -> str:
        return self.body[:10]

    @hybrid_method
    def has_title(self, value: str, mapper=None):
        mapper = mapper or self.__class__
        return mapper.title == value


class Comment(BaseModel):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(String(100))
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    post: Mapped[Post] = relationship(back_populates="comments", lazy="selectin")


class ApiBaseModel(Base, FastAPIMixin):
    __abstract__ = True


class DummySchemaV1:
    @classmethod
    def parse_obj(cls, payload):
        return {"schema": cls.__name__, "payload": payload}


class TestAdditionalFeatures(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        BaseModel.set_sessionmaker(self.sessionmaker)
        ApiBaseModel.set_sessionmaker(self.sessionmaker)

    async def asyncTearDown(self):
        BaseModel.set_sessionmaker(None)
        ApiBaseModel.set_sessionmaker(None)
        await self.engine.dispose()

    async def test_compat_exports_and_relationship_assignment(self):
        self.assertIn("id", User.columns)
        self.assertIn("created_at", User.columns)
        self.assertIn("updated_at", User.columns)
        self.assertIn("name", User.columns)
        self.assertEqual(User.primary_keys, ["id"])
        self.assertCountEqual(Post.relations, ["user", "comments"])
        self.assertCountEqual(Post.settable_relations, ["user", "comments"])
        self.assertIn("preview", Post.hybrid_properties)
        self.assertIn("user", Post.settable_attributes)

        user = await User.create(name="Bill")
        post = await Post.create(title="Hello", body="Relationship create", user=user)

        loaded = await Post.find(post.id)
        self.assertEqual(loaded.user_id, user.id)

    async def test_execute_scalars_destroy_and_repr(self):
        user = await User.create(name="Bill")
        post = await Post.create(title="Long title", body="Body text", user=user)

        result = await Post.execute(select(Post).where(Post.id == post.id))
        self.assertEqual(result.scalar_one().id, post.id)

        scalars = await Post.scalars(Post.order_by("id"))
        self.assertEqual([row.id for row in scalars.all()], [post.id])

        self.assertEqual(repr(post), "<Post #1 'Long ...'>")

        await Post.destroy(post.id)
        self.assertIsNone(await Post.find(post.id))

    async def test_serialization_timestamps_and_schema_adapter(self):
        user = await User.create(name="Bill")
        post = await Post.create(title="Hello", body="This body is serialized", user=user)
        await Comment.create(body="first", post=post)

        loaded = await Post.first(stmt=Post.with_({Post.user: SUBQUERY, Post.comments: SUBQUERY}))
        payload = loaded.to_dict(
            nested=True,
            hybrid_attributes=True,
            include_relationships=["user", "comments"],
        )

        self.assertEqual(payload["preview"], "This body ")
        self.assertEqual(payload["user"]["name"], "Bill")
        self.assertEqual(payload["comments"][0]["body"], "first")
        self.assertIsNotNone(loaded.created_at)
        self.assertIsNotNone(loaded.updated_at)

        schema_payload = loaded.to_schema(DummySchemaV1, include=["title"])
        self.assertEqual(schema_payload["payload"], {"title": "Hello"})

        with self.assertRaises(TypeError):
            loaded.to_schema(object)

    async def test_eager_expr_validation_and_fastapi_mixin_repr(self):
        stmt = User.with_subquery(User.posts)
        self.assertIsInstance(stmt, sa.Select)
        self.assertEqual(len(eager_expr({User.posts: SUBQUERY})), 1)
        self.assertIsInstance(User.with_selectin(User.posts), sa.Select)
        self.assertIsInstance(
            User.with_({User.posts: (SUBQUERY, {Post.comments: SUBQUERY})}),
            sa.Select,
        )

        with self.assertRaises(ValueError):
            eager_expr({User.posts: "bad"})

        class Ping(ApiBaseModel):
            __tablename__ = "pings"
            __repr_attrs__ = ["label"]

            id: Mapped[int] = mapped_column(primary_key=True)
            label: Mapped[str] = mapped_column(String(50))

        async with self.engine.begin() as conn:
            await conn.run_sync(Ping.metadata.create_all)

        ping = await Ping.create(label="ok")
        self.assertEqual(repr(ping), "<Ping #1 'ok'>")

    async def test_query_helpers_and_utils_cover_error_paths(self):
        self.assertEqual([rel.key for rel in get_relations(User)], ["posts"])
        self.assertEqual(
            [rel.key for rel in path_to_relations_list(User, "posts.comments")],
            ["posts", "comments"],
        )
        self.assertEqual(len(and_({"title": "Hello"})), 1)

        user = await User.create(name="Bill")
        await Post.create(title="Hello", body="This body is serialized", user=user)

        self.assertEqual(len(Post.filter_expr(has_title="Hello")), 1)

        with self.assertRaises(ValueError):
            apply_query(select(sa.literal(1)))

        with self.assertRaises(TypeError):
            apply_query(select(Post), model=Post, where=1)

        with self.assertRaises(KeyError):
            Post.filter_expr(title__bad="Hello")

        with self.assertRaises(KeyError):
            Post.filter_expr(unknown="Hello")

        with self.assertRaises(KeyError):
            Post.order_expr(None, "unknown")

    async def test_default_select_helpers_delete_flush_and_repr_validation(self):
        user = await User.create(name="Bill")
        post = await Post.create(title="Hello", body="This body is serialized", user=user)

        self.assertEqual((await Post.first()).id, post.id)
        self.assertEqual((await Post.find_or_fail(post.id)).id, post.id)

        async with self.sessionmaker() as session:
            async with session.begin():
                attached = await Post.find(post.id, session=session)
                await attached.delete(session=session, commit=False)
                self.assertIsNone(await Post.find(post.id, session=session))

        self.assertIsNone(await Post.find(post.id))

        unsaved = Post(title="Hello", body="This body is serialized", user=user)
        self.assertEqual(unsaved._id_str, "None")
        unsaved.__repr_attrs__ = ["missing"]
        with self.assertRaises(KeyError):
            repr(unsaved)

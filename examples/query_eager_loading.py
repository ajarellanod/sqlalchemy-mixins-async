from __future__ import annotations

import asyncio

from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy_mixins_async import ActiveRecordMixin, QueryMixin, SELECTIN, or_


class Base(AsyncAttrs, DeclarativeBase):
    pass


class BaseModel(Base, ActiveRecordMixin, QueryMixin):
    __abstract__ = True


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship(back_populates="user", lazy="selectin")


class Post(BaseModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str]
    archived: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship(back_populates="posts", lazy="selectin")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post", lazy="selectin")


class Comment(BaseModel):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str]
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    post: Mapped[Post] = relationship(back_populates="comments", lazy="selectin")


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    BaseModel.set_sessionmaker(sessionmaker)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bill = await User.create(name="Bill")
    bianca = await User.create(name="Bianca")
    bill_post = await Post.create(body="keep me", user=bill)
    await Post.create(body="archive me", user=bill, archived=True)
    bianca_post = await Post.create(body="ship it", user=bianca)
    await Comment.create(body="first", post=bill_post)
    await Comment.create(body="second", post=bianca_post)

    stmt = Post.query(
        where=or_({"user___name": "Bianca"}, {"comments___body__contains": "first"}),
        order_by=("user___name", "-id"),
    )
    rows = await Post.all(stmt=stmt)

    for post in rows:
        print(post.body, post.user.name, [comment.body for comment in post.comments])

    eager_users = await User.all(stmt=User.with_({User.posts: SELECTIN}))
    for user in eager_users:
        print(user.name, [post.body for post in user.posts])

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

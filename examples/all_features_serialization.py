from __future__ import annotations

import asyncio

from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy_mixins_async import AllFeaturesMixin, TimestampsMixin


class Base(AsyncAttrs, DeclarativeBase):
    pass


class BaseModel(Base, AllFeaturesMixin, TimestampsMixin):
    __abstract__ = True
    __repr_attrs__ = ["title"]


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(default="unused")
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship(back_populates="user", lazy="selectin")


class Post(BaseModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship(back_populates="posts", lazy="selectin")

    @hybrid_property
    def preview(self) -> str:
        return self.body[:20]


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    BaseModel.set_sessionmaker(sessionmaker)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user = await User.create(name="Bill", title="author")
    post = await Post.create(
        title="Hello",
        body="This body is longer than the preview.",
        user=user,
    )
    loaded = await Post.first(stmt=Post.with_selectin(Post.user))

    print(repr(post))
    print(loaded.to_dict(nested=True, hybrid_attributes=True))
    print(post.created_at, post.updated_at)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

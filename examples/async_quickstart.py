from __future__ import annotations

import asyncio

from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy_mixins_async import ActiveRecordMixin, QueryMixin


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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship(back_populates="posts", lazy="selectin")


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    BaseModel.set_sessionmaker(sessionmaker)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user = await User.create(name="Bill")
    await Post.create(body="hello", user=user)

    stmt = Post.where(user___name="Bill")
    rows = await Post.all(stmt=stmt)
    print(rows)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

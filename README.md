# sqlalchemy-mixins-async

`sqlalchemy-mixins-async` is the async-only SQLAlchemy 2.x variant, published under a separate package name so it can coexist with the older `sqlalchemy-mixins` project.

## What changed in v3

- `AsyncSession` / `async_sessionmaker` only
- `select()`-first query building
- async CRUD helpers on models
- Django-like filter and sort DSL preserved on top of `Select`
- `selectinload` is the default eager-loading recommendation

Sync `Session.query()` patterns and sync tests/examples were removed.

## Installation

```bash
uv add sqlalchemy-mixins-async
```

Built-in test coverage uses `sqlite+aiosqlite`. PostgreSQL and MySQL drivers are optional:

```bash
uv add 'sqlalchemy-mixins-async[asyncpg]'
uv add 'sqlalchemy-mixins-async[aiomysql]'
uv add 'sqlalchemy-mixins-async[all]'
```

## Quick start

```python
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


engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/app")
Session = async_sessionmaker(engine, expire_on_commit=False)
BaseModel.set_sessionmaker(Session)

user = await User.create(name="Bill")
post = await Post.create(body="hello", user_id=user.id)

stmt = Post.query(where={"user___name": "Bill"})
rows = await Post.all(stmt=stmt)
```

## Supported async engines

- PostgreSQL: `postgresql+asyncpg://user:pass@host/db`
- SQLite: `sqlite+aiosqlite:///path/to.db`
- MySQL/MariaDB: `mysql+aiomysql://user:pass@host/db`

Notes:

- `asyncpg` gets first-class integrity error translation into library exceptions such as `AlreadyExistsError`.
- `aiosqlite` is the default lightweight backend used by the unit tests.
- `aiomysql` is supported through SQLAlchemy's async MySQL dialect. On MySQL-family backends, server-side `RETURNING` behavior is more limited than PostgreSQL, so `expire_on_commit=False` and explicit refreshes remain the recommended pattern.

## Main API

- `set_sessionmaker(async_sessionmaker)`
- `await Model.create(...)`
- `await instance.save()`
- `await instance.update(...)`
- `await instance.delete()`
- `await Model.find(id)`
- `await Model.find_or_fail(id)`
- `await Model.all(stmt=...)`
- `Model.query(where=..., order_by=..., load=...) -> Select`
- `Model.where(...) -> Select`
- `Model.order_by(...) -> Select`
- `Model.with_(schema) -> Select`
- `apply_query(stmt, where=..., order_by=..., load=...) -> Select`
- `await Model.execute(stmt)`
- `await Model.scalars(stmt)`

## Testing

```bash
uv sync --group dev
uv run python -m unittest discover sqlalchemy_mixins_async/tests
```

The backend integration tests use `testcontainers-python` to start PostgreSQL and MySQL automatically.
They run when Docker is available and skip cleanly when the daemon or container dependencies are missing.

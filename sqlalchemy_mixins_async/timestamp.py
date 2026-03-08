from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampsMixin:
    """Mixin that define timestamp columns."""

    __abstract__ = True

    __created_at_name__ = 'created_at'
    __updated_at_name__ = 'updated_at'
    __datetime_func__ = func.now()

    created_at: Mapped[dt.datetime] = mapped_column(
        __created_at_name__, DateTime(timezone=False), default=__datetime_func__, nullable=False
    )

    updated_at: Mapped[dt.datetime] = mapped_column(
        __updated_at_name__,
        DateTime(timezone=False),
        default=__datetime_func__,
        onupdate=__datetime_func__,
        nullable=False,
    )

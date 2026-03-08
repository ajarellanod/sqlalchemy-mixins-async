from __future__ import annotations

from collections.abc import Iterator


def iter_error_chain(error) -> Iterator[BaseException]:
    current = getattr(error, "orig", None)
    while current is not None:
        yield current
        current = getattr(current, "__cause__", None)

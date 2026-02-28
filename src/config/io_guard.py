"""Runtime IO guard helpers.

Goal:
- keep disk IO in config layer
- warn if config disk IO happens during battle hot paths

Implementation notes:
- Uses thread-local state (each device runs in its own worker thread)
- Guard is best-effort; it does not intercept arbitrary `open()` calls
"""

from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Iterator


_tls = threading.local()


def is_in_battle() -> bool:
    return bool(getattr(_tls, "in_battle", False))


def set_in_battle(value: bool) -> None:
    setattr(_tls, "in_battle", bool(value))


@contextmanager
def battle_io_guard() -> Iterator[None]:
    """Mark current thread as running battle hot path."""

    prev = is_in_battle()
    set_in_battle(True)
    try:
        yield
    finally:
        set_in_battle(prev)

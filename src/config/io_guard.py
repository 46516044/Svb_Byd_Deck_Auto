"""运行时 IO 防护辅助函数。

目标是把磁盘 IO 限制在配置层，并在对战热路径中发生配置读写时给出警告。
每台设备运行在独立工作线程中，因此这里使用线程局部状态；该防护仅作尽力检查，
不会拦截任意位置直接调用的 ``open()``。
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
    """标记当前线程正处于对战热路径。"""

    prev = is_in_battle()
    set_in_battle(True)
    try:
        yield
    finally:
        set_in_battle(prev)

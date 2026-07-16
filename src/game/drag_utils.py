"""游戏动作共用的拖拽辅助函数。"""

from __future__ import annotations

import random
from typing import Any, Optional, Protocol

from src.config import settings


class _SwipeDevice(Protocol):
    def swipe(self, *args: Any, **kwargs: Any) -> Any: ...


def human_like_drag(
    u2_device: _SwipeDevice,
    x1: Any,
    y1: Any,
    x2: Any,
    y2: Any,
    duration: Optional[float] = None,
) -> None:
    """执行带轻微抖动的稳定滑动，以模拟人工拖拽。"""

    screen_width = 1280
    screen_height = 720

    def clamp(val: Any, minv: float, maxv: float) -> float:
        try:
            parsed = float(val)
        except Exception:
            parsed = minv
        return max(minv, min(maxv, parsed))

    sx = clamp(x1, 0, screen_width) + random.randint(-2, 2)
    sy = clamp(y1, 0, screen_height) + random.randint(-2, 2)
    ex = clamp(x2, 0, screen_width) + random.randint(-2, 2)
    ey = clamp(y2, 0, screen_height) + random.randint(-2, 2)

    sx = clamp(sx, 0, screen_width)
    sy = clamp(sy, 0, screen_height)
    ex = clamp(ex, 0, screen_width)
    ey = clamp(ey, 0, screen_height)

    if duration is None:
        drag_duration = random.uniform(*settings.get_human_like_drag_duration_range())
    else:
        try:
            drag_duration = float(duration)
        except Exception:
            drag_duration = 0.02
        drag_duration = max(0.05, min(1.0, drag_duration))

    u2_device.swipe(sx, sy, ex, ey, drag_duration)

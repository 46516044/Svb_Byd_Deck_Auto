"""PyQt 控制中心的自定义背景辅助组件。"""

from __future__ import annotations

import os
from typing import Optional

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget

from src.config.paths import get_app_root


BACKGROUND_OPACITY_MIN = 5
BACKGROUND_OPACITY_MAX = 45
BACKGROUND_OPACITY_DEFAULT = 22
BACKGROUND_BASE_COLOR = QColor("#1e1e2e")


def clamp_background_opacity(value: object) -> int:
    try:
        opacity = int(value)
    except (TypeError, ValueError):
        opacity = BACKGROUND_OPACITY_DEFAULT
    return max(BACKGROUND_OPACITY_MIN, min(BACKGROUND_OPACITY_MAX, opacity))


def resolve_background_path(path: object, app_root: Optional[str] = None) -> str:
    raw = os.path.expandvars(os.path.expanduser(str(path or "").strip()))
    if not raw:
        return ""
    if not os.path.isabs(raw):
        raw = os.path.join(os.path.abspath(app_root or get_app_root()), raw)
    return os.path.abspath(os.path.normpath(raw))


def serialize_background_path(path: object, app_root: Optional[str] = None) -> str:
    absolute = resolve_background_path(path, app_root)
    if not absolute:
        return ""

    root = os.path.abspath(app_root or get_app_root())
    try:
        relative = os.path.relpath(absolute, root)
    except ValueError:
        return absolute
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return absolute
    return relative.replace(os.sep, "/")


def _draw_cover(
    painter: QPainter,
    pixmap: QPixmap,
    rect: QRect,
    opacity_percent: int,
) -> None:
    if pixmap.isNull() or rect.isEmpty():
        return
    scaled = pixmap.scaled(
        rect.size(),
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation,
    )
    x = rect.x() + (rect.width() - scaled.width()) // 2
    y = rect.y() + (rect.height() - scaled.height()) // 2
    painter.save()
    painter.setOpacity(clamp_background_opacity(opacity_percent) / 100.0)
    painter.drawPixmap(x, y, scaled)
    painter.restore()


def render_background_preview(
    path: object,
    size: QSize,
    opacity_percent: object,
) -> QPixmap:
    preview = QPixmap(size)
    preview.fill(BACKGROUND_BASE_COLOR)
    image = QPixmap(resolve_background_path(path))
    if image.isNull():
        return preview
    painter = QPainter(preview)
    _draw_cover(
        painter,
        image,
        QRect(0, 0, size.width(), size.height()),
        clamp_background_opacity(opacity_percent),
    )
    painter.end()
    return preview


class BackgroundWidget(QWidget):
    """在页面栈后方绘制可选图片的应用根组件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AppRoot")
        self._background_path = ""
        self._background_opacity = BACKGROUND_OPACITY_DEFAULT
        self._background_pixmap = QPixmap()

    @property
    def background_path(self) -> str:
        return self._background_path

    @property
    def background_opacity(self) -> int:
        return self._background_opacity

    def has_background(self) -> bool:
        return not self._background_pixmap.isNull()

    def set_background(
        self,
        *,
        enabled: bool,
        path: object,
        opacity: object = BACKGROUND_OPACITY_DEFAULT,
    ) -> bool:
        self._background_path = resolve_background_path(path)
        self._background_opacity = clamp_background_opacity(opacity)
        loaded = QPixmap(self._background_path) if enabled and self._background_path else QPixmap()
        self._background_pixmap = loaded if not loaded.isNull() else QPixmap()
        self.update()
        return self.has_background()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API 命名
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND_BASE_COLOR)
        _draw_cover(
            painter,
            self._background_pixmap,
            self.rect(),
            self._background_opacity,
        )
        painter.end()

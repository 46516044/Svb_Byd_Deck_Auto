"""界面侧卡组仓储。

集中处理已保存卡组的发现和变更通知，避免页面之间互相调用造成刷新递归或隐式耦合。
"""

from __future__ import annotations

import json
import os
from typing import List, Tuple

from PyQt5.QtCore import QObject, pyqtSignal


def list_saved_decks(decks_dir: str) -> List[Tuple[str, str]]:
    """返回已保存卡组 JSON 的 ``[(显示名, 文件名)]`` 列表。"""

    if not decks_dir:
        return []
    if not os.path.exists(decks_dir):
        return []

    decks: List[Tuple[str, str, int]] = []
    for filename in os.listdir(decks_dir):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(decks_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("deck json is not dict")
            name = data.get("name")
            display = str(name).strip() if isinstance(name, str) and name.strip() else filename[:-5]
            ts = int(data.get("timestamp", 0) or 0)
            decks.append((display, filename, ts))
        except Exception:
            decks.append((filename[:-5], filename, 0))

    # 稳定排序：先按时间戳从新到旧，再按名称排序。
    decks.sort(key=lambda t: (-t[2], t[0]))
    return [(d, f) for d, f, _ in decks]


class DeckStore(QObject):
    decks_changed = pyqtSignal()

    def __init__(self, *, decks_dir: str, parent: QObject | None = None):
        super().__init__(parent)
        self.decks_dir = decks_dir
        self._decks: List[Tuple[str, str]] = []
        self.refresh(emit=False)

    def refresh(self, *, emit: bool = True) -> None:
        self._decks = list_saved_decks(self.decks_dir)
        if emit:
            self.decks_changed.emit()

    def get_decks(self) -> List[Tuple[str, str]]:
        return list(self._decks)

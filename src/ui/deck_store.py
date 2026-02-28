"""Deck store (UI-side).

Centralizes saved deck discovery and change notification so UI pages don't call
each other (avoids refresh recursion / hidden coupling).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from PyQt5.QtCore import QObject, pyqtSignal


def list_saved_decks(decks_dir: str) -> List[Tuple[str, str]]:
    """Return [(display_name, filename)] for saved deck json files."""

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

    # Stable ordering: newest first by timestamp, then name.
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

"""Shared deck IO helpers."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from src.core.json_io import write_json_atomic


def save_deck_snapshot(
    *,
    deck_name: str,
    cards: List[str],
    decks_dir: str,
    config_path: Optional[str] = None,
) -> str:
    """Save a deck snapshot json and return its file path."""

    name = (deck_name or "").strip()
    if not name:
        raise ValueError("deck_name is empty")

    os.makedirs(decks_dir, exist_ok=True)

    deck_data: Dict[str, Any] = {
        "name": name,
        "cards": list(cards or []),
        "timestamp": int(time.time()),
    }

    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            deck_data["config"] = cfg

    deck_file = os.path.join(decks_dir, f"{name}.json")
    write_json_atomic(deck_file, deck_data, ensure_ascii=False, indent=2)
    return deck_file

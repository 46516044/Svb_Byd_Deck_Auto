"""Configuration path helpers.

Centralizes how we locate `config.json` across CLI/GUI/packaged runs.
"""

from __future__ import annotations

import os
import shutil
import sys


CARD_COST_DIRNAME = "card_cost"
LEGACY_CARD_COST_DIRNAME = "shadowverse_cards_cost"


def is_frozen() -> bool:
    # PyInstaller typically sets `sys.frozen` and provides `sys.executable`.
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def get_app_root() -> str:
    """Return the directory that should be treated as app root.

    - Source run: project root directory (where `main.py` lives)
    - PyInstaller: directory containing the executable
    """

    if is_frozen():
        return os.path.dirname(sys.executable)

    # This file: <project_root>/src/config/paths.py
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def get_config_path(filename: str = "config.json") -> str:
    """Return the canonical config file path."""

    return os.path.join(get_app_root(), filename)


def _migrate_legacy_card_cost_dir(app_root: str, new_dir: str) -> None:
    """Best-effort migrate legacy card-cost folder to the new location.

    - Legacy: ``shadowverse_cards_cost``
    - Current: ``card_cost``
    """

    legacy_dir = os.path.join(app_root, LEGACY_CARD_COST_DIRNAME)
    if not os.path.isdir(legacy_dir):
        return

    if not os.path.isdir(new_dir):
        try:
            os.replace(legacy_dir, new_dir)
            return
        except Exception:
            pass

    try:
        for name in os.listdir(legacy_dir):
            src = os.path.join(legacy_dir, name)
            dst = os.path.join(new_dir, name)
            if not os.path.isfile(src) or os.path.exists(dst):
                continue
            shutil.copy2(src, dst)
    except Exception:
        pass


def get_card_cost_dir(*, ensure: bool = False) -> str:
    """Return the canonical runtime card-cost directory.

    When ``ensure=True``:
    - creates ``card_cost`` if missing
    - migrates legacy ``shadowverse_cards_cost`` content best-effort
    """

    app_root = get_app_root()
    target = os.path.join(app_root, CARD_COST_DIRNAME)
    if ensure:
        os.makedirs(target, exist_ok=True)
        _migrate_legacy_card_cost_dir(app_root, target)
    return target

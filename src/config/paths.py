"""配置路径辅助函数。

统一 CLI、图形界面和打包运行时定位 ``config.json`` 的方式。
"""

from __future__ import annotations

import os
import shutil
import sys


CARD_COST_DIRNAME = "card_cost"
LEGACY_CARD_COST_DIRNAME = "shadowverse_cards_cost"


def is_frozen() -> bool:
    # PyInstaller 通常会设置 ``sys.frozen``，并通过 ``sys.executable`` 提供入口路径。
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def get_app_root() -> str:
    """返回应用根目录。

    源码运行时取 ``main.py`` 所在的项目根目录；PyInstaller 运行时取可执行文件目录。
    """

    if is_frozen():
        return os.path.dirname(sys.executable)

    # 当前文件位于 ``<project_root>/src/config/paths.py``。
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def get_config_path(filename: str = "config.json") -> str:
    """返回规范配置文件路径。"""

    return os.path.join(get_app_root(), filename)


def _migrate_legacy_card_cost_dir(app_root: str, new_dir: str) -> None:
    """尽力将旧卡牌费用目录迁移到新位置。

    旧目录为 ``shadowverse_cards_cost``，当前目录为 ``card_cost``。
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
    """返回规范的运行时卡牌费用目录。

    ``ensure=True`` 时会在目录缺失时创建 ``card_cost``，并尽力迁移旧目录
    ``shadowverse_cards_cost`` 中的内容。
    """

    app_root = get_app_root()
    target = os.path.join(app_root, CARD_COST_DIRNAME)
    if ensure:
        os.makedirs(target, exist_ok=True)
        _migrate_legacy_card_cost_dir(app_root, target)
    return target

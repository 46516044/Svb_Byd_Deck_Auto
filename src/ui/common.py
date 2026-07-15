"""PyQt 界面共用辅助函数。

界面专用工具集中放在这里，使 ``main_ui.py`` 保持轻量。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from src.config.paths import get_app_root


FONT_PATH = "猫啃什锦黑.otf"
BACKGROUND_IMAGE = "Image/ui背景.jpg"  # 背景图片路径


def get_exe_dir() -> str:
    """获取 EXE 所在目录（打包后）或脚本目录（直接运行 .py 时）"""

    return get_app_root()


def _deep_copy_json_like(value: Any) -> Any:
    """深拷贝dict/list等JSON结构，避免引用共享。"""

    if isinstance(value, dict):
        return {k: _deep_copy_json_like(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy_json_like(v) for v in value]
    return value


def deep_update_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """递归更新字典：只覆盖updates里出现的字段，不删除base里已有但updates未提供的字段。"""

    if not isinstance(base, dict) or not isinstance(updates, dict):
        return base

    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update_dict(base[key], value)
        else:
            base[key] = _deep_copy_json_like(value)
    return base


def load_custom_font(size: int = 10):
    # 延迟导入 Qt 字体模块，使本模块导入阶段只依赖标准库。
    from PyQt5.QtGui import QFont, QFontDatabase

    font = QFont("Microsoft YaHei", size)
    font_path = os.path.join(get_exe_dir(), FONT_PATH)
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            if font_families:
                font = QFont(font_families[0], size)
    return font

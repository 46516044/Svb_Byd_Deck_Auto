"""效果规格辅助函数。

实际实现位于 ``src.config.strategy_effects``，使界面导入时不必连带加载重量级
``src.game`` 模块。
"""

from __future__ import annotations

from src.config.strategy_effects import (
    get_card_effect_steps,
    parse_action,
    parse_select_option,
    parse_target_type,
)

__all__ = [
    "get_card_effect_steps",
    "parse_action",
    "parse_select_option",
    "parse_target_type",
]

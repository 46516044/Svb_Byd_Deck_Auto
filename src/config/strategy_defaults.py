"""默认策略与效果映射。

配置迁移和界面会用本模块预填、升级结构，因此这里不得引入 cv、u2 等重量级
运行时依赖。
"""

from __future__ import annotations

from typing import Any, Dict

from src.config.strategy_effects import (
    convert_legacy_action_to_ops,
    convert_legacy_target_type_to_ops,
)


# 默认的 ``on_play`` 目标选择，来源于旧 ``SPECIAL_CARDS`` 映射。
DEFAULT_SPECIAL_CARD_TARGET_TYPES: Dict[str, str] = {
    "蛇神之怒": "enemy_player",
    "威严的星晶骑士·薇拉": "double_enemy",
    "命运黄昏·奥丁": "shield_or_highest_hp",
    "安息的团结者": "shield_or_highest_hp",
    "小栗帽（联动异画）": "shield_or_highest_hp",
    "触手撕咬": "enemy_player",
    "沉默的狙击手·瓦路兹": "enemy_followers_hp_less_than_6",
    "剑士的斩击": "shield_or_highest_hp_no_enemy_retrun_point",
    "王断的威光": "scan_our_follower_to_choose",
}


# 默认进化与超进化特殊动作，来源于旧 ``EVOLVE_SPECIAL_ACTIONS``。
DEFAULT_EVOLVE_SPECIAL_ACTIONS: Dict[str, Dict[str, str]] = {
    "铁拳神父": {
        "on_evolve": "attack_enemy_follower_hp_less_than_4",
    },
    "沙神的巫女·莎拉": {
        "on_evolve": "attack_enemy_follower_hp_less_than_4",
    },
    "爽朗的天宫·菲尔德亚": {
        "on_evolve": "attack_two_enemy_followers_hp_highest",
        "on_super_evolve": "attack_two_enemy_followers_hp_highest",
    },
    "勇武的堕天使·奥莉薇": {
        "on_super_evolve": "our_followers_with_evolution",
    },
}


def build_default_effects() -> Dict[str, Any]:
    """返回默认的 ``strategy.effects`` 数据。"""

    effects: Dict[str, Any] = {}

    for card_name, target_type in DEFAULT_SPECIAL_CARD_TARGET_TYPES.items():
        converted = convert_legacy_target_type_to_ops(target_type)
        if converted:
            effects.setdefault(card_name, {}).setdefault("on_play", []).extend(converted)

    for card_name, actions in DEFAULT_EVOLVE_SPECIAL_ACTIONS.items():
        if "on_evolve" in actions:
            converted = convert_legacy_action_to_ops(actions["on_evolve"])
            if converted:
                effects.setdefault(card_name, {}).setdefault("on_evolve", []).extend(converted)
        if "on_super_evolve" in actions:
            converted = convert_legacy_action_to_ops(actions["on_super_evolve"])
            if converted:
                effects.setdefault(card_name, {}).setdefault("on_super_evolve", []).extend(converted)

    return effects

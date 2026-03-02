"""Default strategy/effects mapping.

Keep this module free of heavy runtime deps (cv/u2/etc.).
It is used by config migrations and UI to prefill/upgrade schemas.
"""

from __future__ import annotations

from typing import Any, Dict


# Default on_play target selection (legacy `SPECIAL_CARDS` mapping).
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


# Default on_evolve/on_super_evolve special actions (legacy `EVOLVE_SPECIAL_ACTIONS`).
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
    """Return default `strategy.effects` payload."""

    effects: Dict[str, Any] = {}

    for card_name, target_type in DEFAULT_SPECIAL_CARD_TARGET_TYPES.items():
        effects.setdefault(card_name, {}).setdefault("on_play", []).append(
            {"op": "legacy_target_type", "target_type": target_type}
        )

    for card_name, actions in DEFAULT_EVOLVE_SPECIAL_ACTIONS.items():
        if "on_evolve" in actions:
            effects.setdefault(card_name, {}).setdefault("on_evolve", []).append(
                {"op": "legacy_action", "action": actions["on_evolve"]}
            )
        if "on_super_evolve" in actions:
            effects.setdefault(card_name, {}).setdefault("on_super_evolve", []).append(
                {"op": "legacy_action", "action": actions["on_super_evolve"]}
            )

    return effects

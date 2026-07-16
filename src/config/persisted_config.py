"""控制 ``config.json`` 实际落盘内容的辅助函数。

运行时配置与 ``DEFAULT_CONFIG`` 合并后，可能带有内部字段或硬编码字段。将这些
并未真正由代码消费的内容写给用户，只会增加噪声和理解成本。本模块定义写入前
执行的精简步骤。
"""

from __future__ import annotations

import copy
from typing import Any, Dict


# 以下键当前属于内部字段、硬编码字段或未使用字段，不应写入用户配置。
_DROP_TOP_LEVEL_KEYS = {
    "adb_port",  # 未使用，设备序列号保存在 devices[*].serial。
    "templates",  # 当前未使用，每个模板的阈值仍由代码单独定义。
    "profiles",  # 内部占位结构，由运行时默认值补齐。
    "card_mode_options",  # 加载时迁移到 strategy.effects。
    "card_evolve_mode_options",  # 加载时迁移到 strategy.effects。
}

_DROP_GAME_KEYS = {
    "resolution",  # 当前未使用，大部分坐标仍按 1280x720 处理。
    "evolution_rounds",  # 当前由状态机硬编码。
    "evolution_rounds_with_extra_cost",  # 当前由状态机硬编码。
    "max_follower_count",  # 当前硬编码为 HP_MAX_FOLLOWERS。
    "cost_recognition",  # 当前未使用，费用来自 SIFT 模板。
    "use_enhanced_mulligan",  # 运行时只使用规范化后的增强换牌路径。
}

_DROP_AUTO_RESTART_KEYS = {
    "output_timeout",  # 旧键，已由 stage_timeout 替代。
    "match_timeout",  # 已移除的旧键。
}

_DROP_RUN_SETTINGS_KEYS = {
    "max_battle_count",  # 已移除。
    "force_close",  # 已移除。
}


def prune_config_for_save(config: Dict[str, Any]) -> Dict[str, Any]:
    """返回适合写入磁盘的精简配置副本。"""

    if not isinstance(config, dict):
        return {}

    cfg: Dict[str, Any] = copy.deepcopy(config)

    for k in _DROP_TOP_LEVEL_KEYS:
        cfg.pop(k, None)

    game = cfg.get("game")
    if isinstance(game, dict):
        for k in _DROP_GAME_KEYS:
            game.pop(k, None)

        # 若 game 精简后为空，则一并删除该容器。
        if not game:
            cfg.pop("game", None)

    auto_restart = cfg.get("auto_restart")
    if isinstance(auto_restart, dict):
        for k in _DROP_AUTO_RESTART_KEYS:
            auto_restart.pop(k, None)

    run_settings = cfg.get("run_settings")
    if isinstance(run_settings, dict):
        for k in _DROP_RUN_SETTINGS_KEYS:
            run_settings.pop(k, None)

        try:
            run_settings["max_run_duration"] = max(
                0, int(run_settings.get("max_run_duration", 0) or 0)
            )
        except Exception:
            run_settings["max_run_duration"] = 0

    return cfg

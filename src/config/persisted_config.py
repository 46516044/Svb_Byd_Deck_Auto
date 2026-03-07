"""Helpers for controlling what gets written to disk as config.json.

The runtime config is merged with DEFAULT_CONFIG and may include internal/
hard-coded fields. For end-users, persisting those fields in config.json adds
noise and confusion (especially when the code does not actually consume them).

This module defines a small "prune" step applied before writing config.json.
"""

from __future__ import annotations

import copy
from typing import Any, Dict


# Keys that are currently internal/hard-coded/unused and should not be persisted
# into user-facing config.json.
_DROP_TOP_LEVEL_KEYS = {
    "adb_port",  # unused (device serials are stored under devices[*].serial)
    "templates",  # currently unused (template thresholds are hard-coded per-template)
    "profiles",  # internal placeholder; runtime defaults fill it
    "card_mode_options",  # migrated to strategy.effects at load-time
    "card_evolve_mode_options",  # migrated to strategy.effects at load-time
}

_DROP_GAME_KEYS = {
    "resolution",  # currently unused (most coordinates assume 1280x720)
    "evolution_rounds",  # currently hard-coded in state machine
    "evolution_rounds_with_extra_cost",  # currently hard-coded in state machine
    "max_follower_count",  # currently hard-coded as HP_MAX_FOLLOWERS
    "cost_recognition",  # currently unused (cost comes from SIFT templates)
    "use_enhanced_mulligan",  # runtime now uses canonical enhanced path only
}

_DROP_AUTO_RESTART_KEYS = {
    "output_timeout",  # legacy key; replaced by stage_timeout
    "match_timeout",  # legacy key; removed
}

_DROP_RUN_SETTINGS_KEYS = {
    "max_battle_count",  # removed
    "force_close",  # removed
}


def prune_config_for_save(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a pruned copy of config for persistence to disk."""

    if not isinstance(config, dict):
        return {}

    cfg: Dict[str, Any] = copy.deepcopy(config)

    for k in _DROP_TOP_LEVEL_KEYS:
        cfg.pop(k, None)

    game = cfg.get("game")
    if isinstance(game, dict):
        for k in _DROP_GAME_KEYS:
            game.pop(k, None)

        # If game becomes empty (unlikely), drop it.
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

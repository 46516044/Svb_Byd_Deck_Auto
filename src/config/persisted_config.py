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
}

_DROP_GAME_KEYS = {
    "resolution",  # currently unused (most coordinates assume 1280x720)
    "evolution_rounds",  # currently hard-coded in state machine
    "evolution_rounds_with_extra_cost",  # currently hard-coded in state machine
    "max_follower_count",  # currently hard-coded as HP_MAX_FOLLOWERS
    "cost_recognition",  # currently unused (cost comes from SIFT templates)
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

    return cfg

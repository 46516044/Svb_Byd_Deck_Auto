"""Card priority helpers.

Configuration is the single source of truth.

This module should not perform disk IO or maintain its own divergent cache.
Callers should pass a config dict explicitly (preferred). For backward
compatibility, `reload_config(config)` can be called at startup to inject a
process-wide runtime config used when call sites don't pass one.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


_RUNTIME_CONFIG: Optional[Dict[str, Any]] = None


def set_runtime_config(config: Optional[Dict[str, Any]]) -> None:
    """Inject a runtime config dict (e.g. ConfigManager.config)."""

    global _RUNTIME_CONFIG
    _RUNTIME_CONFIG = config if isinstance(config, dict) else None


def reload_config(config: Optional[Dict[str, Any]] = None) -> None:
    """Backward-compatible entrypoint used by bootstrap.

    Note: no disk read occurs here.
    """

    if config is not None:
        set_runtime_config(config)
        logger.info("卡牌优先级配置已注入(运行期配置)")
    else:
        # Keep behavior safe: do not silently read from disk.
        logger.info("卡牌优先级配置 reload 被调用(未提供config)，将使用已注入的运行期配置")


def _effective_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(config, dict):
        return config
    if isinstance(_RUNTIME_CONFIG, dict):
        return _RUNTIME_CONFIG
    return {}


def _get_mapping(config: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
    cfg = _effective_config(config)
    val = cfg.get(key)
    return val if isinstance(val, dict) else {}


def get_high_priority_cards(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return mapping: card_name -> config dict."""

    return _get_mapping(config, "high_priority_cards")


def is_high_priority_card(card_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
    return str(card_name) in get_high_priority_cards(config)


def get_evolve_priority_cards(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return mapping: card_name -> config dict."""

    return _get_mapping(config, "evolve_priority_cards")


def is_evolve_priority_card(card_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
    return str(card_name) in get_evolve_priority_cards(config)


def get_card_priority_pre_evolution(card_name: str, config: Optional[Dict[str, Any]] = None) -> int:
    """Get play priority for pre-evolution stage (smaller is higher priority)."""

    cfg = get_high_priority_cards(config).get(str(card_name))
    if isinstance(cfg, dict) and "priority_pre_evolution" in cfg:
        try:
            return int(cfg["priority_pre_evolution"])
        except Exception:
            return 999
    return 999


def get_card_priority_post_evolution(card_name: str, config: Optional[Dict[str, Any]] = None) -> int:
    """Get play priority for post-evolution stage (smaller is higher priority)."""

    cfg = get_high_priority_cards(config).get(str(card_name))
    if isinstance(cfg, dict) and "priority_post_evolution" in cfg:
        try:
            return int(cfg["priority_post_evolution"])
        except Exception:
            return 999
    return 999


def is_evolution_unlocked(device_state) -> bool:
    """Determine if evolve is unlocked based on current round + first/second."""

    if getattr(device_state, "extra_cost_available_this_match", None) is None:
        return False

    if getattr(device_state, "extra_cost_available_this_match", None) is True:
        return int(getattr(device_state, "current_round_count", 0) or 0) >= 4

    if getattr(device_state, "extra_cost_available_this_match", None) is False:
        return int(getattr(device_state, "current_round_count", 0) or 0) >= 5

    return False

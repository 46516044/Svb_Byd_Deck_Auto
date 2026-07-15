"""卡牌优先级辅助函数。

配置对象是唯一可信数据源。本模块不执行磁盘 IO，也不维护可能与配置分叉的缓存。
调用方应优先显式传入配置字典；为兼容旧调用方式，启动时也可通过
``reload_config(config)`` 注入进程级运行配置，供未传配置的调用点使用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.utils.card_filename import (
    make_enhance_key,
    normalize_card_base_name,
    parse_follower_stat_suffix,
    split_enhance_key,
)


logger = logging.getLogger(__name__)


_runtime_config: Optional[Dict[str, Any]] = None


def set_runtime_config(config: Optional[Dict[str, Any]]) -> None:
    """注入运行时配置字典，例如 ``ConfigManager.config``。"""

    global _runtime_config
    _runtime_config = config if isinstance(config, dict) else None


def reload_config(config: Optional[Dict[str, Any]] = None) -> None:
    """供启动编排层使用的兼容入口；此处不会读取磁盘。"""

    if config is not None:
        set_runtime_config(config)
        logger.info("卡牌优先级配置已注入(运行期配置)")
    else:
    # 未注入配置时保持安全默认值，不在这里隐式读取磁盘。
        logger.info("卡牌优先级配置 reload 被调用(未提供config)，将使用已注入的运行期配置")


def _effective_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(config, dict):
        return config
    if isinstance(_runtime_config, dict):
        return _runtime_config
    return {}


def _get_mapping(config: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
    cfg = _effective_config(config)
    val = cfg.get(key)
    return val if isinstance(val, dict) else {}


def _name_candidates(card_name: str) -> list[str]:
    raw = str(card_name or "")
    if not raw:
        return []

    out: list[str] = [raw]
    base = raw
    enhance_cost = None

    if "@" in raw:
        b, c = split_enhance_key(raw)
        base = str(b or "")
        enhance_cost = c
        if base and base not in out:
            out.append(base)

    stripped, _atk, _hp = parse_follower_stat_suffix(base)
    if stripped and stripped != base:
        if enhance_cost is not None:
            enh_key = make_enhance_key(stripped, int(enhance_cost))
            if enh_key not in out:
                out.append(enh_key)
        if stripped not in out:
            out.append(stripped)

    normalized_base = normalize_card_base_name(base)
    if normalized_base:
        if enhance_cost is not None:
            enh_key = make_enhance_key(normalized_base, int(enhance_cost))
            if enh_key not in out:
                out.append(enh_key)
        if normalized_base not in out:
            out.append(normalized_base)

    return out


def get_high_priority_cards(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """返回 ``卡牌名 -> 配置字典`` 映射。"""

    return _get_mapping(config, "high_priority_cards")


def is_high_priority_card(card_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
    mapping = get_high_priority_cards(config)
    return any(name in mapping for name in _name_candidates(str(card_name)))


def get_evolve_priority_cards(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """返回 ``卡牌名 -> 配置字典`` 映射。"""

    return _get_mapping(config, "evolve_priority_cards")


def is_evolve_priority_card(card_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
    mapping = get_evolve_priority_cards(config)
    return any(name in mapping for name in _name_candidates(str(card_name)))


def get_card_priority_pre_evolution(card_name: str, config: Optional[Dict[str, Any]] = None) -> int:
    """获取进化前出牌优先级，数值越小优先级越高。"""

    mapping = get_high_priority_cards(config)
    for key in _name_candidates(str(card_name)):
        cfg = mapping.get(key)
        if isinstance(cfg, dict) and "priority_pre_evolution" in cfg:
            try:
                return int(cfg["priority_pre_evolution"])
            except Exception:
                return 999
    return 999


def get_card_priority_post_evolution(card_name: str, config: Optional[Dict[str, Any]] = None) -> int:
    """获取进化后出牌优先级，数值越小优先级越高。"""

    mapping = get_high_priority_cards(config)
    for key in _name_candidates(str(card_name)):
        cfg = mapping.get(key)
        if isinstance(cfg, dict) and "priority_post_evolution" in cfg:
            try:
                return int(cfg["priority_post_evolution"])
            except Exception:
                return 999
    return 999


def get_evolve_priority(card_name: str, config: Optional[Dict[str, Any]] = None) -> int:
    """获取进化优先级，数值越小优先级越高。"""

    mapping = get_evolve_priority_cards(config)
    for key in _name_candidates(str(card_name)):
        cfg = mapping.get(key)
        if isinstance(cfg, dict) and "priority" in cfg:
            try:
                return int(cfg["priority"])
            except Exception:
                return 999
    return 999


def is_evolution_unlocked(device_state) -> bool:
    """根据当前回合以及先后手判断是否已解锁进化。"""

    if getattr(device_state, "extra_cost_available_this_match", None) is None:
        return False

    if getattr(device_state, "extra_cost_available_this_match", None) is True:
        return int(getattr(device_state, "current_round_count", 0) or 0) >= 4

    if getattr(device_state, "extra_cost_available_this_match", None) is False:
        return int(getattr(device_state, "current_round_count", 0) or 0) >= 5

    return False

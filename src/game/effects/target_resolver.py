"""Target resolving for Step3A `select_targets` operation.

This module is runtime-only (allowed to call cv/u2/game managers).
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple

from src.config.card_priorities import get_evolve_priority_cards
from src.config.game_constants import DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_TARGET
from src.game.policy.targets import TargetSelector


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _parse_target_spec(target: Any) -> Tuple[str, str, Dict[str, Any]]:
    if not isinstance(target, dict):
        return "", "", {}
    kind = str(target.get("kind") or "")
    selector = str(target.get("selector") or "")
    params = target.get("params")
    if not isinstance(params, dict):
        params = {}
    return kind, selector, params


def _random_enemy_leader_target() -> Tuple[int, int]:
    x = int(DEFAULT_ATTACK_TARGET[0]) + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
    y = int(DEFAULT_ATTACK_TARGET[1]) + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
    return (x, y)


def _scan_enemy_followers(ds: Any, *, is_select_ui: bool) -> Tuple[Any, List[Any]]:
    screenshot = None
    try:
        screenshot = ds.take_screenshot()
    except Exception:
        screenshot = None

    if screenshot is None:
        return None, []

    try:
        enemy_followers = (
            ds.game_manager.scan_enemy_followers(screenshot, is_select=bool(is_select_ui))
            if ds.game_manager
            else []
        )
    except Exception:
        enemy_followers = []

    return screenshot, list(enemy_followers or [])


def _scan_ward_targets(
    ds: Any,
    *,
    selector: str,
    screenshot: Any,
    enemy_followers: Sequence[Any],
    is_select_ui: bool,
) -> List[Tuple[int, int]]:
    if selector != "ward_or_highest_hp":
        return []

    try:
        if ds.game_manager and hasattr(ds.game_manager, "scan_shield_targets_for_enemy_followers"):
            return ds.game_manager.scan_shield_targets_for_enemy_followers(
                screenshot,
                enemy_followers,
                is_select=bool(is_select_ui),
            )
        return ds.game_manager.scan_shield_targets() if ds.game_manager else []
    except Exception:
        return []


def _enemy_follower_fallback_flags(selector: str, params: Dict[str, Any]) -> Tuple[bool, bool]:
    try:
        if selector == "ward_or_highest_hp":
            allow_amulet_fallback = bool(params.get("allow_amulet_fallback", True))
        elif selector == "hp_leq_or_highest_hp":
            allow_amulet_fallback = bool(params.get("allow_amulet_fallback", False))
        else:
            allow_amulet_fallback = bool(params.get("allow_amulet_fallback", False))
        fallback_to_enemy_leader = bool(params.get("fallback_to_enemy_leader", False))
        return allow_amulet_fallback, fallback_to_enemy_leader
    except Exception:
        return False, False


def _pick_enemy_follower_targets(
    enemy_followers: Sequence[Any],
    *,
    selector: str,
    params: Dict[str, Any],
    n: int,
    distinct_xy: bool,
    wards: Sequence[Tuple[int, int]],
) -> List[Any]:
    picked: List[Any] = []

    if selector in ("", "highest_hp"):
        if n <= 1:
            one = TargetSelector.enemy_follower_highest_hp(enemy_followers)
            if one is not None:
                picked = [one]
        else:
            picked = TargetSelector.enemy_followers_highest_hp(
                enemy_followers,
                n=n,
                distinct_xy=bool(distinct_xy),
            )

    elif selector == "hp_leq":
        max_hp = _safe_int(params.get("max_hp", 0), 0)
        if n <= 1:
            one = TargetSelector.enemy_follower_hp_leq(enemy_followers, max_hp=max_hp)
            if one is not None:
                picked = [one]
        else:
            picked = TargetSelector.enemy_followers_hp_leq(
                enemy_followers,
                max_hp=max_hp,
                n=n,
            )

    elif selector == "hp_leq_or_highest_hp":
        max_hp = _safe_int(params.get("max_hp", 0), 0)
        if n <= 1:
            one = TargetSelector.enemy_follower_hp_leq(enemy_followers, max_hp=max_hp)
            if one is None:
                one = TargetSelector.enemy_follower_highest_hp(enemy_followers)
            if one is not None:
                picked = [one]
        else:
            picked = TargetSelector.enemy_followers_hp_leq(
                enemy_followers,
                max_hp=max_hp,
                n=n,
            )
            if not picked:
                picked = TargetSelector.enemy_followers_highest_hp(
                    enemy_followers,
                    n=n,
                    distinct_xy=bool(distinct_xy),
                )

    elif selector == "ward_or_highest_hp":
        if n <= 1:
            one = TargetSelector.enemy_follower_ward_or_highest_hp(
                enemy_followers,
                list(wards or []),
            )
            if one is not None:
                picked = [one]
        else:
            ward_followers = TargetSelector.enemy_followers_in_wards(
                enemy_followers,
                list(wards or []),
            )
            source = ward_followers if ward_followers else list(enemy_followers or [])
            picked = TargetSelector.enemy_followers_highest_hp(
                source,
                n=n,
                distinct_xy=bool(distinct_xy),
            )

    return list(picked or [])


def _to_xy_targets(items: Sequence[Any]) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for item in list(items or []):
        try:
            out.append((_safe_int(item[0], 0), _safe_int(item[1], 0)))
        except Exception:
            continue
    return out


def _resolve_enemy_follower_targets(
    ctx: Any,
    *,
    ds: Any,
    selector: str,
    params: Dict[str, Any],
    n: int,
    distinct_xy: bool,
    is_select_ui: bool,
) -> List[Tuple[int, int]]:
    allow_amulet_fallback, fallback_to_enemy_leader = _enemy_follower_fallback_flags(selector, params)

    screenshot, enemy_followers = _scan_enemy_followers(ds, is_select_ui=bool(is_select_ui))
    if screenshot is None:
        return []

    wards = _scan_ward_targets(
        ds,
        selector=selector,
        screenshot=screenshot,
        enemy_followers=enemy_followers,
        is_select_ui=bool(is_select_ui),
    )

    if not enemy_followers and allow_amulet_fallback:
        try:
            amulet_targets = ds.game_manager.card_can_choose_target_like_amulet() if ds.game_manager else []
        except Exception:
            amulet_targets = []

        if not amulet_targets:
            return []
        return _to_xy_targets(list(amulet_targets or [])[:n])

    if not enemy_followers and fallback_to_enemy_leader:
        return [_random_enemy_leader_target()]

    if not enemy_followers:
        return []

    picked = _pick_enemy_follower_targets(
        enemy_followers,
        selector=selector,
        params=params,
        n=n,
        distinct_xy=bool(distinct_xy),
        wards=wards,
    )
    return _to_xy_targets(picked)


def _scan_our_followers_for_target(ctx: Any, ds: Any) -> Sequence[Any]:
    our_followers: Sequence[Any] = []
    try:
        if getattr(ctx, "existing_followers", None) is not None:
            our_followers = list(getattr(ctx, "existing_followers") or [])
    except Exception:
        our_followers = []

    if our_followers:
        return our_followers

    screenshot = None
    try:
        screenshot = ds.take_screenshot()
    except Exception:
        screenshot = None
    if screenshot is None:
        return []

    try:
        return (
            ds.game_manager.scan_our_followers(
                screenshot,
                extra_shots=0,
                sort_desc=False,
                with_names=True,
            )
            if ds.game_manager
            else []
        )
    except Exception:
        return []


def _resolve_friendly_follower_targets(
    ctx: Any,
    *,
    ds: Any,
    selector: str,
    params: Dict[str, Any],
) -> List[Tuple[int, int]]:
    our_followers = _scan_our_followers_for_target(ctx, ds)
    if not our_followers:
        return []

    if selector not in ("", "by_evolve_priority"):
        return []

    exclude_self = bool(params.get("exclude_self", True))
    exclude_names: List[str] = []
    if exclude_self:
        try:
            follower_name = str(getattr(ctx, "follower_name", "") or "")
            if follower_name:
                exclude_names = [follower_name]
        except Exception:
            exclude_names = []

    evolve_priority_cards = get_evolve_priority_cards(getattr(ds, "config", None))
    picked_follower = TargetSelector.friendly_follower_by_evolve_priority(
        our_followers,
        exclude_names=exclude_names,
        evolve_priority_cards=evolve_priority_cards,
    )
    if picked_follower is None:
        return []

    try:
        return [
            (
                _safe_int(picked_follower[0], 0),
                _safe_int(picked_follower[1], 0),
            )
        ]
    except Exception:
        return []


def resolve_targets(
    ctx: Any,
    *,
    target: Any,
    count: int = 1,
    distinct_xy: bool = True,
    is_select_ui: bool = True,
) -> List[Tuple[int, int]]:
    """Resolve a TargetSpec dict into click positions."""

    ds = getattr(ctx, "device_state", None)
    if ds is None:
        return []

    kind, selector, params = _parse_target_spec(target)
    n = max(1, _safe_int(count, 1))

    if kind == "enemy_leader":
        return [_random_enemy_leader_target()]

    if kind == "enemy_follower":
        return _resolve_enemy_follower_targets(
            ctx,
            ds=ds,
            selector=selector,
            params=params,
            n=n,
            distinct_xy=bool(distinct_xy),
            is_select_ui=bool(is_select_ui),
        )

    if kind == "friendly_follower":
        return _resolve_friendly_follower_targets(
            ctx,
            ds=ds,
            selector=selector,
            params=params,
        )

    return []

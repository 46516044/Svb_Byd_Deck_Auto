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
        x = int(DEFAULT_ATTACK_TARGET[0]) + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
        y = int(DEFAULT_ATTACK_TARGET[1]) + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
        return [(x, y)]

    if kind == "enemy_follower":
        wards: List[Tuple[int, int]] = []

        allow_amulet_fallback = False
        fallback_to_enemy_leader = False
        try:
            if selector == "ward_or_highest_hp":
                allow_amulet_fallback = bool(params.get("allow_amulet_fallback", True))
            elif selector == "hp_leq_or_highest_hp":
                allow_amulet_fallback = bool(params.get("allow_amulet_fallback", False))
            else:
                allow_amulet_fallback = bool(params.get("allow_amulet_fallback", False))
            fallback_to_enemy_leader = bool(params.get("fallback_to_enemy_leader", False))
        except Exception:
            allow_amulet_fallback = False
            fallback_to_enemy_leader = False

        screenshot = None
        try:
            screenshot = ds.take_screenshot()
        except Exception:
            screenshot = None
        if screenshot is None:
            return []

        try:
            enemy_followers = (
                ds.game_manager.scan_enemy_followers(screenshot, is_select=bool(is_select_ui))
                if ds.game_manager
                else []
            )
        except Exception:
            enemy_followers = []

        # Resolve ward on the same screenshot/frame as enemy followers to avoid
        # cross-frame mismatch (ward missed -> fallback highest_hp).
        if selector == "ward_or_highest_hp":
            try:
                if ds.game_manager and hasattr(ds.game_manager, "scan_shield_targets_for_enemy_followers"):
                    wards = ds.game_manager.scan_shield_targets_for_enemy_followers(
                        screenshot,
                        enemy_followers,
                    )
                else:
                    wards = ds.game_manager.scan_shield_targets() if ds.game_manager else []
            except Exception:
                wards = []

        if not enemy_followers and allow_amulet_fallback:
            # Fallback: when there is no enemy follower but selectable amulet-like targets exist,
            # return those positions so the card can still be cast.
            try:
                amulet_targets = (
                    ds.game_manager.card_can_choose_target_like_amulet()
                    if ds.game_manager
                    else []
                )
            except Exception:
                amulet_targets = []

            if not amulet_targets:
                return []

            out: List[Tuple[int, int]] = []
            for x, y in list(amulet_targets)[:n]:
                out.append((_safe_int(x, 0), _safe_int(y, 0)))
            return out

        if not enemy_followers and fallback_to_enemy_leader:
            x = int(DEFAULT_ATTACK_TARGET[0]) + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
            y = int(DEFAULT_ATTACK_TARGET[1]) + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
            return [(x, y)]

        if not enemy_followers:
            return []

        picked: List[Any] = []
        if selector in ("", "highest_hp"):
            if n <= 1:
                one = TargetSelector.enemy_follower_highest_hp(enemy_followers)
                if one is not None:
                    picked = [one]
            else:
                picked = TargetSelector.enemy_followers_highest_hp(
                    enemy_followers, n=n, distinct_xy=bool(distinct_xy)
                )

        elif selector == "hp_leq":
            max_hp = _safe_int(params.get("max_hp", 0), 0)
            if n <= 1:
                one = TargetSelector.enemy_follower_hp_leq(enemy_followers, max_hp=max_hp)
                if one is not None:
                    picked = [one]
            else:
                picked = TargetSelector.enemy_followers_hp_leq(
                    enemy_followers, max_hp=max_hp, n=n
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
                    source, n=n, distinct_xy=bool(distinct_xy)
                )

        else:
            # Unknown selector: safe no-op.
            picked = []

        out: List[Tuple[int, int]] = []
        for f in picked:
            try:
                out.append((_safe_int(f[0], 0), _safe_int(f[1], 0)))
            except Exception:
                continue
        return out

    if kind == "friendly_follower":
        # Prefer passed-in scan results.
        our_followers: Sequence[Any] = []
        try:
            if getattr(ctx, "existing_followers", None) is not None:
                our_followers = list(getattr(ctx, "existing_followers") or [])
        except Exception:
            our_followers = []

        if not our_followers:
            screenshot = None
            try:
                screenshot = ds.take_screenshot()
            except Exception:
                screenshot = None
            if screenshot is None:
                return []
            try:
                our_followers = (
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
                our_followers = []

        if not our_followers:
            return []

        if selector in ("", "by_evolve_priority"):
            exclude_self = bool(params.get("exclude_self", True))
            exclude_names = []
            if exclude_self:
                try:
                    if getattr(ctx, "follower_name", ""):
                        exclude_names = [str(getattr(ctx, "follower_name"))]
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

        return []

    return []

"""Target selection helpers.

This module centralizes legacy target picking logic so card/evolve special actions
don't each re-implement `max(valid_targets, ...)` variants.

Design goals:
- Pure functions (no device/cv/config IO)
- Accept legacy data shapes used by the current codebase
- Preserve existing selection semantics as much as possible
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.utils.card_filename import normalize_config_key


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _enemy_hp_key(follower: Sequence[Any]) -> int:
    # Legacy enemy follower tuple: (x, y, type, hp_str)
    try:
        hp = follower[3]
    except Exception:
        return 0

    if isinstance(hp, str):
        return _safe_int(hp, 0) if hp.isdigit() else 0
    return _safe_int(hp, 0)


def _follower_xy(follower: Sequence[Any]) -> Tuple[int, int]:
    return _safe_int(follower[0], 0), _safe_int(follower[1], 0)


class TargetSelector:
    """Legacy-friendly selector library."""

    @staticmethod
    def enemy_follower_highest_hp(enemy_followers: Sequence[Sequence[Any]]) -> Optional[Sequence[Any]]:
        """Pick the enemy follower with the highest HP.

        Legacy semantics: non-digit HP counts as 0; if all keys tie, keep the first.
        """

        if not enemy_followers:
            return None
        return max(enemy_followers, key=_enemy_hp_key)

    @staticmethod
    def enemy_followers_in_wards(
        enemy_followers: Sequence[Sequence[Any]],
        ward_positions: Sequence[Sequence[Any]],
        *,
        x_tolerance: int = 50,
    ) -> List[Sequence[Any]]:
        """Filter enemy followers that match ward positions by x-axis proximity."""

        if not enemy_followers or not ward_positions:
            return []

        wards_x = []
        for w in ward_positions:
            try:
                wards_x.append(_safe_int(w[0], 0))
            except Exception:
                continue
        if not wards_x:
            return []

        out: List[Sequence[Any]] = []
        tol = max(1, int(x_tolerance))
        for f in enemy_followers:
            try:
                fx = _safe_int(f[0], 0)
            except Exception:
                continue
            if any(abs(fx - wx) < tol for wx in wards_x):
                out.append(f)
        return out

    @staticmethod
    def enemy_follower_highest_hp_in_wards(
        enemy_followers: Sequence[Sequence[Any]],
        ward_positions: Sequence[Sequence[Any]],
        *,
        x_tolerance: int = 50,
    ) -> Optional[Sequence[Any]]:
        """Pick highest HP follower among ward followers only."""

        ward_followers = TargetSelector.enemy_followers_in_wards(
            enemy_followers,
            ward_positions,
            x_tolerance=int(x_tolerance),
        )
        if not ward_followers:
            return None
        return max(ward_followers, key=_enemy_hp_key)

    @staticmethod
    def enemy_followers_highest_hp(
        enemy_followers: Sequence[Sequence[Any]],
        *,
        n: int = 2,
        distinct_xy: bool = True,
    ) -> List[Sequence[Any]]:
        """Pick top-N enemy followers by HP (descending)."""

        if not enemy_followers:
            return []

        ordered = sorted(enemy_followers, key=_enemy_hp_key, reverse=True)
        picked: List[Sequence[Any]] = []
        seen: set[Tuple[int, int]] = set()

        for f in ordered:
            if len(picked) >= max(0, int(n)):
                break
            if distinct_xy:
                xy = _follower_xy(f)
                if xy in seen:
                    continue
                seen.add(xy)
            picked.append(f)

        return picked

    @staticmethod
    def enemy_follower_ward_or_highest_hp(
        enemy_followers: Sequence[Sequence[Any]],
        ward_positions: Sequence[Sequence[Any]],
        *,
        x_tolerance: int = 50,
    ) -> Optional[Sequence[Any]]:
        """Pick highest HP ward follower first; fallback to highest HP follower."""

        ward_pick = TargetSelector.enemy_follower_highest_hp_in_wards(
            enemy_followers,
            ward_positions,
            x_tolerance=int(x_tolerance),
        )
        if ward_pick is not None:
            return ward_pick
        return TargetSelector.enemy_follower_highest_hp(enemy_followers)

    @staticmethod
    def enemy_follower_hp_leq(
        enemy_followers: Sequence[Sequence[Any]],
        *,
        max_hp: int,
    ) -> Optional[Sequence[Any]]:
        """Pick the enemy follower with highest HP among those with hp <= max_hp.

        Only digit HP values are considered eligible (preserve existing filters).
        """

        if not enemy_followers:
            return None

        limit = _safe_int(max_hp, 0)
        candidates: List[Sequence[Any]] = []
        for f in enemy_followers:
            try:
                hp = f[3]
            except Exception:
                continue
            if not (isinstance(hp, str) and hp.isdigit()):
                continue
            if _safe_int(hp, 0) <= limit:
                candidates.append(f)

        if not candidates:
            return None
        return max(candidates, key=_enemy_hp_key)

    @staticmethod
    def enemy_followers_hp_leq(
        enemy_followers: Sequence[Sequence[Any]],
        *,
        max_hp: int,
        n: int = 2,
    ) -> List[Sequence[Any]]:
        """Pick top-N by HP among those with hp <= max_hp."""

        limit = _safe_int(max_hp, 0)
        candidates: List[Sequence[Any]] = []
        for f in enemy_followers:
            try:
                hp = f[3]
            except Exception:
                continue
            if not (isinstance(hp, str) and hp.isdigit()):
                continue
            if _safe_int(hp, 0) <= limit:
                candidates.append(f)

        ordered = sorted(candidates, key=_enemy_hp_key, reverse=True)
        return ordered[: max(0, int(n))]

    @staticmethod
    def friendly_follower_by_evolve_priority(
        our_followers: Sequence[Sequence[Any]],
        *,
        exclude_names: Iterable[str] = (),
        evolve_priority_cards: Optional[Dict[str, Any]] = None,
    ) -> Optional[Sequence[Any]]:
        """Pick a friendly follower by configured evolve priority.

        Legacy semantics (used by EvolutionSpecialActions):
        - Prefer named followers (name != None) excluding given names
        - Among named: sort by config priority (smaller is better), then x
        - Fallback: first unnamed follower (name is None)
        """

        if not our_followers:
            return None

        exclude = set(exclude_names or [])
        priority_cfg = evolve_priority_cards or {}

        exclude_norm = {normalize_config_key(str(n or "")) for n in list(exclude or [])}
        priority_norm: Dict[str, Any] = {}
        for k, v in dict(priority_cfg or {}).items():
            nk = normalize_config_key(str(k or ""))
            if not nk:
                continue
            if nk not in priority_norm:
                priority_norm[nk] = v

        def _prio(name: Any) -> int:
            if not isinstance(name, str) or not name:
                return 999
            cfg = priority_norm.get(normalize_config_key(name))
            if isinstance(cfg, dict):
                return _safe_int(cfg.get("priority", 999), 999)
            return 999

        named: List[Sequence[Any]] = []
        unnamed: List[Sequence[Any]] = []
        for f in our_followers:
            name = None
            if len(f) > 3:
                name = f[3]
            if isinstance(name, str) and name and normalize_config_key(name) not in exclude_norm:
                named.append(f)
            elif name is None:
                unnamed.append(f)

        if named:
            return sorted(named, key=lambda f: (_prio(f[3]), _safe_int(f[0], 0)))[0]
        if unnamed:
            return unnamed[0]
        return None

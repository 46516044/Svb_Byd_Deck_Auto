"""Runtime board state for Step3B battle decisions."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.game.domain import FollowerRuntimeState
from src.utils.card_filename import (
    normalize_card_base_name,
    parse_follower_stat_suffix,
    split_enhance_key,
)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _parse_hp(v: Any) -> Optional[int]:
    if isinstance(v, int):
        return int(v)
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


class BattleRuntimeState:
    """Tracks lightweight follower runtime states for target/settlement logic."""

    def __init__(self, *, logger: Any = None):
        self.logger = logger
        self.ours: List[FollowerRuntimeState] = []
        self.enemy: List[FollowerRuntimeState] = []

    def reset(self, *, reason: str = "") -> None:
        self.ours = []
        self.enemy = []
        if reason:
            self._debug(f"reset: {reason}")

    def sync_ours(self, followers: Sequence[Sequence[Any]]) -> List[FollowerRuntimeState]:
        self.ours = self._sync_side(
            existing=self.ours,
            scanned=followers,
            side="ours",
            with_hp=False,
            ward_positions=None,
        )
        self._drop_dead(self.ours)
        return list(self.ours)

    def sync_enemy(
        self,
        enemy_followers: Sequence[Sequence[Any]],
        *,
        ward_positions: Optional[Sequence[Sequence[Any]]] = None,
    ) -> List[FollowerRuntimeState]:
        self.enemy = self._sync_side(
            existing=self.enemy,
            scanned=enemy_followers,
            side="enemy",
            with_hp=True,
            ward_positions=ward_positions,
        )
        self._drop_dead(self.enemy)
        return list(self.enemy)

    def mark_our_evolution(self, follower_pos: Sequence[Any], evolved_type: str) -> bool:
        state = self._find_state(self.ours, follower_pos)
        if state is None:
            return False
        mode = str(evolved_type or "none")
        if mode not in ("none", "normal", "super"):
            mode = "none"
        state.evolved_type = mode
        return True

    def mark_latest_play_origin(
        self,
        *,
        card_name: str,
        cfg_key: str,
    ) -> Optional[Tuple[int, int]]:
        """Mark the most likely newly played follower with its config key.

        Returns follower position when a target was tagged.
        """

        cfg = str(cfg_key or "")
        if not cfg:
            return None

        expected_base = normalize_card_base_name(str(card_name or ""))
        if not expected_base:
            b, _enh = split_enhance_key(cfg)
            expected_base = normalize_card_base_name(str(b or ""))

        def _is_match(st: FollowerRuntimeState) -> bool:
            st_base = normalize_card_base_name(str(getattr(st, "base_name", "") or ""))
            if expected_base and st_base and st_base == expected_base:
                return True
            raw = normalize_card_base_name(str(getattr(st, "raw_name", "") or ""))
            if expected_base and raw and raw == expected_base:
                return True
            return False

        candidates = [st for st in list(self.ours or []) if _is_match(st)]
        if not candidates:
            candidates = list(self.ours or [])
        if not candidates:
            return None

        # Prefer rightmost, and prefer states without a specific source key yet.
        picked = sorted(
            candidates,
            key=lambda st: (
                1 if (str(getattr(st, "source_cfg_key", "") or "") in ("", expected_base)) else 0,
                int(getattr(st, "x", 0) or 0),
            ),
            reverse=True,
        )[0]

        picked.source_cfg_key = cfg
        return (int(picked.x), int(picked.y))

    def get_effect_key_for_ours(
        self,
        *,
        follower_pos: Optional[Sequence[Any]],
        fallback_name: str = "",
    ) -> str:
        state = self._find_state(self.ours, follower_pos) if follower_pos is not None else None
        if state is not None:
            key = str(getattr(state, "source_cfg_key", "") or "")
            if key:
                return key
            base = str(getattr(state, "base_name", "") or "")
            if base:
                return base
            raw = str(getattr(state, "raw_name", "") or "")
            if raw:
                return raw
        return str(fallback_name or "")

    def find_ours_pos_by_cfg_key(
        self,
        *,
        cfg_key: str,
        fallback_name: str = "",
    ) -> Optional[Tuple[int, int]]:
        key = str(cfg_key or "")
        if not key:
            return None

        expected_base = normalize_card_base_name(str(fallback_name or ""))
        if not expected_base:
            b, _enh = split_enhance_key(key)
            expected_base = normalize_card_base_name(str(b or ""))

        exact = [
            st
            for st in list(self.ours or [])
            if str(getattr(st, "source_cfg_key", "") or "") == key
        ]
        if exact:
            picked = sorted(exact, key=lambda st: int(getattr(st, "x", 0) or 0), reverse=True)[0]
            return (int(picked.x), int(picked.y))

        if not expected_base:
            return None

        by_base = [
            st
            for st in list(self.ours or [])
            if normalize_card_base_name(str(getattr(st, "base_name", "") or "")) == expected_base
        ]
        if not by_base:
            return None

        picked = sorted(by_base, key=lambda st: int(getattr(st, "x", 0) or 0), reverse=True)[0]
        return (int(picked.x), int(picked.y))

    def apply_buff(
        self,
        *,
        source_pos: Optional[Sequence[Any]],
        target_mode: str,
        atk_delta: int,
        hp_delta: int,
    ) -> int:
        atk_v = _safe_int(atk_delta, 0)
        hp_v = _safe_int(hp_delta, 0)
        if atk_v == 0 and hp_v == 0:
            return 0

        mode = str(target_mode or "others")
        if mode not in ("others", "self"):
            mode = "others"

        source = self._find_state(self.ours, source_pos) if source_pos is not None else None
        changed = 0

        for st in self.ours:
            is_source = source is not None and st is source

            if mode == "self":
                if not is_source:
                    continue
            else:
                if is_source:
                    continue

            st.buff_atk += atk_v
            st.buff_hp += hp_v
            changed += 1

        return changed

    def apply_buff_others(
        self,
        *,
        source_pos: Optional[Sequence[Any]],
        amount: int,
    ) -> int:
        value = _safe_int(amount, 0)
        return self.apply_buff(
            source_pos=source_pos,
            target_mode="others",
            atk_delta=value,
            hp_delta=value,
        )

    def apply_buff_self(
        self,
        *,
        source_pos: Optional[Sequence[Any]],
        amount: int,
    ) -> int:
        value = _safe_int(amount, 0)
        return self.apply_buff(
            source_pos=source_pos,
            target_mode="self",
            atk_delta=value,
            hp_delta=value,
        )

    def pick_enemy_target(
        self,
        *,
        attacker_pos: Sequence[Any],
        ward_only: bool = False,
    ) -> Tuple[Optional[FollowerRuntimeState], Dict[str, Any]]:
        attacker = self._find_state(self.ours, attacker_pos)
        attacker_atk = attacker.effective_atk() if attacker is not None else None

        candidates = [e for e in self.enemy if (e.is_ward if ward_only else True)]
        if not candidates:
            return None, {
                "mode": "no_candidates",
                "attacker_atk": attacker_atk,
                "ward_only": bool(ward_only),
            }

        hp_known = [(c, c.current_hp()) for c in candidates if c.current_hp() is not None]

        if attacker_atk is not None and hp_known:
            lethal: List[Tuple[FollowerRuntimeState, int, int]] = []
            for c, hp in hp_known:
                hp_i = _safe_int(hp, 0)
                residual = hp_i - int(attacker_atk)
                if residual <= 0:
                    lethal.append((c, hp_i, residual))
            if lethal:
                target, hp_i, residual = max(lethal, key=lambda it: (int(it[2]), int(it[0].x)))
                return target, {
                    "mode": "kill_overflow",
                    "attacker_atk": attacker_atk,
                    "target_hp": hp_i,
                    "residual": residual,
                    "ward_only": bool(ward_only),
                }

        if hp_known:
            target, hp_i = min(
                hp_known,
                key=lambda it: (_safe_int(it[1], 999), -_safe_int(it[0].x, 0)),
            )
            return target, {
                "mode": "fallback_min_hp",
                "attacker_atk": attacker_atk,
                "target_hp": _safe_int(hp_i, 0),
                "ward_only": bool(ward_only),
            }

        target = max(candidates, key=lambda it: int(it.x))
        return target, {
            "mode": "fallback_rightmost_unknown_hp",
            "attacker_atk": attacker_atk,
            "target_hp": None,
            "ward_only": bool(ward_only),
        }

    def apply_local_combat(
        self,
        *,
        attacker_pos: Sequence[Any],
        target_pos: Sequence[Any],
    ) -> Dict[str, Any]:
        attacker = self._find_state(self.ours, attacker_pos)
        target = self._find_state(self.enemy, target_pos)
        if target is None:
            return {"applied": False}

        attacker_atk = attacker.effective_atk() if attacker is not None else None
        target_atk = target.effective_atk()

        target_hp_before = target.current_hp()
        if attacker_atk is not None:
            if target.hp0 is not None:
                target.damage_taken += int(attacker_atk)
            if target.observed_hp is not None:
                target.observed_hp = max(0, int(target.observed_hp) - int(attacker_atk))

        target_hp_after = target.current_hp()
        target_dead = target_hp_after is not None and int(target_hp_after) <= 0

        attacker_hp_before = attacker.current_hp() if attacker is not None else None
        attacker_dead = False

        if attacker is not None and attacker.evolved_type != "super":
            if target_atk is not None and attacker.hp0 is not None:
                attacker.damage_taken += int(target_atk)
                if attacker.observed_hp is not None:
                    attacker.observed_hp = max(0, int(attacker.observed_hp) - int(target_atk))
                attacker_hp_after = attacker.current_hp()
                attacker_dead = attacker_hp_after is not None and int(attacker_hp_after) <= 0

        if target_dead:
            self.enemy = [e for e in self.enemy if e is not target]
        if attacker is not None and attacker_dead:
            self.ours = [o for o in self.ours if o is not attacker]

        return {
            "applied": True,
            "attacker_name": getattr(attacker, "base_name", "") if attacker is not None else "",
            "attacker_atk": attacker_atk,
            "attacker_hp_before": attacker_hp_before,
            "attacker_dead": attacker_dead,
            "target_name": target.base_name,
            "target_hp_before": target_hp_before,
            "target_hp_after": target_hp_after,
            "target_dead": target_dead,
        }

    def _sync_side(
        self,
        *,
        existing: Sequence[FollowerRuntimeState],
        scanned: Sequence[Sequence[Any]],
        side: str,
        with_hp: bool,
        ward_positions: Optional[Sequence[Sequence[Any]]],
    ) -> List[FollowerRuntimeState]:
        used: set[int] = set()
        out: List[FollowerRuntimeState] = []
        wards = list(ward_positions or [])

        for item in list(scanned or []):
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            x = _safe_int(item[0], 0)
            y = _safe_int(item[1], 0)
            ftype = str(item[2] if len(item) > 2 else "normal")

            idx = self._match_existing_index(existing, used, x, y)
            if idx is not None:
                st = existing[idx]
                used.add(int(idx))
            else:
                st = FollowerRuntimeState(side=side)

            st.side = side
            st.x = int(x)
            st.y = int(y)
            st.follower_type = ftype

            if side == "enemy":
                st.is_ward = any(abs(int(x) - _safe_int(w[0], 0)) < 50 for w in wards if len(w) >= 1)

            raw_name = ""
            if len(item) > 3 and isinstance(item[3], str):
                raw_name = str(item[3] or "")
            if raw_name:
                st.raw_name = raw_name
                base_name, atk0, hp0 = parse_follower_stat_suffix(raw_name)
                st.base_name = base_name if base_name else raw_name
                if atk0 is not None:
                    st.atk0 = int(atk0)
                if hp0 is not None:
                    st.hp0 = int(hp0)
            elif not st.base_name:
                st.base_name = st.raw_name or ""

            if with_hp:
                hp_seen = _parse_hp(item[3] if len(item) > 3 else None)
                if hp_seen is not None:
                    hp_seen_i = int(hp_seen)
                    st.observed_hp = hp_seen_i
                    if st.hp0 is None:
                        st.hp0 = hp_seen_i
                    total = int(st.hp0 or hp_seen_i) + int(st.evolution_bonus()) + int(st.buff_hp)
                    if hp_seen_i > total:
                        st.hp0 = hp_seen_i - int(st.evolution_bonus()) - int(st.buff_hp)
                        st.damage_taken = 0
                    else:
                        st.damage_taken = max(0, total - hp_seen_i)

            out.append(st)

        out = sorted(out, key=lambda s: int(s.x), reverse=True)
        return out

    def _match_existing_index(
        self,
        existing: Sequence[FollowerRuntimeState],
        used: Iterable[int],
        x: int,
        y: int,
    ) -> Optional[int]:
        used_set = set(used)
        best_idx = None
        best_score = 10**9
        for i, st in enumerate(list(existing or [])):
            if i in used_set:
                continue
            dx = abs(int(st.x) - int(x))
            dy = abs(int(st.y) - int(y))
            if dx > 72 or dy > 90:
                continue
            score = dx * 2 + dy
            if score < best_score:
                best_score = score
                best_idx = i
        return best_idx

    def _find_state(
        self,
        states: Sequence[FollowerRuntimeState],
        pos: Sequence[Any],
    ) -> Optional[FollowerRuntimeState]:
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            return None
        x = _safe_int(pos[0], 0)
        y = _safe_int(pos[1], 0)

        best: Optional[FollowerRuntimeState] = None
        best_score = 10**9
        for st in list(states or []):
            dx = abs(int(st.x) - int(x))
            dy = abs(int(st.y) - int(y))
            if dx > 84 or dy > 110:
                continue
            score = dx * 2 + dy
            if score < best_score:
                best_score = score
                best = st
        return best

    def _drop_dead(self, states: List[FollowerRuntimeState]) -> None:
        keep: List[FollowerRuntimeState] = []
        for st in list(states or []):
            hp = st.current_hp()
            if hp is not None and int(hp) <= 0:
                continue
            keep.append(st)
        states[:] = keep

    def _debug(self, msg: str) -> None:
        try:
            if self.logger is not None:
                self.logger.debug(f"[Runtime] {msg}")
        except Exception:
            pass

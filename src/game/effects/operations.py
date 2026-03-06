"""Operation executors for Step3A effects."""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Tuple

from src.config.game_constants import BLANK_CLICK_POSITION, BLANK_CLICK_RANDOM

from .target_resolver import resolve_targets


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


class OperationExecutor:
    @staticmethod
    def select_option(ctx: Any, *, index: Any) -> bool:
        ds = getattr(ctx, "device_state", None)
        if ds is None:
            return False
        idx = _safe_int(index, 0)
        if idx == 1:
            x, y = 748, 328
        elif idx == 2:
            x, y = 724, 429
        else:
            return False

        try:
            ds.logger.info(f"[Effect] select_option index={idx}")
        except Exception:
            pass

        time.sleep(0.3)
        ds.u2_device.click(x + random.randint(-15, 15), y + random.randint(-2, 2))
        time.sleep(0.5)
        return True

    @staticmethod
    def cancel_action(ctx: Any) -> bool:
        ds = getattr(ctx, "device_state", None)
        if ds is None:
            return False
        try:
            ds.logger.info("[Effect] cancel_action")
        except Exception:
            pass
        ds.u2_device.click(
            BLANK_CLICK_POSITION[0] + random.randint(-BLANK_CLICK_RANDOM, BLANK_CLICK_RANDOM),
            BLANK_CLICK_POSITION[1] + random.randint(-BLANK_CLICK_RANDOM, BLANK_CLICK_RANDOM),
        )
        time.sleep(0.2)
        return True

    @staticmethod
    def buff(ctx: Any, *, target: Any, atk_delta: Any, hp_delta: Any) -> bool:
        ds = getattr(ctx, "device_state", None)
        if ds is None:
            return False

        target_mode = str(target or "others")
        if target_mode not in ("others", "self"):
            target_mode = "others"

        atk_val = _safe_int(atk_delta, 0)
        hp_val = _safe_int(hp_delta, 0)

        runtime = getattr(ds, "battle_runtime_state", None)
        if runtime is None or not hasattr(runtime, "apply_buff"):
            try:
                ds.logger.warning("[Effect] buff skipped: runtime unavailable")
            except Exception:
                pass
            return True

        source_pos = getattr(ctx, "follower_pos", None) or getattr(ctx, "attack_source_pos", None)
        if source_pos is None and runtime is not None and hasattr(runtime, "find_ours_pos_by_cfg_key"):
            try:
                source_pos = runtime.find_ours_pos_by_cfg_key(
                    cfg_key=str(getattr(ctx, "cfg_key", "") or ""),
                    fallback_name=str(
                        getattr(ctx, "card_name", "")
                        or getattr(ctx, "follower_name", "")
                        or ""
                    ),
                )
            except Exception:
                source_pos = None
        try:
            changed = int(
                runtime.apply_buff(
                    source_pos=source_pos,
                    target_mode=target_mode,
                    atk_delta=atk_val,
                    hp_delta=hp_val,
                )
            )
        except Exception:
            changed = 0

        try:
            ds.logger.info(
                f"[Effect] buff mode={target_mode} atk_delta={atk_val} hp_delta={hp_val} affected={changed}"
            )
        except Exception:
            pass
        return True

    @staticmethod
    def buff_others(ctx: Any, *, amount: Any) -> bool:
        value = _safe_int(amount, 0)
        return OperationExecutor.buff(
            ctx,
            target="others",
            atk_delta=value,
            hp_delta=value,
        )

    @staticmethod
    def select_targets(
        ctx: Any,
        *,
        target: Any,
        count: Any = 1,
        distinct_xy: Any = True,
        is_select_ui: Any = True,
    ) -> bool:
        ds = getattr(ctx, "device_state", None)
        if ds is None:
            return False

        target_kind = ""
        try:
            if isinstance(target, dict):
                target_kind = str(target.get("kind") or "")
        except Exception:
            target_kind = ""

        # Allow animations / target UI to settle.
        time.sleep(0.4)

        n = max(1, _safe_int(count, 1))
        positions: List[Tuple[int, int]] = resolve_targets(
            ctx,
            target=target,
            count=n,
            distinct_xy=bool(distinct_xy),
            is_select_ui=bool(is_select_ui),
        )
        if not positions:
            try:
                ds.logger.warning(f"[Effect] select_targets: no targets (target={target})")
            except Exception:
                pass
            try:
                fail_kinds = getattr(ctx, "select_targets_fail_kinds", None)
                if isinstance(fail_kinds, list):
                    if target_kind:
                        fail_kinds.append(target_kind)
                else:
                    setattr(ctx, "select_targets_fail_kinds", [target_kind] if target_kind else [])
            except Exception:
                pass
            return False

        try:
            ds.logger.info(f"[Effect] select_targets count={len(positions)}/{n}")
        except Exception:
            pass

        for i, (x, y) in enumerate(list(positions)[:n], 1):
            ds.u2_device.click(int(x), int(y))
            try:
                ds.logger.info(f"[Effect] click_target {i}: ({int(x)},{int(y)})")
            except Exception:
                pass
            time.sleep(0.35)
        return True

    @staticmethod
    def legacy_action(ctx: Any, *, action: Any) -> bool:
        """Compatibility op for Step2B `action` strings."""

        act = str(action or "")
        if act == "attack_enemy_follower_hp_less_than_4":
            return OperationExecutor.select_targets(
                ctx,
                target={"kind": "enemy_follower", "selector": "hp_leq", "params": {"max_hp": 3}},
                count=1,
                distinct_xy=True,
                is_select_ui=True,
            )
        if act == "attack_two_enemy_followers_hp_less_than_4":
            return OperationExecutor.select_targets(
                ctx,
                target={"kind": "enemy_follower", "selector": "hp_leq", "params": {"max_hp": 3}},
                count=2,
                distinct_xy=True,
                is_select_ui=True,
            )
        if act == "attack_two_enemy_followers_hp_highest":
            return OperationExecutor.select_targets(
                ctx,
                target={"kind": "enemy_follower", "selector": "highest_hp", "params": {}},
                # Keep legacy runtime behavior (was implemented as 1 click).
                count=1,
                distinct_xy=True,
                is_select_ui=True,
            )
        if act == "our_followers_with_evolution":
            return OperationExecutor.select_targets(
                ctx,
                target={
                    "kind": "friendly_follower",
                    "selector": "by_evolve_priority",
                    "params": {"exclude_self": True},
                },
                count=1,
                distinct_xy=True,
                is_select_ui=False,
            )
        return False

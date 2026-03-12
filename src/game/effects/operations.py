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
    def select_option_by_our_followers(
        ctx: Any,
        *,
        threshold: Any = 3,
        le_option: Any = 1,
        gt_option: Any = 2,
    ) -> bool:
        ds = getattr(ctx, "device_state", None)
        if ds is None:
            return False

        threshold_i = _safe_int(threshold, 3)
        le_option_i = _safe_int(le_option, 1)
        gt_option_i = _safe_int(gt_option, 2)

        follower_count = 0
        try:
            screenshot = ds.take_screenshot()
            if screenshot is not None and ds.game_manager is not None:
                followers = ds.game_manager.scan_our_followers(
                    screenshot,
                    extra_shots=0,
                    with_names=False,
                )
                follower_count = len(list(followers or []))
        except Exception:
            follower_count = 0

        selected_option = le_option_i if follower_count <= threshold_i else gt_option_i
        try:
            ds.logger.info(
                "[Effect] select_option_by_our_followers "
                f"count={follower_count} threshold={threshold_i} -> option={selected_option}"
            )
        except Exception:
            pass

        return OperationExecutor.select_option(ctx, index=selected_option)

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
    def buff(
        ctx: Any,
        *,
        target: Any,
        atk_delta: Any,
        hp_delta: Any,
        attack_times: Any = None,
    ) -> bool:
        ds = getattr(ctx, "device_state", None)
        if ds is None:
            return False

        target_mode = str(target or "others")
        if target_mode not in ("others", "self"):
            target_mode = "others"

        atk_val = _safe_int(atk_delta, 0)
        hp_val = _safe_int(hp_delta, 0)
        attack_times_val = None
        if attack_times is not None:
            attack_times_val = max(1, _safe_int(attack_times, 1))

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
                    attack_times=attack_times_val,
                    round_index=getattr(ds, "current_round_count", None),
                )
            )
        except Exception:
            changed = 0

        try:
            ds.logger.info(
                "[Effect] buff "
                f"mode={target_mode} atk_delta={atk_val} hp_delta={hp_val} "
                f"attack_times={attack_times_val if attack_times_val is not None else '-'} "
                f"affected={changed}"
            )
        except Exception:
            pass
        return True

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
            success_kinds = getattr(ctx, "select_targets_success_kinds", None)
            if isinstance(success_kinds, list):
                if target_kind and target_kind not in success_kinds:
                    success_kinds.append(target_kind)
            else:
                setattr(
                    ctx,
                    "select_targets_success_kinds",
                    [target_kind] if target_kind else [],
                )

            fail_kinds = getattr(ctx, "select_targets_fail_kinds", None)
            if isinstance(fail_kinds, list) and target_kind:
                while target_kind in fail_kinds:
                    fail_kinds.remove(target_kind)
        except Exception:
            pass

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

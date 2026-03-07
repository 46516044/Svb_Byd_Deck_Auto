"""
出牌特殊操作处理模块
处理出牌时的特殊操作（如选择目标等）
"""

import time
import random
from typing import TYPE_CHECKING
from src.config.card_priorities import is_high_priority_card
from src.game.game_actions import human_like_drag
from src.game.policy.effects import get_card_effect_steps

from src.config.strategy_effects import normalize_effect_steps_to_ops
from src.game.effects import EffectEngine, HandCardContext

if TYPE_CHECKING:
    from src.device.device_state import DeviceState

class CardPlaySpecialActions:
    """出牌特殊操作处理类"""
    
    def __init__(self, device_state: 'DeviceState'):
        self.device_state = device_state
    
    def play_single_card(self, card):
        """打出单张牌"""
        self._extra_cost_bonus = 0
        self._should_not_consume_cost = False
        self._should_remove_from_hand = False

        center_x, center_y = card['center']
        target_x = center_x + 40
        card_name = card.get('name', '')
        # Enhance variants can use a separate config key.
        cfg_key = card.get('_config_key') or card.get('config_key') or card_name

        # Prefer config-driven effects (Step3A op schema; legacy steps will be normalized).
        steps = get_card_effect_steps(
            self.device_state.config, card_name=str(cfg_key), trigger="on_play"
        )
        if (not steps) and str(cfg_key) != str(card_name):
            steps = get_card_effect_steps(
                self.device_state.config, card_name=str(card_name), trigger="on_play"
            )
        ops = normalize_effect_steps_to_ops(steps)

        if ops:
            # Normal play drag, then run post-play ops.
            self._default_card_play(center_x, center_y, target_x)
            time.sleep(0.2)

            source_pos = self._tag_played_follower_origin(
                card_name=str(card_name or ""),
                cfg_key=str(cfg_key or ""),
            )

            ctx = HandCardContext(
                device_state=self.device_state,
                card_name=str(card_name),
                cfg_key=str(cfg_key),
                card_center=(int(center_x), int(center_y)),
                play_target=(int(target_x), 400),
                follower_pos=source_pos,
                card=dict(card or {}),
            )
            run_result = EffectEngine.run_ops(ops, ctx=ctx, trigger_id="on_play")

            # Unified failure policy for enemy_follower targeting:
            # - no cost consumption
            # - ignore this card for current round
            fail_kinds = list(getattr(ctx, "select_targets_fail_kinds", []) or [])
            success_kinds = set(str(k) for k in list(getattr(ctx, "select_targets_success_kinds", []) or []))
            enemy_target_failed = any(
                str(k) == "enemy_follower" and "enemy_follower" not in success_kinds
                for k in fail_kinds
            )
            if enemy_target_failed:
                self.device_state.logger.info(
                    f"[{card_name}] 敌方随从目标选择失败，回退为本回合忽略且不耗费"
                )
                try:
                    from src.game.effects.operations import OperationExecutor

                    OperationExecutor.cancel_action(ctx)
                except Exception:
                    pass
                self._should_not_consume_cost = True
                self._should_remove_from_hand = True
                return False

            if run_result.aborted:
                self.device_state.logger.warning(
                    f"[{card_name}] on_play effects aborted，回退为本回合忽略且不耗费"
                )
                self._should_not_consume_cost = True
                self._should_remove_from_hand = True
                return False

        else:
            # 普通卡牌，正常打出
            self._default_card_play(center_x, center_y, target_x)
        
        # 特殊费用处理：勇武的堕天使奥莉薇打出后增加2点费用
        if card_name == "勇武的堕天使奥莉薇":
            time.sleep(5)
            self.device_state.logger.info(f"检测到打出{card_name}，增加2点费用")
            # 这里需要在调用方处理费用增加，我们通过返回值来通知
            self._extra_cost_bonus = 2
        elif card_name == "白银骑士团团长艾蜜莉亚":
            time.sleep(5)
            self.device_state.logger.info(f"检测到打出{card_name}，增加3点费用")
            # 这里需要在调用方处理费用增加，我们通过返回值来通知
            self._extra_cost_bonus = 3
        elif card_name == "纯白圣女贞德":
            time.sleep(5)
            self.device_state.logger.info(f"检测到打出{card_name}，等待5s")
        else:
            self._extra_cost_bonus = 0
        
        # 如果是高优先级卡牌，多等一会
        if is_high_priority_card(str(cfg_key), self.device_state.config) or is_high_priority_card(
            str(card_name), self.device_state.config
        ):
            time.sleep(1)
        
        time.sleep(0.5)
        return True

    def _tag_played_follower_origin(self, *, card_name: str, cfg_key: str):
        """Try to tag the just-played follower with its cfg key."""

        runtime = getattr(self.device_state, "battle_runtime_state", None)
        game_manager = getattr(self.device_state, "game_manager", None)
        if runtime is None or game_manager is None:
            return None

        try:
            self.device_state.sleep(1.0)
            screenshot = self.device_state.take_screenshot()
            if screenshot is None:
                return None

            followers = game_manager.scan_our_followers(
                screenshot,
                extra_shots=0,
                sort_desc=True,
                shot_delay_range=(0.05, 0.10),
                with_names=True,
            )

            if followers:
                runtime.sync_ours(followers)
            pos = runtime.mark_latest_play_origin(card_name=str(card_name or ""), cfg_key=str(cfg_key or ""))
            return pos
        except Exception:
            return None

    def _default_card_play(self, center_x, center_y, target_x):
        """默认卡牌打出"""
        human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)

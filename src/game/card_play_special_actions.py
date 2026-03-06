"""
出牌特殊操作处理模块
处理出牌时的特殊操作（如选择目标等）
"""

import time
import random
import logging
from typing import TYPE_CHECKING
from src.config.card_priorities import is_high_priority_card
from src.config.game_constants import DEFAULT_ATTACK_TARGET, DEFAULT_ATTACK_RANDOM
from src.game.game_actions import human_like_drag
from src.game.policy.targets import TargetSelector
from src.game.policy.effects import get_card_effect_steps
from src.utils.card_filename import normalize_config_key

from src.config.strategy_effects import normalize_effect_steps_to_ops, parse_select_option
from src.game.effects import EffectEngine, HandCardContext

if TYPE_CHECKING:
    from src.device.device_state import DeviceState

logger = logging.getLogger(__name__)

# 获取卡牌模式选项配置
def get_card_mode_options(config=None):
    """获取卡牌模式选项配置。

    优先使用传入的运行期 config（如 device_state.config），避免高频磁盘读取。
    """
    if isinstance(config, dict):
        return config.get("card_mode_options", {}) or {}

    # Avoid business-module disk IO; callers should pass runtime config.
    return {}

# 获取卡牌进化模式选项配置
def get_card_evolve_mode_options(config=None):
    """获取卡牌进化模式选项配置。

    优先使用传入的运行期 config（如 device_state.config），避免高频磁盘读取。
    """
    if isinstance(config, dict):
        return config.get("card_evolve_mode_options", {}) or {}

    # Avoid business-module disk IO; callers should pass runtime config.
    return {}


def _lookup_by_normalized_key(mapping, *keys):
    """Lookup config value by direct key or normalized base key."""

    if not isinstance(mapping, dict) or not mapping:
        return None

    for key in list(keys or []):
        ks = str(key or "")
        if ks in mapping:
            return mapping.get(ks)

    normalized_mapping = {}
    for mk, mv in dict(mapping).items():
        nk = normalize_config_key(str(mk or ""))
        if nk and nk not in normalized_mapping:
            normalized_mapping[nk] = mv

    for key in list(keys or []):
        nk = normalize_config_key(str(key or ""))
        if nk in normalized_mapping:
            return normalized_mapping.get(nk)

    return None

class CardPlaySpecialActions:
    """出牌特殊操作处理类"""
    
    def __init__(self, device_state: 'DeviceState'):
        self.device_state = device_state
    
    def play_single_card(self, card):
        """打出单张牌"""
        cost = card.get('cost', 0)
        center_x, center_y = card['center']
        target_x = center_x + 40
        card_name = card.get('name', '')
        # Enhance variants can use a separate config key.
        cfg_key = card.get('_config_key') or card.get('config_key') or card_name

        card_mode_options = get_card_mode_options(self.device_state.config)
        mode_option = None

        # Prefer config-driven effects (Step3A op schema; legacy steps will be normalized).
        steps = get_card_effect_steps(
            self.device_state.config, card_name=str(cfg_key), trigger="on_play"
        )
        if (not steps) and str(cfg_key) != str(card_name):
            steps = get_card_effect_steps(
                self.device_state.config, card_name=str(card_name), trigger="on_play"
            )
        ops = normalize_effect_steps_to_ops(steps)

        has_select_option = any(
            isinstance(o, dict) and str(o.get("op") or "") == "select_option" for o in ops
        )
        legacy_target_type_step = None
        for o in ops:
            if not isinstance(o, dict) or str(o.get("op") or "") != "legacy_target_type":
                continue
            tt = o.get("target_type")
            if isinstance(tt, str) and tt:
                legacy_target_type_step = o
                break
        
        # Priority (prefer config-driven effects):
        # 1) effects ops (select_option/select_targets/...)  [Step3A]
        # 2) legacy_target_type (handled by legacy dispatcher)
        # 3) legacy card_mode_options (mode)
        if ops:
            # Legacy target_type is handled by the existing dispatcher.
            # Preserve old precedence: if any supported new-engine ops exist,
            # prefer the op engine and ignore legacy_target_type.
            has_engine_ops = any(
                isinstance(o, dict)
                and str(o.get("op") or "")
                in (
                    "select_option",
                    "select_targets",
                    "cancel_action",
                    "buff",
                )
                for o in ops
            )

            if (
                legacy_target_type_step is not None
                and (not has_select_option)
                and (not has_engine_ops)
            ):
                target_type = str(legacy_target_type_step.get("target_type") or "")
                result = self._dispatch_play_target_type(
                    target_type, card_name, center_x, center_y, target_x
                )
                if result is False:
                    self._should_not_consume_cost = True
                    self._should_remove_from_hand = True
                    return False
            else:
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
                ops_to_run = [
                    o
                    for o in ops
                    if isinstance(o, dict) and str(o.get("op") or "") != "legacy_target_type"
                ]
                run_result = EffectEngine.run_ops(ops_to_run, ctx=ctx, trigger_id="on_play")

                # Unified failure policy for enemy_follower targeting:
                # - no cost consumption
                # - ignore this card for current round
                fail_kinds = list(getattr(ctx, "select_targets_fail_kinds", []) or [])
                enemy_target_failed = any(str(k) == "enemy_follower" for k in fail_kinds)
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
            mode_option = _lookup_by_normalized_key(card_mode_options, str(cfg_key), str(card_name))

        if mode_option is not None:
            self.device_state.logger.info(f"检测到模式卡牌{card_name}，选项: {mode_option}")

            human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
            time.sleep(0.2)

            if mode_option == "选项1":
                click_x, click_y = 748, 328
                self.device_state.logger.info(
                    f"执行选项1操作，点击坐标: ({click_x}, {click_y})"
                )
                time.sleep(0.3)
                self.device_state.u2_device.click(
                    click_x + random.randint(-15, 15),
                    click_y + random.randint(-2, 2),
                )
                time.sleep(0.5)
            elif mode_option == "选项2":
                click_x, click_y = 724, 429
                self.device_state.logger.info(
                    f"执行选项2操作，点击坐标: ({click_x}, {click_y})"
                )
                time.sleep(0.3)
                self.device_state.u2_device.click(
                    click_x + random.randint(-15, 15),
                    click_y + random.randint(-2, 2),
                )
                time.sleep(0.5)

        elif not ops:
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

    def _dispatch_play_target_type(self, target_type, card_name, center_x, center_y, target_x):
        """Dispatch legacy target_type handlers.

        Returns:
            - False for the special "return point" case (do not consume cost)
            - True/None otherwise
        """

        if target_type == "enemy_player":
            self._handle_enemy_player_target(card_name, center_x, center_y, target_x)
            return True
        if target_type == "shield_or_highest_hp":
            self._handle_shield_or_highest_hp_target(card_name, center_x, center_y, target_x)
            return True
        if target_type == "double_enemy":
            self._handle_double_destroy(card_name, center_x, center_y, target_x)
            return True
        if target_type == "enemy_followers_hp_less_than_6":
            self._handle_enemy_followers_hp_less_than_6_target(card_name, center_x, center_y, target_x)
            return True
        if target_type == "scan_our_follower_to_choose":
            self._handle_scan_our_follower_to_choose_target(card_name, center_x, center_y, target_x)
            return True
        if target_type == "shield_or_highest_hp_no_enemy_retrun_point":
            res = self._handle_shield_or_highest_hp_noenemy_retrun_point_target(
                card_name, center_x, center_y, target_x
            )
            return False if res is False else True

        # Unknown target type: safe fallback
        self._default_card_play(center_x, center_y, target_x)
        return True
    
    def _handle_enemy_player_target(self, card_name, center_x, center_y, target_x):
        """处理选择敌方玩家目标"""
        self.device_state.logger.info(f"检测到{card_name}，划出卡牌后选择敌方玩家目标")
        # 划出卡牌
        human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
        time.sleep(0.8)  # 等待
        
        enemy_x = DEFAULT_ATTACK_TARGET[0] + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
        enemy_y = DEFAULT_ATTACK_TARGET[1] + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
        self.device_state.u2_device.click(enemy_x, enemy_y)
        self.device_state.logger.info(f"{card_name}选择敌方玩家目标: ({enemy_x}, {enemy_y})")
        time.sleep(0.5)  # 等待0.1秒
    
    def _handle_double_destroy(self, card_name, center_x, center_y, target_x):
        self.device_state.logger.info(f"检测到{card_name}，执行两次破坏") 
        # 检测敌方随从
        screenshot = self.device_state.take_screenshot()
        if screenshot:
            enemy_followers = self._scan_enemy_followers(screenshot)
            if enemy_followers:
                self.device_state.logger.info("检测到敌方随从，划出卡牌后破坏血量最高的敌方随从")
                # 划出卡牌
                human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
                time.sleep(0.9)  # 等待0.2秒
                try:
                    picked = TargetSelector.enemy_followers_highest_hp(
                        enemy_followers, n=2, distinct_xy=True
                    )
                    if not picked:
                        self.device_state.logger.info("未检测到敌方随从，不消耗能量点，直接返回")
                        return False

                    if len(picked) == 1:
                        fx, fy = int(picked[0][0]), int(picked[0][1])
                        self.device_state.u2_device.click(fx, fy)
                        self.device_state.logger.info(f"点击血量最高的敌方随从位置: ({fx}, {fy})")
                    else:
                        for idx, f in enumerate(picked, 1):
                            fx, fy = int(f[0]), int(f[1])
                            self.device_state.u2_device.click(fx, fy)
                            self.device_state.logger.info(f"第{idx}次点击目标随从位置: ({fx}, {fy})")
                            time.sleep(0.35)

                    time.sleep(2.7)
                except Exception as e:
                    self.device_state.logger.warning(f"选择敌方随从时出错: {str(e)}")
                    time.sleep(0.6)
            else:
                self.device_state.logger.info("未检测到敌方随从，不消耗能量点，直接返回")
                # 不划出卡牌，不消耗能量点
                return False
        else:
            self.device_state.logger.warning("无法获取截图，不消耗能量点，直接返回")
            return False                       
        
    
    def _handle_shield_or_highest_hp_target(self, card_name, center_x, center_y, target_x):
        """处理优先破坏护盾，否则选择血量最高的敌方随从"""
        self.device_state.logger.info(f"检测到{card_name}，先检测护盾情况")
        # 检测护盾
        shield_targets = self._scan_shield_targets()
        shield_detected = bool(shield_targets)
        
        if shield_detected:
            self.device_state.logger.info("检测到护盾，划出卡牌后破坏护盾随从")
            # 划出卡牌
            human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
            time.sleep(0.9)  # 等待

            # 优先点击“护盾随从中血量最高”的目标。
            shield_pick = None
            try:
                screenshot = self.device_state.take_screenshot()
                if screenshot is not None:
                    enemy_followers = self._scan_enemy_followers(screenshot, is_select=True)
                    shield_pick = TargetSelector.enemy_follower_highest_hp_in_wards(
                        enemy_followers,
                        shield_targets,
                    )
            except Exception:
                shield_pick = None

            if shield_pick is not None:
                shield_x, shield_y = int(shield_pick[0]), int(shield_pick[1])
                hp_text = shield_pick[3] if len(shield_pick) > 3 else "?"
                self.device_state.u2_device.click(shield_x, shield_y)
                self.device_state.logger.info(
                    f"点击护盾中血量最高随从: ({shield_x}, {shield_y}) HP={hp_text}"
                )
            else:
                # 兜底：护盾列表第一个。
                shield_x, shield_y = shield_targets[0]
                self.device_state.u2_device.click(shield_x, shield_y)
                self.device_state.logger.info(f"点击护盾随从位置(兜底): ({shield_x}, {shield_y})")
        else:
            self.device_state.logger.info("未检测到护盾，尝试检测血量最高的敌方随从")
            # 划出卡牌
            human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
            time.sleep(0.9)  # 等待0.2秒
            
            # 检测敌方随从
            screenshot = self.device_state.take_screenshot()
            if screenshot:
                enemy_followers = self._scan_enemy_followers(screenshot, is_select=True)
                if enemy_followers:
                    # 找出血量最高的随从
                    try:
                        target = TargetSelector.enemy_follower_highest_hp(enemy_followers)
                        if target is None:
                            raise ValueError("no enemy follower target")
                        enemy_x, enemy_y = target[0], target[1]
                        enemy_x = int(enemy_x)
                        enemy_y = int(enemy_y)
                        # human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
                        # time.sleep(0.9)  # 等待0.2秒
                        self.device_state.u2_device.click(enemy_x, enemy_y)
                        self.device_state.logger.info(f"点击血量最高的敌方随从位置: ({enemy_x}, {enemy_y})")
                    except Exception as e:
                        self.device_state.logger.warning(f"选择敌方随从时出错: {str(e)}")
                else:
                    # human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
                    # time.sleep(0.9)  # 等待0.2秒
                    player_x = DEFAULT_ATTACK_TARGET[0] + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
                    player_y = DEFAULT_ATTACK_TARGET[1] + random.randint(-DEFAULT_ATTACK_RANDOM, DEFAULT_ATTACK_RANDOM)
                    self.device_state.logger.info("未检测到敌方随从，尝试检测敌方护符或者其他可选择目标")
                    time.sleep(0.5)  # 等待0.几秒
                    gm = self.device_state.game_manager
                    can_choosetargets = gm.card_can_choose_target_like_amulet() if gm is not None else None
                    if can_choosetargets:
                        for pos in can_choosetargets:
                            self.device_state.u2_device.click(pos[0], pos[1])
                            time.sleep(0.3)

                        self.device_state.u2_device.click(645+random.randint(-3, 3),232+random.randint(-2, 2))
                        time.sleep(0.3)
                        self.device_state.u2_device.click(player_x+random.randint(-3, 3), player_y+random.randint(-2, 2))
                        self.device_state.logger.info(f"选择了一个可破坏目标(护符之类)")
                    else:
                        self.device_state.u2_device.click(645+random.randint(-3, 3),232+random.randint(-2, 2))
                        time.sleep(0.3)
                        self.device_state.u2_device.click(player_x+random.randint(-3, 3), player_y+random.randint(-2, 2))
                        self.device_state.logger.info("未检测到可破坏目标")


        time.sleep(2.7)
    
    def _handle_shield_or_highest_hp_noenemy_retrun_point_target(self, card_name, center_x, center_y, target_x):
        """处理优先破坏护盾，否则选择血量最高的敌方随从，若未检测到敌方随从则不消耗能量点"""
        self.device_state.logger.info(f"检测到{card_name}，先检测护盾情况")
        # 检测护盾
        shield_targets = self._scan_shield_targets()
        shield_detected = bool(shield_targets)
        
        if shield_detected:
            self.device_state.logger.info("检测到护盾，划出卡牌后破坏护盾随从")
            # 划出卡牌
            human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
            time.sleep(0.9)  # 等待

            # 优先点击“护盾随从中血量最高”的目标。
            shield_pick = None
            try:
                screenshot = self.device_state.take_screenshot()
                if screenshot is not None:
                    enemy_followers = self._scan_enemy_followers(screenshot, is_select=True)
                    shield_pick = TargetSelector.enemy_follower_highest_hp_in_wards(
                        enemy_followers,
                        shield_targets,
                    )
            except Exception:
                shield_pick = None

            if shield_pick is not None:
                shield_x, shield_y = int(shield_pick[0]), int(shield_pick[1])
                hp_text = shield_pick[3] if len(shield_pick) > 3 else "?"
                self.device_state.u2_device.click(shield_x, shield_y)
                self.device_state.logger.info(
                    f"点击护盾中血量最高随从: ({shield_x}, {shield_y}) HP={hp_text}"
                )
            else:
                # 兜底：护盾列表第一个。
                shield_x, shield_y = shield_targets[0]
                self.device_state.u2_device.click(shield_x, shield_y)
                self.device_state.logger.info(f"点击护盾随从位置(兜底): ({shield_x}, {shield_y})")
            time.sleep(2.7)
        else:
            self.device_state.logger.info("未检测到护盾，检测敌方随从")
            # 检测敌方随从
            screenshot = self.device_state.take_screenshot()
            if screenshot:
                enemy_followers = self._scan_enemy_followers(screenshot)
                if enemy_followers:
                    self.device_state.logger.info("检测到敌方随从，划出卡牌后破坏血量最高的敌方随从")
                    # 划出卡牌
                    human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
                    time.sleep(0.9)  # 等待0.2秒
                    
                    # 找出血量最高的随从
                    try:
                        target = TargetSelector.enemy_follower_highest_hp(enemy_followers)
                        if target is None:
                            raise ValueError("no enemy follower target")
                        enemy_x, enemy_y = target[0], target[1]
                        enemy_x = int(enemy_x)
                        enemy_y = int(enemy_y)
                        self.device_state.u2_device.click(enemy_x, enemy_y)
                        self.device_state.logger.info(f"点击血量最高的敌方随从位置: ({enemy_x}, {enemy_y})")
                    except Exception as e:
                        self.device_state.logger.warning(f"选择敌方随从时出错: {str(e)}")
                    time.sleep(2.7)
                else:
                    self.device_state.logger.info("未检测到敌方随从，不消耗能量点，直接返回")
                    # 不划出卡牌，不消耗能量点
                    return False
            else:
                self.device_state.logger.warning("无法获取截图，不消耗能量点，直接返回")
                return False
    
    def _handle_enemy_followers_hp_less_than_6_target(self, card_name, center_x, center_y, target_x):
        """处理点击敌方随从血量小于等于5的随从"""
        screenshot = self.device_state.take_screenshot()
        if not screenshot:
            return

        enemy_followers = self._scan_enemy_followers(screenshot)
        target_leq = TargetSelector.enemy_follower_hp_leq(enemy_followers, max_hp=5)

        if target_leq is not None:
            # 划出该手牌
            human_like_drag(
                self.device_state.u2_device, center_x, center_y, target_x, 400
            )
            time.sleep(0.9)

            self.device_state.logger.info(
                f"[划出{card_name}]，点击血量最大敌方随从: ({target_leq[0]}, {target_leq[1]}) HP={target_leq[3]}"
            )
            self.device_state.u2_device.click(int(target_leq[0]), int(target_leq[1]))
            time.sleep(0.5)
            return

        # 没有血量<=5的随从：检查是否有其他敌方随从
        if enemy_followers:
            self.device_state.logger.info(
                f"划出[{card_name}]，未检测到血量小于5的敌方随从，选择血量最大的敌方随从"
            )
            human_like_drag(
                self.device_state.u2_device, center_x, center_y, target_x, 400
            )
            time.sleep(0.9)

            try:
                target = TargetSelector.enemy_follower_highest_hp(enemy_followers)
                if target is None:
                    raise ValueError("no enemy follower target")
                enemy_x, enemy_y, _, hp = target
                enemy_x = int(enemy_x)
                enemy_y = int(enemy_y)
                self.device_state.u2_device.click(enemy_x, enemy_y)
                self.device_state.logger.info(
                    f"划出[{card_name}]，点击血量最大的敌方随从: ({enemy_x}, {enemy_y}) HP={hp}"
                )
            except Exception as e:
                self.device_state.logger.warning(
                    f"划出[{card_name}]，选择敌方随从时出错: {str(e)}"
                )

            time.sleep(0.5)
            return

        # 一个敌方随从都没有，点击指定位置
        self.device_state.logger.info(f"划出[{card_name}]，未检测到任何敌方随从")
        human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
        time.sleep(0.9)
        self.device_state.u2_device.click(
            611 + random.randint(-3, 3), 227 + random.randint(-2, 2)
        )
        time.sleep(0.5)
    
    def _default_card_play(self, center_x, center_y, target_x):
        """默认卡牌打出"""
        human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
    

    
    def _scan_shield_targets(self):
        """扫描护盾目标"""
        # 这里需要调用原有的扫描方法，通过device_state访问
        if hasattr(self.device_state, 'game_manager') and self.device_state.game_manager:
            return self.device_state.game_manager.scan_shield_targets()
        return []
    
    def _scan_enemy_followers(self, screenshot, is_select=False):
        """扫描敌方随从"""
        # 这里需要调用原有的扫描方法，通过device_state访问
        if hasattr(self.device_state, 'game_manager') and self.device_state.game_manager:
            return self.device_state.game_manager.scan_enemy_followers(screenshot, is_select=is_select)
        return []
    
    def _handle_scan_our_follower_to_choose_target(self, card_name, center_x, center_y, target_x):
        """处理扫描我方随从数量选择选项（王断的威光）"""
        self.device_state.logger.info(f"检测到{card_name}，扫描我方随从数量")
        
        # 扫描我方随从
        screenshot = self.device_state.take_screenshot()
        time.sleep(0.2)  # 等待

        # 划出卡牌
        human_like_drag(self.device_state.u2_device, center_x, center_y, target_x, 400)
        time.sleep(0.2)  # 等待
        if screenshot:
            our_followers = self._scan_our_followers(screenshot)
            follower_count = len(our_followers)
            
            self.device_state.logger.info(f"检测到我方随从数量: {follower_count}")
            
            # 根据随从数量选择点击位置
            if follower_count <= 3:
                # 随从数量小于等于3个，点击上面的选项(748, 328)召唤两个随从
                click_x, click_y = 748, 328
                self.device_state.logger.info(f"随从数量≤3，召唤两个随从")
            else:
                # 随从数量大于3个，点击上面的选项(724, 429)强化随从
                click_x, click_y = 724, 429
                self.device_state.logger.info(f"随从数量>3，强化随从")
            
            # 执行点击
            self.device_state.u2_device.click(click_x+random.randint(-15, 15), click_y+random.randint(-2, 2))
            time.sleep(0.5)  # 等待点击响应
        else:
            self.device_state.logger.warning("无法获取截图，使用默认处理")
            # 如果无法获取截图，使用默认处理
            self._default_card_play(center_x, center_y, target_x)
    
    def _scan_our_followers(self, screenshot):
        """扫描我方随从"""
        # 这里需要调用原有的扫描方法，通过device_state访问
        if hasattr(self.device_state, 'game_manager') and self.device_state.game_manager:
            # This path only needs follower count; keep it fast.
            return self.device_state.game_manager.scan_our_followers(
                screenshot,
                extra_shots=0,
                with_names=False,
            )
        return []
    
    def handle_evolve_mode_option(self, card_name, *, is_super_evolution: bool = False):
        """处理进化后模式选项的点击操作"""
        # Prefer config-driven effects.
        trigger = "on_super_evolve" if is_super_evolution else "on_evolve"
        steps = get_card_effect_steps(
            self.device_state.config, card_name=card_name, trigger=trigger
        )
        # Super-evolve: fallback to on_evolve (legacy behavior used one config for both).
        if is_super_evolution and not steps:
            steps = get_card_effect_steps(
                self.device_state.config, card_name=card_name, trigger="on_evolve"
            )
        eff_select_option = parse_select_option(steps)

        if eff_select_option in (1, 2):
            mode_option = f"选项{eff_select_option}"
            self.device_state.logger.info(f"检测到进化模式卡牌{card_name}，选项: {mode_option}")
        else:
            # 获取卡牌进化模式选项配置（legacy fallback）
            card_evolve_mode_options = get_card_evolve_mode_options(self.device_state.config)
            card_mode_options = get_card_mode_options(self.device_state.config)
        
            # 优先使用进化模式选项配置，如果没有则使用普通模式选项配置
            mode_source = None
            mode_option = _lookup_by_normalized_key(
                card_evolve_mode_options,
                card_name,
            )
            if mode_option is not None:
                mode_source = "evolve"
            else:
                mode_option = _lookup_by_normalized_key(
                    card_mode_options,
                    card_name,
                )
                if mode_option is not None:
                    mode_source = "normal"
            if mode_option is not None:
                if mode_source == "evolve":
                    self.device_state.logger.info(f"检测到进化模式卡牌{card_name}，选项: {mode_option}")
                else:
                    self.device_state.logger.info(f"检测到进化模式卡牌{card_name}，使用普通模式选项配置: {mode_option}")
            else:
                # 不是进化模式卡牌，返回False
                return False
        
        # 根据选择的选项执行相应的坐标点击操作
        if eff_select_option == 1 or (eff_select_option is None and mode_option == "选项1"):
            # 执行坐标点击操作：click_x, click_y = 748, 328
            click_x, click_y = 748, 328
            self.device_state.logger.info(f"执行进化选项1操作，点击坐标: ({click_x}, {click_y})")
            # 等待卡牌动画完成
            time.sleep(0.3)
            # 执行点击
            self.device_state.u2_device.click(click_x+random.randint(-15, 15), click_y+random.randint(-2, 2))
            # 等待点击响应
            time.sleep(0.5)
        elif eff_select_option == 2 or (eff_select_option is None and mode_option == "选项2"):
            # 执行坐标点击操作：click_x, click_y = 724, 429
            click_x, click_y = 724, 429
            self.device_state.logger.info(f"执行进化选项2操作，点击坐标: ({click_x}, {click_y})")
            # 等待卡牌动画完成
            time.sleep(0.3)
            # 执行点击
            self.device_state.u2_device.click(click_x+random.randint(-15, 15), click_y+random.randint(-2, 2))
            # 等待点击响应
            time.sleep(0.5)
        # 空选项不需要处理
        return True 

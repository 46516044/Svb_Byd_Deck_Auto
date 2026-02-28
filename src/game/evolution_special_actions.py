"""
进化/超进化特殊操作处理模块
处理进化/超进化后的特殊action（如铁拳神父等）
"""

import time
import random
import logging
from src.config.card_priorities import get_evolve_priority_cards
from src.config import settings
from src.game.policy.targets import TargetSelector
from src.game.policy.effects import get_card_effect_steps, parse_action

logger = logging.getLogger(__name__)

class EvolutionSpecialActions:
    """进化/超进化特殊操作处理类"""
    
    def __init__(self, device_state):
        self.device_state = device_state
    
    def handle_evolve_special_action(self, follower_name, pos=None, is_super_evolution=False, existing_followers=None):
        """
        处理进化/超进化后特殊action（如铁拳神父等），便于扩展
        follower_name: 卡牌名称
        pos: 进化随从的坐标（如有需要）
        is_super_evolution: 是否为超进化
        existing_followers: 已扫描的随从结果，避免重复扫描
        """
        # Prefer config-driven effects.
        trigger = "on_super_evolve" if is_super_evolution else "on_evolve"
        steps = get_card_effect_steps(
            getattr(self.device_state, "config", None), card_name=follower_name, trigger=trigger
        )
        if is_super_evolution and not steps:
            # Legacy behavior often uses one config for both; allow fallback.
            steps = get_card_effect_steps(
                getattr(self.device_state, "config", None),
                card_name=follower_name,
                trigger="on_evolve",
            )
        cfg_action = parse_action(steps)
        
        if is_super_evolution:
            # 超进化逻辑
            action = cfg_action
            if action == 'attack_two_enemy_followers_hp_less_than_4':
                self._handle_attack_two_enemy_followers_hp_less_than_4(follower_name, is_super_evolution=True)
            elif action == 'attack_two_enemy_followers_hp_highest':
                self._handle_attack_two_enemy_followers_hp_highest(follower_name, is_super_evolution=True)
            elif action == 'our_followers_with_evolution':
                self._handle_our_followers_with_evolution(follower_name, is_super_evolution=True, existing_followers=existing_followers)
        else:
            # 普通进化逻辑
            action = cfg_action
            if action == 'attack_enemy_follower_hp_less_than_4':
                self._handle_attack_enemy_follower_hp_less_than_4(follower_name)
            elif action == 'attack_two_enemy_followers_hp_highest':
                self._handle_attack_two_enemy_followers_hp_highest(follower_name)
        
        # 处理进化后模式选项的点击操作
        from .card_play_special_actions import CardPlaySpecialActions
        card_play_actions = CardPlaySpecialActions(self.device_state)
        # 执行点击操作
        card_play_actions.handle_evolve_mode_option(
            follower_name, is_super_evolution=is_super_evolution
        )
        
        # 以后可扩展更多action
    
    def _handle_attack_two_enemy_followers_hp_less_than_4(self, follower_name, is_super_evolution=False):
        """处理攻击两个HP<=3的敌方随从"""
        evolution_type = "超进化" if is_super_evolution else "进化"
        screenshot = self.device_state.take_screenshot()
        if screenshot:
            enemy_followers = self._scan_enemy_followers(screenshot)
            targets_to_click = TargetSelector.enemy_followers_hp_leq(
                enemy_followers, max_hp=3, n=2
            )
            if targets_to_click:
                for i, target in enumerate(targets_to_click):
                    self.device_state.logger.info(
                        f"[{follower_name}]{evolution_type}后点击第{i+1}个敌方HP<=3随从: ({target[0]}, {target[1]}) HP={target[3]}"
                    )
                    self.device_state.u2_device.click(int(target[0]), int(target[1]))
                    time.sleep(0.5)
            else:
                self.device_state.logger.info(f"[{follower_name}]{evolution_type}后未找到HP<=3随从")
    
    def _handle_attack_two_enemy_followers_hp_highest(self, follower_name, is_super_evolution=False):
        """处理攻击血量最高的敌方随从"""
        evolution_type = "超进化" if is_super_evolution else "进化"
        screenshot = self.device_state.take_screenshot()
        if screenshot:
            enemy_followers = self._scan_enemy_followers(screenshot)
            # 只保留HP为数字的随从
            valid_targets = [f for f in enemy_followers if f[3].isdigit()]
            if valid_targets:
                target = TargetSelector.enemy_follower_highest_hp(valid_targets)
                if target is None:
                    self.device_state.logger.info(f"[{follower_name}]{evolution_type}后未找到有效敌方随从")
                    return
                self.device_state.logger.info(f"[{follower_name}]{evolution_type}后点击血量最大敌方随从: ({target[0]}, {target[1]}) HP={target[3]}")
                self.device_state.u2_device.click(int(target[0]), int(target[1]))
                time.sleep(0.5)
            else:
                self.device_state.logger.info(f"[{follower_name}]{evolution_type}后未找到有效敌方随从")
    
    def _handle_our_followers_with_evolution(self, follower_name, is_super_evolution=False, existing_followers=None):
        """选择随从进行/超进化"""
        evolution_type = "超进化" if is_super_evolution else "进化"
        
        # 如果传入了已扫描的随从结果，直接使用；否则重新扫描
        if existing_followers is not None:
            our_followers = existing_followers
            self.device_state.logger.debug(f"[{follower_name}]{evolution_type}后使用已扫描的随从结果，避免重复扫描")
        else:
            screenshot = self.device_state.take_screenshot()
            if screenshot:
                # 获取我方随从位置和名字（scan_our_followers已经包含了SIFT识别结果）
                our_followers = self._scan_our_followers(screenshot)
            else:
                self.device_state.logger.info(f"[{follower_name}]{evolution_type}后截图失败")
                return
        
        if our_followers:
            evolve_priority_cards = get_evolve_priority_cards(
                getattr(self.device_state, "config", None)
            )
            target = TargetSelector.friendly_follower_by_evolve_priority(
                our_followers,
                exclude_names=(follower_name,),
                evolve_priority_cards=evolve_priority_cards,
            )

            if target is None:
                self.device_state.logger.info(
                    f"[{follower_name}]{evolution_type}后未检测到可选择进化的我方随从"
                )
                return

            target_x, target_y, target_type, target_name = target
            target_priority = 999
            if target_name and target_name in evolve_priority_cards:
                try:
                    target_priority = int(
                        evolve_priority_cards[target_name].get("priority", 999)
                    )
                except Exception:
                    target_priority = 999

            if target_name and target_priority < 999:
                self.device_state.logger.info(
                    f"[{follower_name}]{evolution_type}后选择高优先级随从: {target_name} (优先级:{target_priority})"
                )
            elif target_name:
                self.device_state.logger.info(
                    f"[{follower_name}]{evolution_type}后选择我方未进化随从: {target_name}"
                )
            else:
                self.device_state.logger.info(f"[{follower_name}]{evolution_type}后选择我方随从")

            self.device_state.u2_device.click(int(target_x), int(target_y))
            time.sleep(0.5)
        else:
            self.device_state.logger.info(f"[{follower_name}]{evolution_type}后未检测到我方随从")
        time.sleep(1)
    
    def _handle_attack_enemy_follower_hp_less_than_4(self, follower_name):
        """处理攻击HP<=3的敌方随从"""
        screenshot = self.device_state.take_screenshot()
        if screenshot:
            enemy_followers = self._scan_enemy_followers(screenshot)
            target = TargetSelector.enemy_follower_hp_leq(enemy_followers, max_hp=3)
            if target is not None:
                self.device_state.logger.info(f"[{follower_name}]进化后点击敌方HP<=3且最大随从: ({target[0]}, {target[1]}) HP={target[3]}")
                self.device_state.u2_device.click(int(target[0]), int(target[1]))
                time.sleep(0.5)
            else:
                self.device_state.logger.info(f"[{follower_name}]进化后未找到HP<=3随从")
    
    def _scan_enemy_followers(self, screenshot, is_select=False):
        """扫描敌方随从"""
        # 这里需要调用原有的扫描方法，通过device_state访问
        if hasattr(self.device_state, 'game_manager') and self.device_state.game_manager:
            return self.device_state.game_manager.scan_enemy_followers(screenshot, is_select=is_select)
        return []
    
    def _scan_our_followers(self, screenshot):
        """扫描我方随从"""
        # 这里需要调用原有的扫描方法，通过device_state访问
        if hasattr(self.device_state, 'game_manager') and self.device_state.game_manager:
            return self.device_state.game_manager.scan_our_followers(screenshot)
        return [] 

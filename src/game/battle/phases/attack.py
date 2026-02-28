"""Attack phase wrapper."""

from __future__ import annotations


class AttackPhase:
    def __init__(self, actions):
        self.actions = actions

    def run(self, enemy_check) -> None:
        ds = self.actions.device_state
        ds.logger.info("[Phase] attack")

        # 刷新一次我方随从信息（扫描/补扫在内部统一处理）
        self.actions._refresh_our_followers(sort_desc=False)
        self.actions.perform_follower_attacks(enemy_check)

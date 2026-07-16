"""进化与超进化阶段包装器。"""

from __future__ import annotations



class EvolvePhase:
    def __init__(self, actions, policy):
        self.actions = actions
        self.policy = policy

    def run(self) -> bool:
        ds = self.actions.device_state

        if not (getattr(ds, "evolution_point", 0) > 0 or getattr(ds, "super_evolution_point", 0) > 0):
            return False

        if not self.policy.should_evolve(self.actions):
            return False

        ds.logger.info("[Phase] evolve")
        self.actions.perform_evolution_actions()

        # 进化点击后的主要等待已在执行函数内部处理。
        # 点击空白处关闭面板
        self.actions._click_blank_panel(sleep_seconds=0.3)
        # 刷新随从信息
        self.actions._refresh_our_followers(
            sort_desc=False,
            extra_shots=0,
            retries=0,
            with_names=True,
        )
        return True

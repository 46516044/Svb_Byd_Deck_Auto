"""Policy interfaces.

For now we introduce a minimal battle policy hook so the existing logic can be
gradually migrated without changing outward behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from src.config.card_priorities import is_evolve_priority_card


if TYPE_CHECKING:
    from src.game.game_actions import GameActions


class BattlePolicy(Protocol):
    name: str

    def should_evolve(self, actions: "GameActions") -> bool:
        """Return True if evolve/super-evolve phase should run."""


class LegacyBattlePolicy:
    """Policy that preserves the current hardcoded evolve decision."""

    name = "legacy"

    def should_evolve(self, actions: "GameActions") -> bool:
        ds = actions.device_state

        # Must have points.
        if not (getattr(ds, "evolution_point", 0) > 0 or getattr(ds, "super_evolution_point", 0) > 0):
            return False

        # Condition 1: enemy has followers (scan fresh screenshot).
        screenshot = ds.take_screenshot()
        if screenshot:
            try:
                enemy_followers = actions._scan_enemy_ATK(screenshot)
            except Exception:
                enemy_followers = []
            if enemy_followers:
                ds.logger.info("检测到敌方随从，满足进化/超进化条件")
                return True

        # Condition 2: our green (storm) followers exist.
        try:
            our_followers = actions.follower_manager.get_positions() or []
        except Exception:
            our_followers = []
        green_followers = [f for f in our_followers if len(f) > 2 and f[2] == "green"]
        if green_followers:
            ds.logger.info("检测到我方疾驰随从，满足进化/超进化条件")
            return True

        # Condition 3: any evolve-priority follower exists.
        for follower in our_followers:
            follower_name = follower[3] if len(follower) > 3 else None
            if follower_name and is_evolve_priority_card(
                follower_name, getattr(ds, "config", None)
            ):
                ds.logger.info(f"检测到优先进化随从[{follower_name}]，满足进化/超进化条件")
                return True

        return False

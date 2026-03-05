"""Attack phase wrapper."""

from __future__ import annotations


class AttackPhase:
    def __init__(self, actions):
        self.actions = actions

    def run(self, enemy_check) -> None:
        ds = self.actions.device_state
        ds.logger.info("[Phase] attack")

        # Only pay the SIFT naming cost when on_attack effects exist.
        try:
            from src.config.strategy_effects import has_any_effects_for_trigger

            need_names = has_any_effects_for_trigger(getattr(ds, "config", None), trigger="on_attack")
        except Exception:
            need_names = False

        # Attack phase prefers a fresh strict scan to avoid stale-cache misses.
        # Baseline: 3-frame merge + 1 retry (up to 2 attempts).
        our_followers = self.actions._refresh_our_followers(
            sort_desc=True,
            extra_shots=2,
            retries=1,
            with_names=bool(need_names),
            allow_cached_fallback=False,
        )

        # Only use cached followers as a last fallback when strict scan returns nothing.
        if not our_followers:
            try:
                fm = getattr(self.actions, "follower_manager", None)
                if fm is not None and hasattr(fm, "get_positions_sorted"):
                    our_followers = fm.get_positions_sorted(sort_desc=True)
                elif fm is not None:
                    our_followers = sorted(
                        (fm.get_positions() or []), key=lambda f: int(f[0]), reverse=True
                    )
            except Exception:
                our_followers = []

        self.actions.perform_follower_attacks(enemy_check, all_followers=our_followers)

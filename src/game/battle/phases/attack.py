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

        # Avoid redundant rescans: if evolve/play phase just refreshed positions,
        # reuse them; otherwise do one quick refresh for the attack phase.
        our_followers = None
        try:
            fm = getattr(self.actions, "follower_manager", None)
            if fm is not None and hasattr(fm, "is_fresh") and fm.is_fresh(max_age_seconds=1.5):
                if hasattr(fm, "get_positions_sorted"):
                    our_followers = fm.get_positions_sorted(sort_desc=True)
                else:
                    our_followers = sorted(
                        (fm.get_positions() or []), key=lambda f: int(f[0]), reverse=True
                    )

                if need_names and our_followers:
                    try:
                        if not any(len(f) > 3 and f[3] for f in our_followers):
                            our_followers = None
                    except Exception:
                        our_followers = None
        except Exception:
            our_followers = None

        if our_followers is None:
            our_followers = self.actions._refresh_our_followers(
                sort_desc=True,
                extra_shots=0,
                retries=1,
                with_names=bool(need_names),
            )

        self.actions.perform_follower_attacks(enemy_check, all_followers=our_followers)

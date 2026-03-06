"""Attack phase wrapper."""

from __future__ import annotations


class AttackPhase:
    def __init__(self, actions):
        self.actions = actions

    def run(self, enemy_check) -> None:
        ds = self.actions.device_state
        ds.logger.info("[Phase] attack")

        # Attack phase prefers a fresh strict scan to avoid stale-cache misses.
        # Baseline: 3-shot sampling with names, retry handled by lower layer.
        our_followers = self.actions._refresh_our_followers(
            sort_desc=True,
            extra_shots=2,
            retries=0,
            with_names=True,
            allow_cached_fallback=False,
        )

        # Only use cached followers as a last fallback when strict scan returns nothing.
        if not our_followers:
            try:
                fm = getattr(self.actions, "follower_manager", None)
                is_fresh = bool(
                    fm is not None
                    and hasattr(fm, "is_fresh")
                    and fm.is_fresh(max_age_seconds=0.8)
                )
                if is_fresh and fm is not None and hasattr(fm, "get_positions_sorted"):
                    our_followers = fm.get_positions_sorted(sort_desc=True)
                elif is_fresh and fm is not None:
                    our_followers = sorted(
                        (fm.get_positions() or []), key=lambda f: int(f[0]), reverse=True
                    )
                else:
                    our_followers = []
            except Exception:
                our_followers = []

        self.actions.perform_follower_attacks(enemy_check, all_followers=our_followers)

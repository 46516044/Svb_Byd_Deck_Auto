"""Config migrations (one-time, in-place upgrades)."""

from __future__ import annotations

from typing import Any, Dict


def migrate_high_priority_cards_priority_fields(config: Dict[str, Any]) -> bool:
    """Migrate legacy `high_priority_cards[*].priority` to split pre/post fields.

    Rules:
    - If only `priority` exists: set both `priority_pre_evolution` and
      `priority_post_evolution` to that value, then delete `priority`.
    - If only one of pre/post exists: copy the existing value to the missing one.
    - If pre/post already exist: drop legacy `priority` if present.

    The migration is applied in-place and returns True when any change is made.
    """

    high_priority_cards = config.get("high_priority_cards")
    if not isinstance(high_priority_cards, dict):
        return False

    changed = False
    for card_name, card_cfg in list(high_priority_cards.items()):
        # Extremely old format: value is an int/str priority.
        if isinstance(card_cfg, (int, float, str)):
            try:
                priority_value = int(card_cfg)
            except Exception:
                continue

            high_priority_cards[card_name] = {
                "priority_pre_evolution": priority_value,
                "priority_post_evolution": priority_value,
            }
            changed = True
            continue

        if not isinstance(card_cfg, dict):
            continue

        has_pre = "priority_pre_evolution" in card_cfg
        has_post = "priority_post_evolution" in card_cfg

        if ("priority" in card_cfg) and (not has_pre) and (not has_post):
            try:
                priority_value = int(card_cfg.get("priority"))
            except Exception:
                # Keep legacy data if it's not parseable.
                continue

            card_cfg["priority_pre_evolution"] = priority_value
            card_cfg["priority_post_evolution"] = priority_value
            del card_cfg["priority"]
            changed = True
            continue

        # Fill missing stage so callers can rely on both existing.
        if has_pre and not has_post:
            card_cfg["priority_post_evolution"] = card_cfg["priority_pre_evolution"]
            changed = True
        elif has_post and not has_pre:
            card_cfg["priority_pre_evolution"] = card_cfg["priority_post_evolution"]
            changed = True

        # Remove redundant legacy key once split keys exist.
        if ("priority" in card_cfg) and ("priority_pre_evolution" in card_cfg) and (
            "priority_post_evolution" in card_cfg
        ):
            del card_cfg["priority"]
            changed = True

    return changed


def migrate_strategy_effects_schema(config: Dict[str, Any]) -> bool:
    """Seed/upgrade `strategy.effects` from legacy fields and defaults.

    Goals:
    - Provide a single, structured `strategy.effects` mapping
    - Keep legacy fields for compatibility (do not delete them here)
    - Be idempotent: safe to run multiple times
    """

    changed = False

    # Ensure containers
    strategy = config.get("strategy")
    if not isinstance(strategy, dict):
        strategy = {}
        config["strategy"] = strategy
        changed = True

    effects = strategy.get("effects")
    if not isinstance(effects, dict):
        effects = {}
        strategy["effects"] = effects
        changed = True

    def _norm_select_option(v: Any) -> int | None:
        if v in (1, "1", "选项1", "Option1", "option1"):
            return 1
        if v in (2, "2", "选项2", "Option2", "option2"):
            return 2
        return None

    def _ensure_steps(card_name: str, trigger: str) -> list:
        nonlocal changed
        card_eff = effects.get(card_name)
        if not isinstance(card_eff, dict):
            card_eff = {}
            effects[card_name] = card_eff
            changed = True
        steps = card_eff.get(trigger)
        if steps is None:
            steps = []
            card_eff[trigger] = steps
            changed = True
        elif not isinstance(steps, list):
            steps = []
            card_eff[trigger] = steps
            changed = True
        return steps

    def _replace_select_option(card_name: str, trigger: str, opt: int) -> None:
        nonlocal changed
        steps = _ensure_steps(card_name, trigger)
        new_steps = [s for s in steps if not (isinstance(s, dict) and "select_option" in s)]
        new_steps.insert(0, {"select_option": int(opt)})
        if new_steps != steps:
            effects[card_name][trigger] = new_steps
            changed = True

    # Legacy: card_mode_options -> on_play select_option
    legacy_mode = config.get("card_mode_options")
    if isinstance(legacy_mode, dict):
        for card_name, opt_raw in legacy_mode.items():
            opt = _norm_select_option(opt_raw)
            if opt is None:
                continue
            _replace_select_option(str(card_name), "on_play", opt)

    # Legacy: card_evolve_mode_options -> on_evolve/on_super_evolve select_option
    legacy_evo_mode = config.get("card_evolve_mode_options")
    if isinstance(legacy_evo_mode, dict):
        for card_name, opt_raw in legacy_evo_mode.items():
            opt = _norm_select_option(opt_raw)
            if opt is None:
                continue
            card_name = str(card_name)
            _replace_select_option(card_name, "on_evolve", opt)
            _replace_select_option(card_name, "on_super_evolve", opt)

    # Defaults: seed special target/actions so they become config-editable.
    try:
        from src.config.strategy_defaults import build_default_effects

        defaults = build_default_effects()
    except Exception:
        defaults = {}

    if isinstance(defaults, dict):
        for card_name, card_eff in defaults.items():
            if not isinstance(card_eff, dict):
                continue
            for trigger, default_steps in card_eff.items():
                if not isinstance(default_steps, list):
                    continue

                steps = _ensure_steps(str(card_name), str(trigger))
                # Append missing step dicts (idempotent)
                for step in default_steps:
                    if not isinstance(step, dict):
                        continue
                    if any(isinstance(s, dict) and s == step for s in steps):
                        continue
                    steps.append(step)
                    changed = True

    return changed

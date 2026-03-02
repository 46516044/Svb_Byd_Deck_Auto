"""Config migrations (one-time, in-place upgrades)."""

from __future__ import annotations

import json
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
                raw_priority = card_cfg.get("priority")
                if not isinstance(raw_priority, (int, float, str)):
                    continue
                priority_value = int(raw_priority)
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

    # Whether this config already had any effects before this migration runs.
    # If yes, we must NOT keep re-seeding defaults, otherwise users can never
    # delete default entries (they would come back on every startup).
    had_any_effects = bool(effects)

    def _norm_select_option(v: Any) -> int | None:
        if v in (1, "1", "选项1", "Option1", "option1"):
            return 1
        if v in (2, "2", "选项2", "Option2", "option2"):
            return 2
        return None

    def _is_select_option_step(step: Any) -> bool:
        if not isinstance(step, dict):
            return False
        if "select_option" in step:
            return True
        return str(step.get("op") or "") == "select_option"

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

    def _seed_select_option_if_missing(card_name: str, trigger: str, opt: int) -> None:
        nonlocal changed
        steps = _ensure_steps(card_name, trigger)
        if any(_is_select_option_step(s) for s in steps):
            return
        steps.insert(0, {"op": "select_option", "index": int(opt)})
        changed = True

    # Legacy: card_mode_options -> on_play select_option
    legacy_mode = config.get("card_mode_options")
    if isinstance(legacy_mode, dict):
        for card_name, opt_raw in legacy_mode.items():
            opt = _norm_select_option(opt_raw)
            if opt is None:
                continue
            _seed_select_option_if_missing(str(card_name), "on_play", opt)

    # Legacy: card_evolve_mode_options -> on_evolve/on_super_evolve select_option
    legacy_evo_mode = config.get("card_evolve_mode_options")
    if isinstance(legacy_evo_mode, dict):
        for card_name, opt_raw in legacy_evo_mode.items():
            opt = _norm_select_option(opt_raw)
            if opt is None:
                continue
            card_name = str(card_name)
            _seed_select_option_if_missing(card_name, "on_evolve", opt)
            _seed_select_option_if_missing(card_name, "on_super_evolve", opt)

    # Defaults: seed special target/actions so they become config-editable.
    # IMPORTANT: only seed once for "fresh" configs; do not re-seed on every
    # load, otherwise users cannot delete old/default rules.
    defaults_seeded_key = "_effects_defaults_seeded"
    if not bool(strategy.get(defaults_seeded_key)):
        if had_any_effects:
            # Existing config: mark as seeded without mutating effects.
            strategy[defaults_seeded_key] = True
            changed = True
        else:
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

            strategy[defaults_seeded_key] = True
            changed = True

    return changed


def migrate_strategy_effects_to_ops(config: Dict[str, Any]) -> bool:
    """Upgrade `strategy.effects[*][trigger]` steps to the Step3A op schema.

    - Idempotent
    - Keeps unknown dict steps as-is
    - Best-effort upgrade for legacy keys: select_option/target_type/action
    """

    strategy = config.get("strategy")
    if not isinstance(strategy, dict):
        return False
    effects = strategy.get("effects")
    if not isinstance(effects, dict):
        return False

    def _norm_select_option(v: Any) -> int | None:
        if v in (1, "1", "选项1", "Option1", "option1"):
            return 1
        if v in (2, "2", "选项2", "Option2", "option2"):
            return 2
        return None

    def _is_op(step: Any, op_id: str) -> bool:
        return isinstance(step, dict) and str(step.get("op") or "") == str(op_id)

    changed = False

    for card_name, card_eff in list(effects.items()):
        if not isinstance(card_eff, dict):
            continue

        for trigger, steps in list(card_eff.items()):
            if not isinstance(steps, list):
                continue

            new_steps = []
            for step in steps:
                if isinstance(step, dict) and isinstance(step.get("op"), str) and step.get("op"):
                    # Deprecation: select_targets(target.kind=option) -> select_option
                    try:
                        if str(step.get("op")) == "select_targets":
                            tgt = step.get("target")
                            if isinstance(tgt, dict) and str(tgt.get("kind") or "") == "option":
                                params = tgt.get("params")
                                if not isinstance(params, dict):
                                    params = {}
                                idx = _norm_select_option(params.get("index"))
                                if idx is not None:
                                    converted = {"op": "select_option", "index": int(idx)}
                                    if step.get("on_error"):
                                        converted["on_error"] = step.get("on_error")
                                    new_steps.append(converted)
                                    changed = True
                                    continue
                    except Exception:
                        pass

                    new_steps.append(step)
                    continue

                if not isinstance(step, dict):
                    continue

                expanded = []
                if "select_option" in step:
                    opt = _norm_select_option(step.get("select_option"))
                    if opt is not None:
                        expanded.append({"op": "select_option", "index": int(opt)})
                if "target_type" in step:
                    tt = step.get("target_type")
                    if isinstance(tt, str) and tt:
                        expanded.append({"op": "legacy_target_type", "target_type": str(tt)})
                if "action" in step:
                    act = step.get("action")
                    if isinstance(act, str) and act:
                        expanded.append({"op": "legacy_action", "action": str(act)})

                if expanded:
                    new_steps.extend(expanded)
                    changed = True
                else:
                    # Unknown legacy dict step: preserve as-is.
                    new_steps.append(step)

            # Preserve legacy runtime semantics for evolve: do action/targets before select_option.
            if str(trigger) in ("on_evolve", "on_super_evolve"):
                reordered = [s for s in new_steps if not _is_op(s, "select_option")] + [
                    s for s in new_steps if _is_op(s, "select_option")
                ]
                if reordered != new_steps:
                    new_steps = reordered
                    changed = True

            # Dedup exact dict steps while preserving order.
            deduped = []
            seen = set()
            for s in new_steps:
                if not isinstance(s, dict):
                    continue
                key = json.dumps(s, ensure_ascii=False, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(s)

            if deduped != steps:
                if deduped:
                    card_eff[trigger] = deduped
                else:
                    del card_eff[trigger]
                changed = True

        # Cleanup empty card entries.
        if not card_eff:
            del effects[card_name]
            changed = True

    return changed

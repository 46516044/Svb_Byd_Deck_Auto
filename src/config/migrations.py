"""Config migrations (one-time, in-place upgrades)."""

from __future__ import annotations

import json
import copy
from typing import Any, Dict

from src.utils.card_filename import normalize_card_base_name, normalize_config_key, split_enhance_key
from src.config.strategy_effects import normalize_effect_steps_to_ops


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
    - Canonical runtime schema only (no runtime legacy wrappers)
    """

    strategy = config.get("strategy")
    if not isinstance(strategy, dict):
        return False
    effects = strategy.get("effects")
    if not isinstance(effects, dict):
        return False

    def _is_op(step: Any, op_id: str) -> bool:
        return isinstance(step, dict) and str(step.get("op") or "") == str(op_id)

    changed = False

    for card_name, card_eff in list(effects.items()):
        if not isinstance(card_eff, dict):
            continue

        for trigger, steps in list(card_eff.items()):
            if not isinstance(steps, list):
                continue

            try:
                new_steps = normalize_effect_steps_to_ops(steps)
            except Exception:
                new_steps = [dict(s) for s in steps if isinstance(s, dict)]

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

        # Remove runtime fallback: super evolve no longer falls back to on_evolve.
        # Keep compatibility at migration boundary by cloning missing trigger.
        try:
            on_evolve_steps = card_eff.get("on_evolve")
            on_super_steps = card_eff.get("on_super_evolve")
            if (
                isinstance(on_evolve_steps, list)
                and on_evolve_steps
                and (
                    not isinstance(on_super_steps, list)
                    or not on_super_steps
                )
            ):
                card_eff["on_super_evolve"] = copy.deepcopy(on_evolve_steps)
                changed = True
        except Exception:
            pass

        # Cleanup empty card entries.
        if not card_eff:
            del effects[card_name]
            changed = True

    return changed


def migrate_strategy_name_keys(config: Dict[str, Any]) -> bool:
    """Normalize strategy-related card keys to suffix-free base naming.

    Targets:
    - high_priority_cards
    - evolve_priority_cards
    - strategy.effects

    Normalization rules:
    - Remove follower stat suffix ``_<atk>_<hp>`` from base names.
    - Preserve enhance tier format ``name@cost`` where applicable.
    - `evolve_priority_cards` is always stored by base name (no `@cost`).
    """

    changed = False

    def _merge_dict(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
        out = copy.deepcopy(dst)
        for k, v in src.items():
            out[k] = copy.deepcopy(v)
        return out

    def _normalize_mapping(
        mapping: Any,
        *,
        force_base_key: bool = False,
        merge_effects: bool = False,
    ) -> tuple[Dict[str, Any], bool]:
        if not isinstance(mapping, dict):
            return {}, False

        out: Dict[str, Any] = {}
        local_changed = False

        for raw_k, raw_v in mapping.items():
            if not isinstance(raw_k, str):
                continue

            nk = normalize_config_key(raw_k)
            if force_base_key:
                base, _enh = split_enhance_key(nk)
                nk = normalize_card_base_name(str(base or ""))

            if not nk:
                local_changed = True
                continue

            if nk != raw_k:
                local_changed = True

            if nk not in out:
                out[nk] = copy.deepcopy(raw_v)
                continue

            # Key collision after normalization.
            local_changed = True
            existing = out[nk]
            if merge_effects and isinstance(existing, dict) and isinstance(raw_v, dict):
                merged_eff = copy.deepcopy(existing)
                for trig, steps in raw_v.items():
                    if trig not in merged_eff:
                        merged_eff[trig] = copy.deepcopy(steps)
                        continue
                    if isinstance(merged_eff.get(trig), list) and isinstance(steps, list):
                        cur = list(merged_eff.get(trig) or [])
                        for s in steps:
                            if s in cur:
                                continue
                            cur.append(copy.deepcopy(s))
                        merged_eff[trig] = cur
                out[nk] = merged_eff
            elif isinstance(existing, dict) and isinstance(raw_v, dict):
                out[nk] = _merge_dict(existing, raw_v)
            else:
                out[nk] = copy.deepcopy(raw_v)

        return out, local_changed

    hp = config.get("high_priority_cards")
    if isinstance(hp, dict):
        hp_new, hp_changed = _normalize_mapping(hp, force_base_key=False, merge_effects=False)
        if hp_changed:
            config["high_priority_cards"] = hp_new
            changed = True

    ep = config.get("evolve_priority_cards")
    if isinstance(ep, dict):
        ep_new, ep_changed = _normalize_mapping(ep, force_base_key=True, merge_effects=False)
        if ep_changed:
            config["evolve_priority_cards"] = ep_new
            changed = True

    strategy = config.get("strategy")
    if isinstance(strategy, dict):
        effects = strategy.get("effects")
        if isinstance(effects, dict):
            eff_new, eff_changed = _normalize_mapping(effects, force_base_key=False, merge_effects=True)
            if eff_changed:
                strategy["effects"] = eff_new
                changed = True

    return changed


def migrate_runtime_legacy_fields(config: Dict[str, Any]) -> bool:
    """Drop runtime legacy fields after one-time migration seeding.

    Compatibility is kept at startup/load boundary by migration functions.
    Runtime should consume only canonical schema/paths.
    """

    if not isinstance(config, dict):
        return False

    changed = False

    for key in ("card_mode_options", "card_evolve_mode_options"):
        if key in config:
            del config[key]
            changed = True

    game = config.get("game")
    if isinstance(game, dict) and "use_enhanced_mulligan" in game:
        del game["use_enhanced_mulligan"]
        changed = True

    return changed

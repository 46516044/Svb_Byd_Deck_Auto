"""Strategy effects schema helpers.

Important: this module must stay lightweight because UI imports it.
It should not import cv/u2/game modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def get_card_effect_steps(
    config: Dict[str, Any] | None,
    *,
    card_name: str,
    trigger: str,
) -> List[Dict[str, Any]]:
    if not isinstance(config, dict):
        return []
    effects = config.get("strategy", {}).get("effects", {})
    if not isinstance(effects, dict):
        return []
    card_eff = effects.get(card_name, {})
    if not isinstance(card_eff, dict):
        return []
    steps = card_eff.get(trigger, [])
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict)]


def normalize_effect_steps_to_ops(steps: Sequence[Any]) -> List[Dict[str, Any]]:
    """Normalize legacy Step2B steps to Step3A OperationSpec dicts.

    Supported legacy keys:
    - {"select_option": 1/2} -> {"op": "select_option", "index": 1/2}
    - {"target_type": "..."} -> {"op": "legacy_target_type", "target_type": "..."}
    - {"action": "..."} -> {"op": "legacy_action", "action": "..."}
    """

    def _norm_select_option(v: Any) -> int | None:
        if v in (1, "1", "选项1", "Option1", "option1"):
            return 1
        if v in (2, "2", "选项2", "Option2", "option2"):
            return 2
        return None

    ops: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue

        op_id = step.get("op")
        if isinstance(op_id, str) and op_id:
            ops.append(step)
            continue

        if "select_option" in step:
            opt = _norm_select_option(step.get("select_option"))
            if opt is not None:
                ops.append({"op": "select_option", "index": int(opt)})

        if "target_type" in step:
            tt = step.get("target_type")
            if isinstance(tt, str) and tt:
                ops.append({"op": "legacy_target_type", "target_type": str(tt)})

        if "action" in step:
            act = step.get("action")
            if isinstance(act, str) and act:
                ops.append({"op": "legacy_action", "action": str(act)})

    return ops


def get_card_effect_ops(
    config: Dict[str, Any] | None,
    *,
    card_name: str,
    trigger: str,
) -> List[Dict[str, Any]]:
    return normalize_effect_steps_to_ops(
        get_card_effect_steps(config, card_name=card_name, trigger=trigger)
    )


def parse_select_option(steps: Sequence[Any]) -> Optional[int]:
    """Return 1/2 if any step requests option selection."""

    for step in steps:
        if not isinstance(step, dict) or "select_option" not in step:
            # Step3A op schema
            if not isinstance(step, dict) or str(step.get("op") or "") != "select_option":
                continue
            v = step.get("index")
        else:
            v = step.get("select_option")

        if v in (1, "1", "选项1", "Option1", "option1"):
            return 1
        if v in (2, "2", "选项2", "Option2", "option2"):
            return 2
    return None


def parse_target_type(steps: Sequence[Any]) -> Optional[str]:
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("op") or "") == "legacy_target_type":
            v = step.get("target_type")
        else:
            v = step.get("target_type")
        if isinstance(v, str) and v:
            return v
    return None


def parse_action(steps: Sequence[Any]) -> Optional[str]:
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("op") or "") == "legacy_action":
            v = step.get("action")
        else:
            v = step.get("action")
        if isinstance(v, str) and v:
            return v
    return None


def has_any_effects_for_trigger(config: Dict[str, Any] | None, *, trigger: str) -> bool:
    if not isinstance(config, dict):
        return False
    effects = config.get("strategy", {}).get("effects", {})
    if not isinstance(effects, dict):
        return False
    trig = str(trigger or "")
    for _card_name, card_eff in effects.items():
        if not isinstance(card_eff, dict):
            continue
        steps = card_eff.get(trig)
        if isinstance(steps, list) and any(isinstance(s, dict) for s in steps):
            return True
    return False

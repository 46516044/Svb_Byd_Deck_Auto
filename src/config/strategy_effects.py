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


def parse_select_option(steps: Sequence[Any]) -> Optional[int]:
    """Return 1/2 if any step requests option selection."""

    for step in steps:
        if not isinstance(step, dict) or "select_option" not in step:
            continue
        v = step.get("select_option")
        if v in (1, "1", "选项1"):
            return 1
        if v in (2, "2", "选项2"):
            return 2
    return None


def parse_target_type(steps: Sequence[Any]) -> Optional[str]:
    for step in steps:
        if not isinstance(step, dict):
            continue
        v = step.get("target_type")
        if isinstance(v, str) and v:
            return v
    return None


def parse_action(steps: Sequence[Any]) -> Optional[str]:
    for step in steps:
        if not isinstance(step, dict):
            continue
        v = step.get("action")
        if isinstance(v, str) and v:
            return v
    return None

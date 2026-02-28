"""Effect spec helpers.

Note: the actual implementation lives in `src.config.strategy_effects` so the UI
can import it without pulling in heavy `src.game` modules.
"""

from __future__ import annotations

from src.config.strategy_effects import (
    get_card_effect_steps,
    parse_action,
    parse_select_option,
    parse_target_type,
)

__all__ = [
    "get_card_effect_steps",
    "parse_action",
    "parse_select_option",
    "parse_target_type",
]

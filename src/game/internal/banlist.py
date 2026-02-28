"""Internal banlist / anti-abuse guard.

Banlist is intentionally hardcoded (not user-configurable). It can be toggled by
config at `game.banlist_enabled`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple


# Hardcoded card-name banlist. Empty means "no restrictions".
_BANLIST_HAND_CARD_NAMES = frozenset(
    {
        # Keep empty for now.
    }
)


def is_banlist_enabled(config: Dict[str, Any] | None) -> bool:
    try:
        return bool((config or {}).get("game", {}).get("banlist_enabled", False))
    except Exception:
        return False


def should_block_play(
    hand_cards: Sequence[Dict[str, Any]] | None,
    config: Dict[str, Any] | None,
) -> Tuple[bool, List[str]]:
    """Return (blocked, hit_card_names)."""

    if not is_banlist_enabled(config):
        return False, []
    if not hand_cards:
        return False, []

    hits: List[str] = []
    for card in hand_cards:
        if not isinstance(card, dict):
            continue
        name = card.get("name")
        if isinstance(name, str) and name in _BANLIST_HAND_CARD_NAMES:
            hits.append(name)

    if not hits:
        return False, []

    seen = set()
    uniq: List[str] = []
    for name in hits:
        if name in seen:
            continue
        seen.add(name)
        uniq.append(name)
    return True, uniq

"""内部禁用名单与防滥用保护。

名单刻意硬编码，不向用户开放编辑；可通过 ``game.banlist_enabled`` 配置开关。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple


# 硬编码卡名禁用名单；空集合表示不限制。
_BANLIST_HAND_CARD_NAMES = frozenset(
    {
# 当前暂时保持为空。
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
    """返回是否阻止以及命中的卡名列表。"""

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

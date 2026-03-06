"""Card filename helpers.

Support Enhance/"爆能" tiers encoded in image filenames.

Naming convention (stem without extension):
- "4_xxx" -> base_cost=4, enhance_costs=[], name="xxx"
- "4_6_xxx" -> base_cost=4, enhance_costs=[6], name="xxx"
- "4_6_8_xxx" -> base_cost=4, enhance_costs=[6, 8], name="xxx"

Card names may contain underscores. Enhance tiers are parsed as consecutive
integer segments immediately after the base cost.
"""

from __future__ import annotations

from typing import List, Optional, Tuple


def parse_follower_stat_suffix(card_name: str) -> Tuple[str, Optional[int], Optional[int]]:
    """Parse follower stat suffix from a card name.

    Expected suffix format: ``..._<atk>_<hp>``.
    Parsing is done from the rightmost two underscore segments.

    Returns:
        (base_name, base_atk, base_hp)
        - On success: base_name excludes the trailing ``_<atk>_<hp>``.
        - On failure: base_name is the original name, atk/hp are None.
    """

    raw = str(card_name or "").strip()
    if not raw:
        return "", None, None

    parts = raw.split("_")
    if len(parts) < 3:
        return raw, None, None

    atk_s = parts[-2]
    hp_s = parts[-1]
    if not (atk_s.isdigit() and hp_s.isdigit()):
        return raw, None, None

    base_name = "_".join(parts[:-2]).strip()
    if not base_name:
        return raw, None, None

    try:
        return base_name, int(atk_s), int(hp_s)
    except Exception:
        return raw, None, None


def normalize_card_base_name(card_name: str) -> str:
    """Return a stable card base name used by UI/config keys.

    - Removes follower stat suffix ``_<atk>_<hp>`` when present.
    - Keeps original text when suffix is absent.
    """

    raw = str(card_name or "").strip()
    if not raw:
        return ""
    base, _atk, _hp = parse_follower_stat_suffix(raw)
    return str(base or raw)


def normalize_config_key(key: str) -> str:
    """Normalize a strategy/config key to suffix-free base naming.

    Supports both plain keys and enhance keys (``name@cost``).
    """

    raw = str(key or "").strip()
    if not raw:
        return ""

    base, enhance = split_enhance_key(raw)
    normalized_base = normalize_card_base_name(str(base or ""))
    if enhance is None:
        return normalized_base
    return make_enhance_key(normalized_base, int(enhance))


def parse_card_stem(stem: str) -> Tuple[int, List[int], str]:
    """Parse a card filename stem.

    Args:
        stem: filename without extension.

    Returns:
        (base_cost, enhance_costs, card_name)
    """

    stem = str(stem or "").strip()
    if not stem:
        return 0, [], ""

    parts = stem.split("_")
    if not parts:
        return 0, [], stem

    try:
        base_cost = int(parts[0])
    except Exception:
        # Fallback: treat whole stem as name.
        return 0, [], stem

    enhance_raw: List[int] = []
    name_parts: List[str] = []

    # Parse consecutive enhance tiers until the first non-int segment.
    for seg in parts[1:]:
        if name_parts:
            name_parts.append(seg)
            continue

        try:
            enhance_raw.append(int(seg))
            continue
        except Exception:
            name_parts.append(seg)

    card_name = "_".join([p for p in name_parts if p is not None])
    if not card_name:
        # If name is missing, best-effort fallback to stem tail.
        card_name = stem.split("_", 1)[-1] if "_" in stem else stem

    # Normalize enhance tiers: unique, > base_cost, sorted ascending.
    enhance_costs: List[int] = []
    for c in enhance_raw:
        try:
            c = int(c)
        except Exception:
            continue
        if c <= base_cost:
            continue
        if c not in enhance_costs:
            enhance_costs.append(c)
    enhance_costs.sort()

    return int(base_cost), enhance_costs, str(card_name)


def parse_card_filename(filename: str) -> Tuple[int, List[int], str]:
    """Parse a card image filename (with extension)."""

    name = str(filename or "")
    stem = name.rsplit(".", 1)[0]
    return parse_card_stem(stem)


def make_enhance_key(card_name: str, enhance_cost: int) -> str:
    """Build a config key for an enhance-tier variant."""

    return f"{str(card_name)}@{int(enhance_cost)}"


def split_enhance_key(key: str) -> Tuple[str, Optional[int]]:
    """Split a config key into (base_name, enhance_cost)."""

    s = str(key or "")
    if "@" not in s:
        return s, None
    base, tail = s.rsplit("@", 1)
    try:
        return base, int(tail)
    except Exception:
        return s, None

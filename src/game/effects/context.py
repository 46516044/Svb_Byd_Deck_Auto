"""Runtime effect contexts.

Keep these structures lightweight (pure data). The heavy logic stays in the
executor/engine modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple


@dataclass
class HandCardContext:
    context_kind: str = "hand_card"
    device_state: Any = None

    # Identity
    card_name: str = ""
    cfg_key: str = ""

    # Play geometry (used by caller; engine doesn't drag by default)
    card_center: Tuple[int, int] = (0, 0)
    play_target: Tuple[int, int] = (0, 0)

    # Full recognized card payload (optional)
    card: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FollowerContext:
    context_kind: str = "follower"
    device_state: Any = None

    follower_name: str = ""
    follower_pos: Optional[Tuple[int, int]] = None
    is_super_evolution: bool = False

    # Optional: reuse already scanned followers to avoid extra CV work
    existing_followers: Optional[Sequence[Any]] = None

    # For on_attack
    attack_source_pos: Optional[Tuple[int, int]] = None

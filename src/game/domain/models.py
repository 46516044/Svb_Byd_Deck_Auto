"""Minimal domain/data structures.

Keep these models pure (no device/cv/config imports) so they can be reused by
policy/effects/phases without dragging runtime dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class GameRules:
    """Game rule constants used by higher-level logic.

    Note: this is intentionally minimal; expand later.
    """

    pp_cap: int = 10
    evolve_unlock_turn_first: int = 5
    evolve_unlock_turn_second: int = 4


@dataclass(frozen=True)
class TargetSpec:
    """A declarative target request (not coordinates).

    Examples:
      - kind="enemy_leader"
      - kind="enemy_follower", selector="highest_hp"
      - kind="option", selector="index", params={"index": 2}
    """

    kind: str
    selector: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Action:
    """An abstract action step (execution layer will translate it).

    Placeholder to be consumed by phases/policy later.
    """

    type: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservedGameState:
    """What the script currently *observes* about the match.

    Fields may be missing/None when recognition fails.
    This structure is designed to accept legacy outputs directly.
    """

    turn: Optional[int] = None
    is_second_player: Optional[bool] = None
    pp_available: Optional[int] = None
    ep: Optional[int] = None
    sep: Optional[int] = None

    # Legacy-friendly shapes:
    # - hand: list[dict] from HandCardManager/SIFT
    # - board_*: list[tuple] from follower scans
    # - ward_enemy: list[(x,y)] from shield scan
    hand: List[Dict[str, Any]] = field(default_factory=list)
    board_ours: List[Any] = field(default_factory=list)
    board_enemy: List[Any] = field(default_factory=list)
    ward_enemy: List[Any] = field(default_factory=list)
    ui: Dict[str, Any] = field(default_factory=dict)

    note: str = ""

    def brief(self) -> str:
        """Human-readable one-line summary for logs."""

        def _fmt_bool(v: Optional[bool]) -> str:
            if v is None:
                return "?"
            return "2nd" if v else "1st"

        hand_preview: Sequence[Dict[str, Any]] = self.hand[:6]
        hand_str = ",".join(
            f"{c.get('cost', '?')}:{c.get('name', '?')}" for c in hand_preview
        )
        if len(self.hand) > 6:
            hand_str += f"(+{len(self.hand) - 6})"

        parts = [
            f"turn={self.turn if self.turn is not None else '?'}",
            f"side={_fmt_bool(self.is_second_player)}",
            f"pp={self.pp_available if self.pp_available is not None else '?'}",
            f"ep={self.ep if self.ep is not None else '?'}",
            f"sep={self.sep if self.sep is not None else '?'}",
            f"hand={len(self.hand)}[{hand_str}]" if self.hand else "hand=0[]",
            f"ours={len(self.board_ours)}",
            f"enemy={len(self.board_enemy)}",
            f"ward={len(self.ward_enemy)}",
        ]
        if self.note:
            parts.append(f"note={self.note}")
        return " ".join(parts)

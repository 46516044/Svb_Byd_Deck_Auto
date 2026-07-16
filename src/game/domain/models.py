"""最小领域数据结构。

这些模型保持纯数据，不导入 device、cv 或 config，使策略、效果和阶段模块复用时
不会连带加载运行时依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class GameRules:
    """上层逻辑使用的游戏规则常量；当前刻意保持最小，按需扩展。"""

    pp_cap: int = 10
    evolve_unlock_turn_first: int = 5
    evolve_unlock_turn_second: int = 4


@dataclass(frozen=True)
class TargetSpec:
    """声明式目标请求，而非实际坐标。

    例如 ``kind="enemy_leader"``、``kind="enemy_follower"`` 搭配
    ``selector="highest_hp"``，或用 ``params={"index": 2}`` 指定选项索引。
    """

    kind: str
    selector: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Action:
    """由执行层转换的抽象动作步骤，供阶段和策略层后续消费。"""

    type: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservedGameState:
    """脚本当前观察到的对战状态。

    识别失败时字段可能缺失或为 ``None``；该结构可直接接收旧版输出形态。
    """

    turn: Optional[int] = None
    is_second_player: Optional[bool] = None
    pp_available: Optional[int] = None
    ep: Optional[int] = None
    sep: Optional[int] = None

    # 兼容旧数据形态：手牌来自 HandCardManager/SIFT 的字典列表，场面来自随从扫描
    # 的元组列表，守护目标来自护盾扫描的坐标列表。
    hand: List[Dict[str, Any]] = field(default_factory=list)
    board_ours: List[Any] = field(default_factory=list)
    board_enemy: List[Any] = field(default_factory=list)
    ward_enemy: List[Any] = field(default_factory=list)
    ui: Dict[str, Any] = field(default_factory=dict)

    note: str = ""

    def brief(self) -> str:
        """生成供日志使用的人类可读单行摘要。"""

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


@dataclass
class FollowerRuntimeState:
    """对战选择与结算使用的运行时随从模型。"""

    side: str = "ours"
    x: int = 0
    y: int = 0
    follower_type: str = "normal"

    raw_name: str = ""
    base_name: str = ""
    source_cfg_key: str = ""
    uid: int = 0

    atk0: Optional[int] = None
    hp0: Optional[int] = None
    observed_hp: Optional[int] = None

    buff_atk: int = 0
    buff_hp: int = 0
    damage_taken: int = 0
    is_ward: bool = False
    evolved_type: str = "none"
    miss_count: int = 0

    # 逐回合覆盖：指定回合内该随从可攻击 N 次；默认仍为每回合一次。
    attack_times_round: int = -1
    attack_times_total: int = 1

    def evolution_bonus(self) -> int:
        if self.evolved_type == "super":
            return 3
        if self.evolved_type == "normal":
            return 2
        return 0

    def effective_atk(self) -> Optional[int]:
        if self.atk0 is None:
            return None
        return int(self.atk0) + int(self.evolution_bonus()) + int(self.buff_atk)

    def effective_hp(self) -> Optional[int]:
        if self.hp0 is None:
            return None
        total = int(self.hp0) + int(self.evolution_bonus()) + int(self.buff_hp)
        return total - int(self.damage_taken)

    def current_hp(self) -> Optional[int]:
        if self.observed_hp is not None:
            return int(self.observed_hp)
        return self.effective_hp()

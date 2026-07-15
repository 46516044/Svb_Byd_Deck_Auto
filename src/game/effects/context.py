"""运行时效果上下文。

这些结构保持轻量并只承载数据，重量级逻辑留在执行器和引擎模块中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class HandCardContext:
    context_kind: str = "hand_card"
    device_state: Any = None

    # 卡牌身份信息。
    card_name: str = ""
    cfg_key: str = ""

    # 出牌几何信息由调用方使用，引擎默认不主动拖拽。
    card_center: Tuple[int, int] = (0, 0)
    play_target: Tuple[int, int] = (0, 0)
    follower_pos: Optional[Tuple[int, int]] = None
    follower_uid: Optional[int] = None

    # 可选的完整识别卡牌数据。
    card: Dict[str, Any] = field(default_factory=dict)

    # ``select_targets`` 失败诊断信息，供调用方策略判断。
    select_targets_fail_kinds: List[str] = field(default_factory=list)
    select_targets_success_kinds: List[str] = field(default_factory=list)

    # 可选的动作前场面快照，用于出牌或进化界面遮挡场面时回退。
    pre_action_our_followers: Optional[Sequence[Any]] = None
    pre_action_our_follower_count: Optional[int] = None


@dataclass
class FollowerContext:
    context_kind: str = "follower"
    device_state: Any = None

    follower_name: str = ""
    cfg_key: str = ""
    follower_pos: Optional[Tuple[int, int]] = None
    follower_uid: Optional[int] = None
    is_super_evolution: bool = False

    # 可复用已扫描随从，避免额外视觉识别开销。
    existing_followers: Optional[Sequence[Any]] = None

    # 可选的动作前场面快照，用于界面遮挡时回退。
    pre_action_our_followers: Optional[Sequence[Any]] = None
    pre_action_our_follower_count: Optional[int] = None

    # ``on_attack`` 触发器使用的攻击者信息。
    attack_source_pos: Optional[Tuple[int, int]] = None

    # ``select_targets`` 失败诊断信息，供调用方策略判断。
    select_targets_fail_kinds: List[str] = field(default_factory=list)
    select_targets_success_kinds: List[str] = field(default_factory=list)

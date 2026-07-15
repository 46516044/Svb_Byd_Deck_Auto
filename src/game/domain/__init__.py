"""领域模型包，刻意只包含数据类，不执行 IO。"""

from .models import Action, FollowerRuntimeState, GameRules, ObservedGameState, TargetSpec

__all__ = [
    "Action",
    "GameRules",
    "FollowerRuntimeState",
    "ObservedGameState",
    "TargetSpec",
]

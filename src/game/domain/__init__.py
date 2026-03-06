"""Domain models.

This package is intentionally lightweight: dataclasses only, no IO.
"""

from .models import Action, FollowerRuntimeState, GameRules, ObservedGameState, TargetSpec

__all__ = [
    "Action",
    "GameRules",
    "FollowerRuntimeState",
    "ObservedGameState",
    "TargetSpec",
]

"""Domain models.

This package is intentionally lightweight: dataclasses only, no IO.
"""

from .models import Action, GameRules, ObservedGameState, TargetSpec

__all__ = [
    "Action",
    "GameRules",
    "ObservedGameState",
    "TargetSpec",
]

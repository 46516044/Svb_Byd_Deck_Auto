"""Run control exceptions.

Used for cooperative, immediate pause/stop by raising lightweight exceptions
from deep action code paths.
"""

from __future__ import annotations


class PauseRequested(Exception):
    """Raised when a pause is requested and the current action should unwind."""


class StopRequested(Exception):
    """Raised when a stop/exit is requested and the current loop should unwind."""

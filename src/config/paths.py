"""Configuration path helpers.

Centralizes how we locate `config.json` across CLI/GUI/packaged runs.
"""

from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    # PyInstaller typically sets `sys.frozen` and provides `sys.executable`.
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def get_app_root() -> str:
    """Return the directory that should be treated as app root.

    - Source run: project root directory (where `main.py` lives)
    - PyInstaller: directory containing the executable
    """

    if is_frozen():
        return os.path.dirname(sys.executable)

    # This file: <project_root>/src/config/paths.py
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def get_config_path(filename: str = "config.json") -> str:
    """Return the canonical config file path."""

    return os.path.join(get_app_root(), filename)

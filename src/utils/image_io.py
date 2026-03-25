"""OpenCV image I/O helpers with Unicode-path fallback.

Windows builds of OpenCV may fail on non-ASCII paths when using ``cv2.imread``.
This module provides a robust fallback via ``np.fromfile + cv2.imdecode``.
"""

from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np


def safe_imread(path: str, flags: int = cv2.IMREAD_COLOR) -> Any | None:
    """Read image from any path, including Unicode paths on Windows.

    Order:
    1) Try ``cv2.imread`` first.
    2) Fallback to ``np.fromfile + cv2.imdecode`` when direct read fails.
    """

    try:
        fs_path = os.fspath(path)
    except Exception:
        fs_path = str(path or "")

    img = cv2.imread(fs_path, flags)
    if img is not None:
        return img

    try:
        raw = np.fromfile(fs_path, dtype=np.uint8)
        if raw.size <= 0:
            return None
        return cv2.imdecode(raw, flags)
    except Exception:
        return None

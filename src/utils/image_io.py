"""带 Unicode 路径回退的 OpenCV 图片 IO 辅助函数。

Windows 版 OpenCV 使用 ``cv2.imread`` 时可能无法读取非 ASCII 路径，因此这里
通过 ``np.fromfile + cv2.imdecode`` 提供稳定回退。
"""

from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np


def safe_imread(path: str, flags: int = cv2.IMREAD_COLOR) -> Any | None:
    """读取任意路径的图片，包括 Windows 下的 Unicode 路径。

    首先尝试 ``cv2.imread``，直接读取失败后回退到
    ``np.fromfile + cv2.imdecode``。
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

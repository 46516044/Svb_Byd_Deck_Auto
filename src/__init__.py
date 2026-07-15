"""
影之诗自动对战脚本 - 核心模块包
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "Auto SZB Team"

__all__ = [
    "ConfigManager",
    "setup_gpu",
    "display_disclaimer_and_get_consent",
    "DeviceManager",
    "NotificationManager",
]


def __getattr__(name: str):
    """延迟重导出，避免包导入阶段加载 cv2、torch、u2 等重量级模块。"""

    if name == "ConfigManager":
        from src.config.config_manager import ConfigManager as _ConfigManager

        return _ConfigManager

    if name == "setup_gpu":
        from src.utils.gpu_utils import setup_gpu as _setup_gpu

        return _setup_gpu

    if name == "display_disclaimer_and_get_consent":
        from src.utils.consent_utils import (
            display_disclaimer_and_get_consent as _display_disclaimer_and_get_consent,
        )

        return _display_disclaimer_and_get_consent

    if name == "DeviceManager":
        from src.device.device_manager import DeviceManager as _DeviceManager

        return _DeviceManager

    if name == "NotificationManager":
        from src.ui.notification_manager import NotificationManager as _NotificationManager

        return _NotificationManager

    raise AttributeError(f"module 'src' has no attribute {name!r}")

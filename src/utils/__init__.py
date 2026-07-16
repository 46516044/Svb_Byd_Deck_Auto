"""
实用工具模块
提供各种辅助功能，包括GPU检测、资源管理、换牌策略等
"""

from __future__ import annotations

# 此处避免使用 ``import *``。许多工具依赖 cv2、torch 等重量级模块，
# 在包导入阶段提前加载会拖慢启动，并可能触发副作用。

__all__ = [
    "display_disclaimer_and_get_consent",
    "remove_consent",
    "setup_gpu",
    "get_easyocr_reader",
    "resource_path",
    "get_resource_path",
    "ensure_directory",
    "get_model_directory",
    "get_templates_directory",
]


def __getattr__(name: str):
    if name in {"display_disclaimer_and_get_consent", "remove_consent"}:
        from . import consent_utils as _consent_utils

        return getattr(_consent_utils, name)

    if name in {"setup_gpu", "get_easyocr_reader"}:
        from . import gpu_utils as _gpu_utils

        return getattr(_gpu_utils, name)

    if name in {
        "resource_path",
        "get_resource_path",
        "ensure_directory",
        "get_model_directory",
        "get_templates_directory",
    }:
        from . import resource_utils as _resource_utils

        return getattr(_resource_utils, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

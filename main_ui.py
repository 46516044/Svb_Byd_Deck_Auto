#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图形界面入口。

该文件仅保留启动所需的最小编排逻辑。
"""

from __future__ import annotations

import os
import sys

from src.utils.onnxruntime_dll import configure_onnxruntime_dll_search

configure_onnxruntime_dll_search()

# 设置环境变量以避免PyTorch的pin_memory警告
os.environ["PIN_MEMORY"] = "false"

# 添加项目目录到Python路径（兼容从任意工作目录启动）
_project_root = os.path.dirname(__file__)

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.app.bootstrap import run_gui


def main():
    sys.exit(run_gui(sys.argv))


if __name__ == "__main__":
    main()

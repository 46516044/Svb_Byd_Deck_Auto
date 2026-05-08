#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影之诗自动对战脚本 2025-07-27
"""

import sys
import os
import queue

from src.utils.onnxruntime_dll import configure_onnxruntime_dll_search

configure_onnxruntime_dll_search()

# 设置环境变量以避免PyTorch的pin_memory警告
os.environ["PIN_MEMORY"] = "false"

_project_root = os.path.dirname(__file__)

# 添加项目根目录到Python路径（确保 `import src.*` 可用）
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.app.bootstrap import run_cli

# 全局命令队列
command_queue = queue.Queue()
# 全局日志队列
log_queue = queue.Queue()

def main(enable_command_listener=True):
    """主函数"""
    run_cli(
        enable_command_listener=enable_command_listener,
        command_queue=command_queue,
        log_queue=log_queue,
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        # 在控制台保持打开（避免UI线程调用时阻塞）
        try:
            input("按回车键退出...")
        except EOFError:
            pass

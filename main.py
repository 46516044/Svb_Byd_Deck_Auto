#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影之诗自动对战脚本 2025-07-27
"""

import sys
import os
import queue
import ctypes

_DLL_DIR_HANDLES = []


def _configure_onnxruntime_dll_search() -> None:
    if os.name != "nt":
        return

    candidates = [
        os.path.join(sys.prefix, "Lib", "site-packages", "onnxruntime", "capi"),
    ]
    seen = set()
    for dll_dir in candidates:
        dll_dir = os.path.abspath(dll_dir)
        norm = os.path.normcase(dll_dir)
        if norm in seen or not os.path.isdir(dll_dir):
            continue
        seen.add(norm)
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if callable(add_dll_directory):
            try:
                _DLL_DIR_HANDLES.append(add_dll_directory(dll_dir))
            except Exception:
                pass
        current_path = os.environ.get("PATH", "")
        parts = current_path.split(os.pathsep) if current_path else []
        if all(os.path.normcase(os.path.abspath(p)) != norm for p in parts if p):
            os.environ["PATH"] = dll_dir + (os.pathsep + current_path if current_path else "")
        for name in ("onnxruntime.dll", "onnxruntime_providers_shared.dll"):
            full_path = os.path.join(dll_dir, name)
            if os.path.isfile(full_path):
                try:
                    ctypes.WinDLL(full_path)
                except Exception:
                    pass


_configure_onnxruntime_dll_search()

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

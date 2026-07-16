"""轻量级 JSON IO 辅助函数。

通过原子写入避免生成半截或损坏的 JSON 文件。模块仅依赖标准库，界面层和配置层
均可安全导入；落盘使用 ``os.replace``，兼容 Windows。
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Optional


def write_text_atomic(
    path: str,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """原子写入文本文件，并尽力执行 ``fsync``。"""

    abs_path = os.path.abspath(path)
    parent = os.path.dirname(abs_path) or os.curdir
    os.makedirs(parent, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                # 部分文件系统或平台不支持 fsync，失败时不影响原子替换流程。
                pass

        os.replace(tmp_path, abs_path)
    finally:
        # 替换前任一步骤失败时清理临时文件。
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def write_json_atomic(
    path: str,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    encoding: str = "utf-8",
) -> None:
    """原子写入 JSON，并在文件末尾保留换行。"""

    text = json.dumps(
        data,
        ensure_ascii=ensure_ascii,
        indent=int(indent),
        sort_keys=bool(sort_keys),
    )
    write_text_atomic(path, text + "\n", encoding=encoding)


def read_json(path: str, *, default: Optional[Any] = None, encoding: str = "utf-8") -> Any:
    """读取 JSON，失败时返回调用方提供的默认值。"""

    try:
        with open(path, "r", encoding=encoding) as f:
            return json.load(f)
    except Exception:
        return default

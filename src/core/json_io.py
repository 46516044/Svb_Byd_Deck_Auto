"""Lightweight JSON IO helpers.

Avoid partial/corrupted JSON files by using atomic writes.

Design constraints:
- stdlib-only (safe to import from UI/config layers)
- Windows-friendly (uses os.replace)
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
    """Atomically write a text file (best-effort fsync)."""

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
                # Some filesystems/platforms may not support fsync.
                pass

        os.replace(tmp_path, abs_path)
    finally:
        # If anything failed before replace, remove the temp file.
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
    """Atomically write JSON with a trailing newline."""

    text = json.dumps(
        data,
        ensure_ascii=ensure_ascii,
        indent=int(indent),
        sort_keys=bool(sort_keys),
    )
    write_text_atomic(path, text + "\n", encoding=encoding)


def read_json(path: str, *, default: Optional[Any] = None, encoding: str = "utf-8") -> Any:
    """Read JSON, returning default on failure."""

    try:
        with open(path, "r", encoding=encoding) as f:
            return json.load(f)
    except Exception:
        return default

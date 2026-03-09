"""PyInstaller runtime hook for stable ONNX Runtime DLL loading on Windows.

Reason:
- Some machines have a different `onnxruntime.dll` in `%SystemRoot%\\System32`.
- If that DLL is loaded before our bundled capi DLLs, importing
  `onnxruntime_pybind11_state` may fail with DLL init errors.

This hook ensures bundled `_internal/onnxruntime/capi` is searched first and
preloads the intended `onnxruntime.dll`/`onnxruntime_providers_shared.dll`.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from typing import List


_DLL_DIR_HANDLES: List[object] = []


def _load_win_dll_raw(full_path: str) -> None:
    """Load DLL via WinAPI directly (avoid PyInstaller ctypes shim)."""

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    load_library = kernel32.LoadLibraryW
    load_library.argtypes = [ctypes.c_wchar_p]
    load_library.restype = ctypes.c_void_p
    handle = load_library(full_path)
    if handle:
        return
    err = ctypes.get_last_error()
    raise OSError(err, f"LoadLibraryW failed for {full_path}")


def _dedupe_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        norm = os.path.normcase(os.path.abspath(item))
        if norm in seen:
            continue
        seen.add(norm)
        out.append(item)
    return out


def _collect_search_dirs() -> List[str]:
    exe_dir = os.path.dirname(sys.executable)
    meipass = getattr(sys, "_MEIPASS", "")

    candidates = [
        os.path.join(exe_dir, "_internal", "onnxruntime", "capi"),
        os.path.join(str(meipass or ""), "onnxruntime", "capi"),
        os.path.join(exe_dir, "_internal"),
        str(meipass or ""),
    ]
    return _dedupe_keep_order([d for d in candidates if d and os.path.isdir(d)])


def _prepend_path(path_dir: str) -> None:
    current = os.environ.get("PATH", "")
    if not current:
        os.environ["PATH"] = path_dir
        return

    parts = current.split(os.pathsep)
    norm_target = os.path.normcase(os.path.abspath(path_dir))
    for p in parts:
        if os.path.normcase(os.path.abspath(p)) == norm_target:
            return
    os.environ["PATH"] = path_dir + os.pathsep + current


def _configure_windows_dll_search(dirs: List[str]) -> None:
    global _DLL_DIR_HANDLES
    for d in dirs:
        _prepend_path(d)

    add_dir = getattr(os, "add_dll_directory", None)
    if not callable(add_dir):
        return

    for d in dirs:
        try:
            handle = add_dir(d)
            _DLL_DIR_HANDLES.append(handle)
        except Exception:
            pass


def _preload_onnxruntime(capi_dir: str) -> List[str]:
    messages: List[str] = []
    if not os.path.isdir(capi_dir):
        return messages

    for name in ("onnxruntime.dll", "onnxruntime_providers_shared.dll"):
        full = os.path.join(capi_dir, name)
        if not os.path.isfile(full):
            messages.append(f"missing:{name}")
            continue
        try:
            _load_win_dll_raw(full)
            messages.append(f"loaded:{name}")
        except Exception as e:
            messages.append(f"failed:{name}:{type(e).__name__}:{e}")
    return messages


def _loaded_onnxruntime_dll_path() -> str:
    if os.name != "nt":
        return ""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_module_handle = kernel32.GetModuleHandleW
        get_module_handle.argtypes = [ctypes.c_wchar_p]
        get_module_handle.restype = ctypes.c_void_p

        get_module_file = kernel32.GetModuleFileNameW
        get_module_file.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        get_module_file.restype = ctypes.c_uint32

        handle = get_module_handle("onnxruntime.dll")
        if not handle:
            return ""
        buf = ctypes.create_unicode_buffer(2048)
        n = get_module_file(handle, buf, 2048)
        if n <= 0:
            return ""
        return str(buf.value or "")
    except Exception:
        return ""


def _append_diag_line(msg: str) -> None:
    try:
        temp_dir = os.getenv("TEMP") or os.getenv("TMP") or os.getcwd()
        log_path = os.path.join(temp_dir, "byd_onnxruntime_hook.log")
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {msg}\\n")
    except Exception:
        pass


def _main() -> None:
    if os.name != "nt":
        return

    search_dirs = _collect_search_dirs()
    _append_diag_line(f"hook_start exe={sys.executable} meipass={getattr(sys, '_MEIPASS', '')}")
    _append_diag_line(f"hook_search_dirs={search_dirs}")
    if not search_dirs:
        return

    _configure_windows_dll_search(search_dirs)

    # Preload bundled ORT DLLs from capi dir (if present) so pybind binds to
    # the packaged binaries instead of a global system copy.
    preload_msgs: List[str] = []
    for d in search_dirs:
        if d.lower().endswith(os.path.join("onnxruntime", "capi").lower()):
            preload_msgs = _preload_onnxruntime(d)
            break
    _append_diag_line(f"hook_preload={preload_msgs}")

    loaded = _loaded_onnxruntime_dll_path()
    _append_diag_line(f"hook_loaded_onnxruntime={loaded}")


_main()

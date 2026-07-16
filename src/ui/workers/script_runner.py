"""界面脚本运行线程。"""

from __future__ import annotations

import time
import traceback
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal


class ScriptRunner(QThread):
    """脚本运行线程"""

    status_signal = pyqtSignal(str)
    stats_signal = pyqtSignal(dict)

    def __init__(
        self,
        run_main_script: Callable[..., object],
        log_queue,
        parent: Optional[QObject] = None,
        device_config=None,
    ):
        super().__init__(parent)
        self._run_main_script = run_main_script
        self._log_queue = log_queue
        self._device_config = device_config
        self.start_time = 0
        self.battle_count = 0
        self.turn_count = 0
        self.current_turn = 0

    def run(self):
        try:
            self.start_time = time.time()
            self.status_signal.emit("运行中")

            self._run_main_script(
                enable_command_listener=True, device_config=self._device_config
            )
        except Exception as e:
            try:
                self._log_queue.put(f"脚本运行出错: {str(e)}")
            except Exception:
                pass
            traceback.print_exc()
        finally:
            self.status_signal.emit("已停止")
            try:
                self._log_queue.put("===== 脚本运行结束 =====")
            except Exception:
                pass

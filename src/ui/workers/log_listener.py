"""Log listener thread for UI."""

from __future__ import annotations

import time
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal


class LogListener(QThread):
    """日志监听线程"""

    log_signal = pyqtSignal(str)

    def __init__(self, log_queue, parent: Optional[object] = None):
        super().__init__(parent)
        self._log_queue = log_queue
        self.running = True

    def run(self):
        while self.running:
            try:
                while not self._log_queue.empty():
                    log = self._log_queue.get_nowait()
                    self.log_signal.emit(log)
                time.sleep(0.1)
            except Exception as e:
                print(f"日志监听异常: {str(e)}")

    def stop(self):
        self.running = False

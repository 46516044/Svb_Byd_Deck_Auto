"""CLI、图形界面及内部模块共用的日志辅助函数。"""

from __future__ import annotations

import logging
import queue
from typing import Any, Dict, Optional


class QueueHandler(logging.Handler):
    """将格式化日志转发到队列的日志处理器。"""

    def __init__(self, log_queue: "queue.Queue[str]"):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            self.handleError(record)


def setup_logging(
    config: Dict[str, Any],
    log_queue: Optional["queue.Queue[str]"] = None,
    *,
    log_file: str = "main_log.log",
) -> logging.Logger:
    """只初始化一次根日志配置，并返回根记录器。"""

    log_level = getattr(logging, config.get("ui", {}).get("log_level", "INFO").upper())

    logger = logging.getLogger()
    logger.setLevel(log_level)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        if log_queue is not None:
            queue_handler = QueueHandler(log_queue)
            queue_handler.setFormatter(console_formatter)
            logger.addHandler(queue_handler)

    return logger

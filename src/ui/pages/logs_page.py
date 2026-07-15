"""桌面界面的可筛选完整日志页面。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from PyQt5.QtCore import QStandardPaths, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import COLORS


_LEVEL_LABELS = {
    "info": "INFO",
    "success": " OK ",
    "warning": "WARN",
    "error": "ERR ",
    "debug": "DBG ",
}

_LEVEL_COLORS = {
    "info": COLORS["text"],
    "success": COLORS["success"],
    "warning": COLORS["warning"],
    "error": COLORS["error"],
    "debug": COLORS["text_muted"],
}

_LEVEL_ALIASES = {
    "info": "info",
    "information": "info",
    "success": "success",
    "ok": "success",
    "warning": "warning",
    "warn": "warning",
    "error": "error",
    "err": "error",
    "critical": "error",
    "fatal": "error",
    "debug": "debug",
    "dbg": "debug",
}

_FORMATTED_LOG_RE = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:,\d+)?)"
    r"\s+-\s+(?:(?P<logger>.*?)\s+-\s+)?"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+-\s+"
    r"(?P<message>.*)$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class LogEntry:
    """独立于当前筛选条件保存的一条规范日志记录。"""

    timestamp: datetime
    level: str
    message: str

    def to_text(self) -> str:
        label = _LEVEL_LABELS[self.level].strip()
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} [{label}] {self.message}"


class LogsPage(QWidget):
    """支持级别、文本筛选及导出的完整日志查看器。"""

    logs_cleared = pyqtSignal()
    export_completed = pyqtSignal(str)
    export_failed = pyqtSignal(str)
    _append_requested = pyqtSignal(object, object, object)

    def __init__(self, parent: Optional[QWidget] = None, max_entries: int = 20_000):
        super().__init__(parent)
        self.setObjectName("LogsPage")
        self.setProperty("pageRoot", True)

        self._entries: List[LogEntry] = []
        self._visible_count = 0
        self._max_entries = max(1, int(max_entries))
        self._append_requested.connect(self._append_log_impl, Qt.QueuedConnection)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 24)
        root.setSpacing(14)

        heading_row = QHBoxLayout()
        heading_row.setSpacing(10)

        heading = QLabel("运行日志")
        heading.setProperty("heading", "page")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)

        self.count_label = QLabel("0 条日志")
        self.count_label.setProperty("muted", True)
        heading_row.addWidget(self.count_label)
        root.addLayout(heading_row)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        level_label = QLabel("级别")
        level_label.setProperty("muted", True)
        toolbar.addWidget(level_label)

        self.level_filter = QComboBox()
        self.level_filter.setObjectName("LogLevelFilter")
        self.level_filter.setMinimumWidth(112)
        self.level_filter.setToolTip("按日志级别筛选")
        self.level_filter.addItem("全部级别", "all")
        self.level_filter.addItem("信息", "info")
        self.level_filter.addItem("成功", "success")
        self.level_filter.addItem("警告", "warning")
        self.level_filter.addItem("错误", "error")
        self.level_filter.addItem("调试", "debug")
        self.level_filter.currentIndexChanged.connect(self._rebuild_view)
        toolbar.addWidget(self.level_filter)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("LogSearch")
        self.search_edit.setPlaceholderText("搜索日志内容")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setToolTip("输入关键字筛选日志")
        self.search_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_edit.textChanged.connect(self._rebuild_view)
        toolbar.addWidget(self.search_edit, 1)

        self.copy_button = QPushButton("复制全部")
        self.copy_button.setToolTip("将全部日志复制到剪贴板")
        self.copy_button.clicked.connect(self.copy_all)
        toolbar.addWidget(self.copy_button)

        self.export_button = QPushButton("导出")
        self.export_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.export_button.setToolTip("将全部日志导出为 UTF-8 文本文件")
        self.export_button.clicked.connect(self.export_logs)
        toolbar.addWidget(self.export_button)

        self.clear_button = QPushButton("清空")
        self.clear_button.setProperty("variant", "danger")
        trash_icon = getattr(QStyle, "SP_TrashIcon", None)
        if trash_icon is not None:
            self.clear_button.setIcon(self.style().standardIcon(trash_icon))
        self.clear_button.setToolTip("清空当前会话中的全部日志")
        self.clear_button.clicked.connect(self.clear_logs)
        toolbar.addWidget(self.clear_button)
        root.addLayout(toolbar)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogViewer")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.log_view.setPlaceholderText("运行日志将在这里显示")
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.log_view, 1)

        self.action_status = QLabel("")
        self.action_status.setProperty("dim", True)
        self.action_status.setMinimumHeight(18)
        root.addWidget(self.action_status)

    @property
    def entries(self) -> List[LogEntry]:
        """返回全部保留日志条目的快照。"""

        return list(self._entries)

    def append_log(
        self,
        message: object,
        level: Optional[object] = None,
        timestamp: Optional[Union[datetime, str]] = None,
    ) -> None:
        """追加一条日志消息。

        旧调用方可以只传 ``message``；显式级别可使用
        ``append_log(message, "warning")``，同时兼容演示代码采用的
        ``append_log("warning", message)`` 参数顺序。
        """

        if QThread.currentThread() != self.thread():
            self._append_requested.emit(message, level, timestamp)
            return
        self._append_log_impl(message, level, timestamp)

    def append(self, message: object) -> None:
        """兼容旧 ``QTextEdit`` 风格调用方的入口。"""

        self.append_log(message)

    def _append_log_impl(
        self,
        message: object,
        level: Optional[object],
        timestamp: Optional[Union[datetime, str]],
    ) -> None:
        raw_message = str(message or "")

        # 同时接受 ``append_log("warning", "message")``，与演示调用保持一致。
        first_as_level = self._normalize_level(raw_message)
        second_as_level = self._normalize_level(level)
        if level is not None and first_as_level and not second_as_level:
            raw_message, level = str(level), raw_message

        parsed = self._parse_formatted_log(raw_message)
        if parsed is not None:
            parsed_timestamp, parsed_level, parsed_message = parsed
            timestamp = timestamp or parsed_timestamp
            level = level or parsed_level
            raw_message = parsed_message

        normalized_level = self._normalize_level(level)
        if normalized_level is None:
            normalized_level = self._infer_level(raw_message)

        entry = LogEntry(
            timestamp=self._coerce_timestamp(timestamp),
            level=normalized_level,
            message=raw_message.rstrip("\r\n"),
        )
        self._entries.append(entry)

        overflow = len(self._entries) - self._max_entries
        if overflow > 0:
            del self._entries[:overflow]
            self._rebuild_view()
            return

        if self._matches(entry):
            self._visible_count += 1
            self._insert_entry(entry)
        self._update_count_label()

    def clear_logs(self) -> None:
        """同时清空显示内容和保留的导出数据。"""

        self._entries.clear()
        self._visible_count = 0
        self.log_view.clear()
        self._update_count_label()
        self._set_action_status("")
        self.action_status.setText("日志已清空")
        self.logs_cleared.emit()

    def copy_all(self) -> str:
        """复制全部保留日志，并返回复制的文本。"""

        text = self._all_logs_text()
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self._set_action_status("")
        self.action_status.setText(f"已复制 {len(self._entries)} 条日志")
        return text

    def export_logs(self, file_path: Optional[Union[str, Path]] = None) -> Optional[str]:
        """将全部保留日志导出为 UTF-8 文本文件。

        显式提供 ``file_path`` 时跳过文件对话框，便于集成代码和自动化检查调用。
        """

        interactive = not file_path
        target = str(file_path) if file_path else ""
        if not target:
            documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            base_dir = Path(documents) if documents else Path.home()
            suggested = base_dir / f"sv-auto-{datetime.now():%Y%m%d-%H%M%S}.log"
            target, _ = QFileDialog.getSaveFileName(
                self,
                "导出运行日志",
                str(suggested),
                "日志文件 (*.log);;文本文件 (*.txt);;所有文件 (*)",
            )
        if not target:
            return None

        try:
            output = Path(target)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(self._all_logs_text(), encoding="utf-8")
        except (OSError, ValueError) as exc:
            message = f"日志导出失败：{exc}"
            self._set_action_status("error", message)
            self.export_failed.emit(message)
            if interactive:
                QMessageBox.warning(self, "导出失败", message)
            return None

        resolved = str(output.resolve())
        self._set_action_status("success", f"日志已导出：{resolved}")
        self.export_completed.emit(resolved)
        return resolved

    def set_level_filter(self, level: str) -> None:
        """通过程序选择筛选条件。"""

        normalized = self._normalize_level(level) or "all"
        index = self.level_filter.findData(normalized)
        self.level_filter.setCurrentIndex(index if index >= 0 else 0)

    def set_search_text(self, text: str) -> None:
        self.search_edit.setText(str(text or ""))

    def _rebuild_view(self, *_args: object) -> None:
        self.log_view.setUpdatesEnabled(False)
        self.log_view.clear()
        self._visible_count = 0
        for entry in self._entries:
            if self._matches(entry):
                self._visible_count += 1
                self._insert_entry(entry, keep_scroll=False)
        self.log_view.setUpdatesEnabled(True)
        self.log_view.viewport().update()
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self._update_count_label()

    def _insert_entry(self, entry: LogEntry, keep_scroll: bool = True) -> None:
        scrollbar = self.log_view.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 4

        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.log_view.document().isEmpty():
            cursor.insertBlock()

        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor(COLORS["text_muted"]))
        cursor.insertText(f"[{entry.timestamp:%H:%M:%S}] ", timestamp_format)

        level_format = QTextCharFormat()
        level_format.setForeground(QColor(_LEVEL_COLORS[entry.level]))
        level_format.setFontWeight(QFont.DemiBold)
        cursor.insertText(f"[{_LEVEL_LABELS[entry.level]}] ", level_format)

        message_format = QTextCharFormat()
        message_format.setForeground(QColor(_LEVEL_COLORS[entry.level]))
        cursor.insertText(entry.message, message_format)
        self.log_view.setTextCursor(cursor)

        if not keep_scroll or was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _matches(self, entry: LogEntry) -> bool:
        selected_level = self.level_filter.currentData() or "all"
        if selected_level != "all" and entry.level != selected_level:
            return False
        query = self.search_edit.text().strip().casefold()
        if query and query not in entry.message.casefold():
            return False
        return True

    def _update_count_label(self) -> None:
        visible = self._visible_count
        total = len(self._entries)
        if visible == total:
            self.count_label.setText(f"{total} 条日志")
        else:
            self.count_label.setText(f"显示 {visible} / {total} 条")

    def _all_logs_text(self) -> str:
        return "\n".join(entry.to_text() for entry in self._entries)

    def _set_action_status(self, status: str, text: Optional[str] = None) -> None:
        self.action_status.setProperty("status", status)
        self.action_status.style().unpolish(self.action_status)
        self.action_status.style().polish(self.action_status)
        if text is not None:
            self.action_status.setText(text)

    @staticmethod
    def _normalize_level(level: Optional[object]) -> Optional[str]:
        if level is None:
            return None
        return _LEVEL_ALIASES.get(str(level).strip().lower())

    @classmethod
    def _infer_level(cls, message: str) -> str:
        bracketed = re.search(
            r"\[(DEBUG|DBG|INFO|SUCCESS|OK|WARNING|WARN|ERROR|ERR|CRITICAL)\]",
            message,
            re.IGNORECASE,
        )
        if bracketed:
            return cls._normalize_level(bracketed.group(1)) or "info"

        lowered = message.casefold()
        if any(word in lowered for word in ("traceback", "exception", "error", "失败", "错误", "异常")):
            return "error"
        if any(word in lowered for word in ("warning", "warn", "警告", "超时")):
            return "warning"
        if any(word in lowered for word in ("success", "成功", "已完成", "完成加载", "已保存")):
            return "success"
        if any(word in lowered for word in ("debug", "调试")):
            return "debug"
        return "info"

    @classmethod
    def _parse_formatted_log(cls, message: str):
        matched = _FORMATTED_LOG_RE.match(message)
        if matched is None:
            return None

        stamp_text = matched.group("stamp")
        parsed_stamp = cls._coerce_timestamp(stamp_text)
        level = cls._normalize_level(matched.group("level")) or "info"
        logger_name = (matched.group("logger") or "").strip()
        clean_message = matched.group("message")
        if logger_name:
            clean_message = f"{logger_name} - {clean_message}"
        return parsed_stamp, level, clean_message

    @staticmethod
    def _coerce_timestamp(value: Optional[Union[datetime, str]]) -> datetime:
        if isinstance(value, datetime):
            return value
        if value:
            text = str(value).strip().replace("T", " ")
            for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
        return datetime.now()


# 保留单数形式，作为便于导入的别名。
LogPage = LogsPage

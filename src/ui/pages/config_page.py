#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Config page (parameters/settings)."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.paths import get_config_path
from src.config.config_repository import ConfigRepository


# PyQt5 stubs vary across environments; keep Qt attribute access flexible.
Qt: Any = _Qt


class ConfigPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget: Any = parent
        self.config_data = self.load_config()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        # 标题
        title_label = QLabel("参数设置")
        title_label.setStyleSheet(
            "font-size: 20px; color: #88AAFF; font-weight: bold;"
        )
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 拖拽速度设置
        drag_group = QGroupBox("拖拽速度设置 (单位:秒)")
        drag_layout = QGridLayout(drag_group)

        # 获取当前拖拽速度设置 - 修复1: 确保正确读取配置
        drag_range = [0.10, 0.13]  # 默认值
        if (
            "game" in self.config_data
            and "human_like_drag_duration_range" in self.config_data["game"]
        ):
            drag_range = self.config_data["game"]["human_like_drag_duration_range"]

        drag_layout.addWidget(QLabel("最小拖拽时间:"), 0, 0)
        self.min_drag_input = QLineEdit(str(drag_range[0]))
        self.min_drag_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        drag_layout.addWidget(self.min_drag_input, 0, 1)

        drag_layout.addWidget(QLabel("最大拖拽时间:"), 1, 0)
        self.max_drag_input = QLineEdit(str(drag_range[1]))
        self.max_drag_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        drag_layout.addWidget(self.max_drag_input, 1, 1)

        drag_layout.addWidget(
            QLabel("说明: 设置更小的值会使操作更快，但可能被检测为脚本"), 2, 0, 1, 2
        )

        main_layout.addWidget(drag_group)

        # 运行设置
        run_group = QGroupBox("运行设置")
        run_layout = QVBoxLayout(run_group)

        # 自动重启设置子区域
        auto_restart_layout = QGridLayout()

        # 获取当前自动重启设置
        auto_restart_config = self.config_data.get("auto_restart", {})
        self.auto_restart_enabled = auto_restart_config.get("enabled", True)
        stage_timeout_seconds = auto_restart_config.get("stage_timeout", 300)
        self.stage_timeout = int(stage_timeout_seconds) // 60
        if self.stage_timeout <= 0:
            self.stage_timeout = 5
        try:
            self.max_restarts = int(auto_restart_config.get("max_restarts", 3))
        except Exception:
            self.max_restarts = 3

        run_settings = self.config_data.get("run_settings", {})
        try:
            self.max_run_duration_minutes = int(
                run_settings.get("max_run_duration", 0) or 0
            ) // 60
        except Exception:
            self.max_run_duration_minutes = 0

        # 启用/禁用复选框
        self.restart_enabled_checkbox = QCheckBox("启用自动重启功能")
        self.restart_enabled_checkbox.setChecked(self.auto_restart_enabled)
        self.restart_enabled_checkbox.setStyleSheet("color: #FFFFFF;")
        auto_restart_layout.addWidget(self.restart_enabled_checkbox, 0, 0, 1, 2)

        # 无新阶段重启时间输入
        auto_restart_layout.addWidget(QLabel("无新阶段自动重启时间 (分钟):"), 1, 0)
        self.restart_time_input = QLineEdit(str(self.stage_timeout))
        self.restart_time_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        self.restart_time_input.setEnabled(self.auto_restart_enabled)
        auto_restart_layout.addWidget(self.restart_time_input, 1, 1)

        # 自动重启最大次数输入
        auto_restart_layout.addWidget(QLabel("自动重启最大次数:"), 2, 0)
        self.restart_count_input = QLineEdit(str(self.max_restarts))
        self.restart_count_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        self.restart_count_input.setEnabled(self.auto_restart_enabled)
        auto_restart_layout.addWidget(self.restart_count_input, 2, 1)

        # 连接复选框状态变化信号
        self.restart_enabled_checkbox.stateChanged.connect(self.on_restart_enabled_changed)

        # 添加说明
        auto_restart_layout.addWidget(
            QLabel(
                "说明: 设置无新阶段自动重启间隔与最大重启次数；达到次数后再次触发将停止脚本。"
            ),
            3,
            0,
            1,
            2,
        )

        # 将自动重启设置添加到运行设置中
        auto_restart_widget = QWidget()
        auto_restart_widget.setLayout(auto_restart_layout)
        run_layout.addWidget(auto_restart_widget)

        # 脚本总时长设置
        runtime_limit_layout = QGridLayout()
        runtime_limit_layout.addWidget(QLabel("脚本运行总时长 (分钟):"), 0, 0)
        self.runtime_limit_input = QLineEdit(str(self.max_run_duration_minutes))
        self.runtime_limit_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        runtime_limit_layout.addWidget(self.runtime_limit_input, 0, 1)
        runtime_limit_layout.addWidget(
            QLabel("说明: 到达总时长后不会立刻中断，会在当前对战结束后自动停止。0表示不限制。"),
            1,
            0,
            1,
            2,
        )

        runtime_limit_widget = QWidget()
        runtime_limit_widget.setLayout(runtime_limit_layout)
        run_layout.addWidget(runtime_limit_widget)

        main_layout.addWidget(run_group)

        # 出牌设置
        play_group = QGroupBox("出牌设置")
        play_layout = QVBoxLayout(play_group)

        # 换牌策略设置
        strategy_selection_layout = QHBoxLayout()
        strategy_selection_layout.addWidget(QLabel("选择换牌策略:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["3费档次", "4费档次", "5费档次"])
        self.strategy_combo.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )

        current_strategy = self.config_data.get("game", {}).get(
            "card_replacement_strategy", "3费档次"
        )
        index = self.strategy_combo.findText(current_strategy)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        strategy_selection_layout.addWidget(self.strategy_combo)

        self.strategy_help_btn = QPushButton("帮助")
        self.strategy_help_btn.clicked.connect(self.show_strategy_help)
        strategy_selection_layout.addWidget(self.strategy_help_btn)

        play_layout.addLayout(strategy_selection_layout)

        strategy_desc = QLabel(
            "说明: 根据费用档次策略自动换牌，确保关键回合能准时展开，每次切换换牌策略后，需重启软件才能生效。"
        )
        strategy_desc.setStyleSheet("font-size: 12px; color: #AACCFF;")
        play_layout.addWidget(strategy_desc)

        main_layout.addWidget(play_group)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存设置")
        self.save_btn.clicked.connect(self.save_config)
        self.back_btn = QPushButton("返回主界面")
        self.back_btn.clicked.connect(self._go_back)

        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.back_btn)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

    def _go_back(self) -> None:
        try:
            sw = getattr(self.parent_widget, "stacked_widget", None)
            if sw is not None and hasattr(sw, "setCurrentIndex"):
                sw.setCurrentIndex(0)
        except Exception:
            pass

    def on_restart_enabled_changed(self):
        """处理自动重启功能启用/禁用状态变化"""

        self.restart_time_input.setEnabled(self.restart_enabled_checkbox.isChecked())
        self.restart_count_input.setEnabled(self.restart_enabled_checkbox.isChecked())

    def show_strategy_help(self):
        """显示换牌策略说明"""

        help_text = """
换牌策略说明：

【3费档次】
• 最优：前三张牌组合为 [1,2,3]
• 次优：牌序为2，3
• 目标：确保3费时能准时打出

【4费档次】
• 最优：四张牌组合为 [1,2,3,4]
• 次优：牌序为 [2,3,4] 或 [2,2,4]
• 目标：确保4费时能有效展开

【5费档次】
• 优先级组合（从高到低）：
[2,3,4,5] > [2,3,3,5] > [2,2,3,5] > [2,2,2,5]
• 目标：确保5费时能打出关键牌
"""
        msg = QMessageBox()
        msg.setWindowTitle("换牌策略说明")
        msg.setText(help_text)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()

    def load_config(self):
        """加载配置文件"""
        config_path = get_config_path()
        cfg, _, _ = ConfigRepository(config_path).load_existing(allow_default_on_error=True)
        return cfg if isinstance(cfg, dict) else {}

    def save_config(self):
        """保存配置到文件"""

        try:
            if getattr(self.parent_widget, "is_script_running", lambda: False)():
                QMessageBox.warning(
                    self,
                    "运行中",
                    "脚本运行中，禁止修改配置。请先停止脚本后再保存。",
                )
                return
        except Exception:
            pass

        try:
            min_drag = float(self.min_drag_input.text())
            max_drag = float(self.max_drag_input.text())

            if min_drag < 0 or max_drag < 0:
                raise ValueError("拖拽时间不能为负数")
            if min_drag > max_drag:
                raise ValueError("最小拖拽时间不能大于最大拖拽时间")

            if "game" not in self.config_data:
                self.config_data["game"] = {}
            self.config_data["game"]["human_like_drag_duration_range"] = [min_drag, max_drag]
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"拖拽时间设置错误: {str(e)}")
            return

        try:
            if "auto_restart" not in self.config_data:
                self.config_data["auto_restart"] = {}
            self.config_data["auto_restart"]["enabled"] = self.restart_enabled_checkbox.isChecked()

            if self.restart_enabled_checkbox.isChecked():
                restart_time = int(self.restart_time_input.text())
                if restart_time < 1 or restart_time > 120:
                    raise ValueError("自动重启时间必须在1-120分钟之间")
                self.config_data["auto_restart"]["stage_timeout"] = restart_time * 60

                max_restarts = int(self.restart_count_input.text())
                if max_restarts < 1 or max_restarts > 20:
                    raise ValueError("自动重启最大次数必须在1-20之间")
                self.config_data["auto_restart"]["max_restarts"] = max_restarts

            self.config_data["auto_restart"].pop("output_timeout", None)
            self.config_data["auto_restart"].pop("match_timeout", None)

            if "stage_timeout" not in self.config_data["auto_restart"]:
                self.config_data["auto_restart"]["stage_timeout"] = 300
            if "max_restarts" not in self.config_data["auto_restart"]:
                self.config_data["auto_restart"]["max_restarts"] = 3
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"自动重启设置错误: {str(e)}")
            return

        try:
            runtime_limit = int(self.runtime_limit_input.text())
            if runtime_limit < 0 or runtime_limit > 10080:
                raise ValueError("脚本运行总时长必须在0-10080分钟之间")
            if "run_settings" not in self.config_data:
                self.config_data["run_settings"] = {}
            self.config_data["run_settings"]["max_run_duration"] = runtime_limit * 60
            self.config_data["run_settings"].pop("max_battle_count", None)
            self.config_data["run_settings"].pop("force_close", None)
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"脚本总时长设置错误: {str(e)}")
            return

        strategy = self.strategy_combo.currentText()
        if "game" not in self.config_data:
            self.config_data["game"] = {}
        self.config_data["game"]["card_replacement_strategy"] = strategy

        config_path = get_config_path()
        try:
            repo = ConfigRepository(config_path)
            res = repo.update(self.config_data, indent=4, ensure_ascii=False)
            if not res.ok:
                raise RuntimeError(res.error or "config write failed")

            if res.parse_ok:
                QMessageBox.information(self, "成功", "配置已保存！")
            else:
                QMessageBox.information(self, "成功", "配置已保存（原config.json解析失败，已重建）")
            try:
                log_output = getattr(self.parent_widget, "log_output", None)
                if log_output is not None and hasattr(log_output, "append"):
                    log_output.append("[配置] 参数设置已更新")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存配置文件时出错: {str(e)}")

    def refresh_config_display(self):
        """刷新整个配置页面的显示"""

        self.config_data = self.load_config()

        drag_range = [0.10, 0.13]
        if (
            "game" in self.config_data
            and "human_like_drag_duration_range" in self.config_data["game"]
        ):
            drag_range = self.config_data["game"]["human_like_drag_duration_range"]
        self.min_drag_input.setText(str(drag_range[0]))
        self.max_drag_input.setText(str(drag_range[1]))

        auto_restart_config = self.config_data.get("auto_restart", {})
        self.auto_restart_enabled = auto_restart_config.get("enabled", True)
        stage_timeout_seconds = auto_restart_config.get("stage_timeout", 300)
        self.stage_timeout = int(stage_timeout_seconds) // 60
        if self.stage_timeout <= 0:
            self.stage_timeout = 5
        self.max_restarts = auto_restart_config.get("max_restarts", 3)
        self.restart_enabled_checkbox.setChecked(self.auto_restart_enabled)
        self.restart_time_input.setText(str(self.stage_timeout))
        self.restart_count_input.setText(str(self.max_restarts))
        self.restart_time_input.setEnabled(self.auto_restart_enabled)
        self.restart_count_input.setEnabled(self.auto_restart_enabled)

        run_settings = self.config_data.get("run_settings", {})
        try:
            self.max_run_duration_minutes = int(
                run_settings.get("max_run_duration", 0) or 0
            ) // 60
        except Exception:
            self.max_run_duration_minutes = 0
        self.runtime_limit_input.setText(str(self.max_run_duration_minutes))

        current_strategy = self.config_data.get("game", {}).get(
            "card_replacement_strategy", "3费档次"
        )
        index = self.strategy_combo.findText(current_strategy)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        return

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Config page (parameters/settings)."""

from __future__ import annotations

from typing import Any, Tuple

from PyQt5.QtCore import Qt as _Qt, pyqtSignal
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.config.paths import get_config_path
from src.config.config_repository import ConfigRepository


# PyQt5 stubs vary across environments; keep Qt attribute access flexible.
Qt: Any = _Qt


class ConfigPage(QWidget):
    config_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget: Any = parent
        self.config_data = self.load_config()
        self.init_ui()

    def init_ui(self):
        self.setObjectName("SettingsPage")
        self.setProperty("pageRoot", True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 22, 24, 20)
        main_layout.setSpacing(16)

        title_label = QLabel("参数设置")
        title_label.setObjectName("PageTitle")
        title_label.setProperty("heading", "page")
        main_layout.addWidget(title_label)

        subtitle_label = QLabel("统一管理操作速度、运行限制和换牌策略")
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setProperty("muted", True)
        main_layout.addWidget(subtitle_label)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName("SettingsScrollArea")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll.setAutoFillBackground(False)
        self.settings_scroll.viewport().setAutoFillBackground(False)

        settings_content = QWidget()
        settings_content.setObjectName("SettingsContent")
        settings_content.setProperty("pageRoot", True)
        content_layout = QVBoxLayout(settings_content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(14)

        drag_range = self._read_drag_range()
        basic_panel, basic_layout = self._create_section(
            "基础设置",
            "调整模拟点击拖拽的持续时间。数值越小操作越快，稳定性也会相应降低。",
            "BasicSettingsPanel",
        )
        basic_form = QGridLayout()
        self._configure_form_layout(basic_form)

        drag_validator = QDoubleValidator(0.0, 999999.0, 3, self)
        drag_validator.setNotation(QDoubleValidator.StandardNotation)

        self.min_drag_input = self._create_line_edit(
            str(drag_range[0]), "MinDragDurationInput"
        )
        self.min_drag_input.setValidator(drag_validator)
        self.max_drag_input = self._create_line_edit(
            str(drag_range[1]), "MaxDragDurationInput"
        )
        max_drag_validator = QDoubleValidator(0.0, 999999.0, 3, self)
        max_drag_validator.setNotation(QDoubleValidator.StandardNotation)
        self.max_drag_input.setValidator(max_drag_validator)

        self._add_form_row(
            basic_form,
            0,
            "最小拖拽时间",
            self.min_drag_input,
            "秒",
            "每次拖拽采用区间内的随机时长。",
        )
        self._add_form_row(
            basic_form,
            2,
            "最大拖拽时间",
            self.max_drag_input,
            "秒",
            "必须大于或等于最小拖拽时间。",
        )
        basic_layout.addLayout(basic_form)
        content_layout.addWidget(basic_panel)

        self._load_run_values()
        run_panel, run_layout = self._create_section(
            "运行设置",
            "控制异常阶段恢复、重启次数以及脚本单次运行上限。",
            "RunSettingsPanel",
        )

        restart_header = QHBoxLayout()
        restart_header.setSpacing(12)
        self.restart_enabled_checkbox = QCheckBox("启用自动重启")
        self.restart_enabled_checkbox.setObjectName("AutoRestartCheckBox")
        self.restart_enabled_checkbox.setChecked(self.auto_restart_enabled)
        restart_header.addWidget(self.restart_enabled_checkbox)
        restart_header.addStretch(1)
        restart_note = QLabel("长时间没有进入新阶段时尝试恢复游戏")
        restart_note.setObjectName("SettingsInlineHint")
        restart_note.setProperty("muted", True)
        restart_header.addWidget(restart_note)
        run_layout.addLayout(restart_header)

        run_form = QGridLayout()
        self._configure_form_layout(run_form)
        self.restart_time_input = self._create_line_edit(
            str(self.stage_timeout), "RestartIntervalInput"
        )
        self.restart_time_input.setValidator(QIntValidator(1, 120, self))
        self.restart_count_input = self._create_line_edit(
            str(self.max_restarts), "RestartCountInput"
        )
        self.restart_count_input.setValidator(QIntValidator(1, 20, self))
        self.runtime_limit_input = self._create_line_edit(
            str(self.max_run_duration_minutes), "RuntimeLimitInput"
        )
        self.runtime_limit_input.setValidator(QIntValidator(0, 10080, self))

        self._add_form_row(
            run_form,
            0,
            "无新阶段重启间隔",
            self.restart_time_input,
            "分钟",
            "允许范围 1-120 分钟。",
        )
        self._add_form_row(
            run_form,
            2,
            "自动重启最大次数",
            self.restart_count_input,
            "次",
            "达到次数后再次触发将停止脚本，允许范围 1-20 次。",
        )
        self._add_form_row(
            run_form,
            4,
            "脚本运行总时长",
            self.runtime_limit_input,
            "分钟",
            "0 表示不限制；达到上限后会等待当前对战结束再停止。",
        )
        run_layout.addLayout(run_form)
        content_layout.addWidget(run_panel)

        strategy_panel, strategy_layout = self._create_section(
            "策略设置",
            "选择自动换牌使用的费用曲线。策略变更将在重启软件后完整生效。",
            "StrategySettingsPanel",
        )
        strategy_row = QHBoxLayout()
        strategy_row.setSpacing(12)
        strategy_label = QLabel("换牌策略")
        strategy_label.setObjectName("SettingsFieldLabel")
        strategy_row.addWidget(strategy_label)

        self.strategy_combo = QComboBox()
        self.strategy_combo.setObjectName("ReplacementStrategyCombo")
        self.strategy_combo.addItems(["3费档次", "4费档次", "5费档次"])
        self.strategy_combo.setMinimumWidth(220)
        current_strategy = self.config_data.get("game", {}).get(
            "card_replacement_strategy", "3费档次"
        )
        index = self.strategy_combo.findText(current_strategy)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        strategy_row.addWidget(self.strategy_combo)

        self.strategy_help_btn = QPushButton("查看规则")
        self.strategy_help_btn.setObjectName("SecondaryButton")
        self.strategy_help_btn.clicked.connect(self.show_strategy_help)
        strategy_row.addWidget(self.strategy_help_btn)
        strategy_row.addStretch(1)
        strategy_layout.addLayout(strategy_row)
        content_layout.addWidget(strategy_panel)
        content_layout.addStretch(1)

        self.settings_scroll.setWidget(settings_content)
        main_layout.addWidget(self.settings_scroll, 1)

        footer = QFrame()
        footer.setObjectName("SettingsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(12)
        save_hint = QLabel("设置只会在点击保存后写入 config.json")
        save_hint.setObjectName("SettingsSaveHint")
        save_hint.setProperty("muted", True)
        footer_layout.addWidget(save_hint)
        footer_layout.addStretch(1)
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setProperty("variant", "primary")
        self.save_btn.setMinimumWidth(120)
        self.save_btn.clicked.connect(self.save_config)
        footer_layout.addWidget(self.save_btn)
        main_layout.addWidget(footer)

        self.restart_enabled_checkbox.stateChanged.connect(
            self.on_restart_enabled_changed
        )
        self.on_restart_enabled_changed()

        self.setTabOrder(self.min_drag_input, self.max_drag_input)
        self.setTabOrder(self.max_drag_input, self.restart_enabled_checkbox)
        self.setTabOrder(self.restart_enabled_checkbox, self.restart_time_input)
        self.setTabOrder(self.restart_time_input, self.restart_count_input)
        self.setTabOrder(self.restart_count_input, self.runtime_limit_input)
        self.setTabOrder(self.runtime_limit_input, self.strategy_combo)
        self.setTabOrder(self.strategy_combo, self.strategy_help_btn)
        self.setTabOrder(self.strategy_help_btn, self.save_btn)

    def _read_drag_range(self) -> Tuple[float, float]:
        drag_range = self.config_data.get("game", {}).get(
            "human_like_drag_duration_range", [0.10, 0.13]
        )
        try:
            return float(drag_range[0]), float(drag_range[1])
        except (IndexError, TypeError, ValueError):
            return 0.10, 0.13

    def _load_run_values(self) -> None:
        auto_restart_config = self.config_data.get("auto_restart", {})
        self.auto_restart_enabled = bool(auto_restart_config.get("enabled", True))
        try:
            self.stage_timeout = int(
                auto_restart_config.get("stage_timeout", 300)
            ) // 60
        except (TypeError, ValueError):
            self.stage_timeout = 5
        if self.stage_timeout <= 0:
            self.stage_timeout = 5
        try:
            self.max_restarts = int(auto_restart_config.get("max_restarts", 3))
        except (TypeError, ValueError):
            self.max_restarts = 3

        run_settings = self.config_data.get("run_settings", {})
        try:
            self.max_run_duration_minutes = int(
                run_settings.get("max_run_duration", 0) or 0
            ) // 60
        except (TypeError, ValueError):
            self.max_run_duration_minutes = 0

    def _create_section(
        self, title: str, description: str, object_name: str
    ) -> Tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName(object_name)
        panel.setProperty("card", True)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("SettingsSectionTitle")
        title_label.setProperty("heading", "section")
        description_label = QLabel(description)
        description_label.setObjectName("SettingsSectionDescription")
        description_label.setProperty("muted", True)
        description_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        return panel, layout

    @staticmethod
    def _configure_form_layout(layout: QGridLayout) -> None:
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(5)
        layout.setColumnMinimumWidth(0, 180)
        layout.setColumnMinimumWidth(1, 180)
        layout.setColumnStretch(3, 1)

    def _create_line_edit(self, text: str, object_name: str) -> QLineEdit:
        line_edit = QLineEdit(text)
        line_edit.setObjectName(object_name)
        line_edit.setMaximumWidth(220)
        line_edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return line_edit

    @staticmethod
    def _add_form_row(
        layout: QGridLayout,
        row: int,
        label_text: str,
        editor: QWidget,
        unit_text: str,
        hint_text: str,
    ) -> None:
        label = QLabel(label_text)
        label.setObjectName("SettingsFieldLabel")
        unit = QLabel(unit_text)
        unit.setObjectName("SettingsUnitLabel")
        unit.setProperty("muted", True)
        hint = QLabel(hint_text)
        hint.setObjectName("SettingsFieldHint")
        hint.setProperty("dim", True)
        hint.setWordWrap(True)
        layout.addWidget(label, row, 0)
        layout.addWidget(editor, row, 1)
        layout.addWidget(unit, row, 2)
        layout.addWidget(hint, row + 1, 1, 1, 3)

    def _go_back(self) -> None:
        try:
            sw = getattr(self.parent_widget, "stacked_widget", None)
            if sw is not None and hasattr(sw, "setCurrentIndex"):
                sw.setCurrentIndex(0)
        except Exception:
            pass

    def on_restart_enabled_changed(self, *_args):
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
            self.config_saved.emit(dict(self.config_data))
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

        drag_range = self._read_drag_range()
        self.min_drag_input.setText(str(drag_range[0]))
        self.max_drag_input.setText(str(drag_range[1]))

        self._load_run_values()
        self.restart_enabled_checkbox.setChecked(self.auto_restart_enabled)
        self.restart_time_input.setText(str(self.stage_timeout))
        self.restart_count_input.setText(str(self.max_restarts))
        self.runtime_limit_input.setText(str(self.max_run_duration_minutes))
        self.on_restart_enabled_changed()

        current_strategy = self.config_data.get("game", {}).get(
            "card_replacement_strategy", "3费档次"
        )
        index = self.strategy_combo.findText(current_strategy)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        return

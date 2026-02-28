#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Config page (parameters/settings)."""

from __future__ import annotations

import json
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
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
from src.ui.common import deep_update_dict, get_exe_dir
from src.utils.card_filename import parse_card_filename


class ConfigPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.config_data = self.load_config()
        self.card_widgets = []
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
        self.output_timeout = auto_restart_config.get("output_timeout", 300) // 60  # 转换为分钟

        # 启用/禁用复选框
        self.restart_enabled_checkbox = QCheckBox("启用自动重启功能")
        self.restart_enabled_checkbox.setChecked(self.auto_restart_enabled)
        self.restart_enabled_checkbox.setStyleSheet("color: #FFFFFF;")
        auto_restart_layout.addWidget(self.restart_enabled_checkbox, 0, 0, 1, 2)

        # 无操作重启时间输入
        auto_restart_layout.addWidget(QLabel("无操作自动重启时间 (分钟):"), 1, 0)
        self.restart_time_input = QLineEdit(str(self.output_timeout))
        self.restart_time_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        self.restart_time_input.setEnabled(self.auto_restart_enabled)
        auto_restart_layout.addWidget(self.restart_time_input, 1, 1)

        # 连接复选框状态变化信号
        self.restart_enabled_checkbox.stateChanged.connect(self.on_restart_enabled_changed)

        # 添加说明
        auto_restart_layout.addWidget(
            QLabel(
                "说明: 设置无操作后自动重启游戏的时间间隔，建议设置在3-10分钟之间"
            ),
            2,
            0,
            1,
            2,
        )

        # 将自动重启设置添加到运行设置中
        auto_restart_widget = QWidget()
        auto_restart_widget.setLayout(auto_restart_layout)
        run_layout.addWidget(auto_restart_widget)

        # 运行终止条件设置
        termination_layout = QGridLayout()

        # 运行时长设置
        termination_layout.addWidget(QLabel("运行时长 (分钟):"), 0, 0)
        self.run_duration_input = QLineEdit("0")
        self.run_duration_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        termination_layout.addWidget(self.run_duration_input, 0, 1)

        # 对战次数阈值设置
        termination_layout.addWidget(QLabel("对战次数阈值:"), 1, 0)
        self.battle_count_input = QLineEdit("0")
        self.battle_count_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )
        termination_layout.addWidget(self.battle_count_input, 1, 1)

        # 添加说明
        termination_layout.addWidget(
            QLabel(
                "说明: 运行时长或对战次数达到设定值时，脚本将会关闭模拟器上的所有程序，并自动停止运行。设置为0表示不限制。"
            ),
            2,
            0,
            1,
            2,
        )
        termination_layout.addWidget(
            QLabel(
                "对战次数检测目前内测来看并不准确，大概率可能会把不正常的对战次数给算进去，导致脚本提前结束，如需使用对战次数检测，建议设置的数值大一点，最好是原本想对战次数的2倍或3倍。"
            ),
            3,
            0,
            1,
            2,
        )

        # 将终止条件设置添加到运行设置中
        termination_widget = QWidget()
        termination_widget.setLayout(termination_layout)
        run_layout.addWidget(termination_widget)

        # 关闭模式选择和帮助按钮（横向对齐）
        close_mode_layout = QVBoxLayout()

        # 将关闭模式设置添加到运行设置中
        close_mode_widget = QWidget()
        close_mode_widget.setLayout(close_mode_layout)
        run_layout.addWidget(close_mode_widget)

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
        self.back_btn.clicked.connect(lambda: self.parent.stacked_widget.setCurrentIndex(0))

        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.back_btn)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

    def on_restart_enabled_changed(self):
        """处理自动重启功能启用/禁用状态变化"""

        self.restart_time_input.setEnabled(self.restart_enabled_checkbox.isChecked())

    def get_current_config(self):
        """获取当前配置的JSON数据"""

        config = {
            "game": {
                "human_like_drag_duration_range": [
                    float(self.min_drag_input.text()),
                    float(self.max_drag_input.text()),
                ]
            },
            "auto_restart": {
                "enabled": self.restart_enabled_checkbox.isChecked(),
                "output_timeout": int(self.restart_time_input.text()) * 60,
                "match_timeout": 900,
            },
            "run_settings": {
                "max_run_duration": int(self.run_duration_input.text()) * 60,
                "max_battle_count": int(self.battle_count_input.text()),
                "force_close": True,
            },
        }
        return config

    def refresh_card_priority(self):
        """刷新卡片优先级显示"""

        return

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

    def show_run_help(self):
        """显示运行设置说明"""

        help_text = """
运行设置说明：

【自动重启设置】
• 启用自动重启功能：当游戏长时间无操作时，自动重启游戏
• 无操作自动重启时间：设置无操作后自动重启游戏的时间间隔
• 建议设置：3-10分钟之间

【运行终止条件】
• 运行时长：设置脚本运行的最大时间（分钟）
• 对战次数阈值：设置脚本运行的最大对战次数
• 终止逻辑：当达到任一条件时，脚本停止运行
• 优先级：两个条件同时设置时，先达到哪个就触发哪个
• 特殊值：设置为0表示不限制

【关闭模式】
• 普通关闭模式：脚本将完成当前正在进行的对战后，再执行关闭操作
• 强制关闭模式：勾选后将忽略当前对战状态，直接强制关闭模拟器

【注意事项】
• 运行时长和对战次数阈值设置为0时，表示不限制
• 自动重启功能和运行终止条件可以同时使用
"""
        msg = QMessageBox()
        msg.setWindowTitle("运行设置说明")
        msg.setText(help_text)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()

    def load_config(self):
        """加载配置文件"""
        config_path = get_config_path()
        cfg, _, _ = ConfigRepository(config_path).load_existing(allow_default_on_error=True)
        return cfg if isinstance(cfg, dict) else {}

    def load_card_priority_settings(self, scroll_content):
        """加载卡片优先级设置"""

        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.card_widgets = []

        card_dir = os.path.join(get_exe_dir(), "shadowverse_cards_cost")
        if not os.path.exists(card_dir):
            QMessageBox.warning(self, "警告", "未找到'shadowverse_cards_cost'文件夹，请先选择卡组！")
            return

        card_files = []
        for file in os.listdir(card_dir):
            if file.lower().endswith((".png", ".jpg", ".jpeg")):
                card_files.append(file)

        if not card_files:
            no_card_label = QLabel("没有找到卡片，请先在'卡组选择'页面选择卡片")
            no_card_label.setStyleSheet("color: #FF8888; font-size: 14px;")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.scroll_layout.addWidget(no_card_label)
            return

        for card_file in card_files:
            try:
                _, _, card_name = parse_card_filename(card_file)
            except Exception:
                card_name = card_file.split("_", 1)[-1].rsplit(".", 1)[0]
            
            card_row = QWidget()
            card_row.setStyleSheet(
                "background-color: rgba(60, 60, 90, 150); border-radius: 10px;"
            )
            row_layout = QHBoxLayout(card_row)
            row_layout.setContentsMargins(10, 5, 10, 5)

            card_label = QLabel()
            card_path = os.path.join(get_exe_dir(), "shadowverse_cards_cost", card_file)
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(80, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(card_label)

            name_label = QLabel(card_name)
            name_label.setStyleSheet("color: #FFFFFF; font-weight: bold; min-width: 120px;")
            name_label.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(name_label)

            row_layout.addWidget(QLabel("出牌优先级:"))
            play_priority_input = QLineEdit()
            play_priority_input.setStyleSheet(
                "background-color: rgba(80, 80, 120, 180); color: white;"
            )
            play_priority_input.setMaximumWidth(50)

            high_priority = self.config_data.get("high_priority_cards", {}).get(card_name, {})
            if high_priority:
                play_priority_input.setText(str(high_priority.get("priority", "")))
            else:
                play_priority_input.setText("")
            row_layout.addWidget(play_priority_input)

            row_layout.addWidget(QLabel("进化优先级:"))
            evolve_priority_input = QLineEdit()
            evolve_priority_input.setStyleSheet(
                "background-color: rgba(80, 80, 120, 180); color: white;"
            )
            evolve_priority_input.setMaximumWidth(50)

            evolve_priority = self.config_data.get("evolve_priority_cards", {}).get(card_name, {})
            if evolve_priority:
                evolve_priority_input.setText(str(evolve_priority.get("priority", "")))
            else:
                evolve_priority_input.setText("")
            row_layout.addWidget(evolve_priority_input)

            self.card_widgets.append(
                {
                    "card_name": card_name,
                    "play_priority": play_priority_input,
                    "evolve_priority": evolve_priority_input,
                }
            )

            self.scroll_layout.addWidget(card_row)

        self.scroll_layout.addStretch()

    def save_config(self):
        """保存配置到文件"""

        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
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
                if restart_time < 1 or restart_time > 60:
                    raise ValueError("自动重启时间必须在1-60分钟之间")
                self.config_data["auto_restart"]["output_timeout"] = restart_time * 60

            if "match_timeout" not in self.config_data["auto_restart"]:
                self.config_data["auto_restart"]["match_timeout"] = 900
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"自动重启设置错误: {str(e)}")
            return

        try:
            if "run_settings" not in self.config_data:
                self.config_data["run_settings"] = {}

            run_duration = int(self.run_duration_input.text())
            battle_count = int(self.battle_count_input.text())

            if run_duration < 0:
                raise ValueError("运行时长不能为负数")
            if battle_count < 0:
                raise ValueError("对战次数不能为负数")

            self.config_data["run_settings"]["max_run_duration"] = run_duration * 60
            self.config_data["run_settings"]["max_battle_count"] = battle_count
            self.config_data["run_settings"]["force_close"] = True
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"运行设置错误: {str(e)}")
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
            self.parent.log_output.append("[配置] 参数设置已更新")
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
        self.output_timeout = auto_restart_config.get("output_timeout", 300) // 60
        self.restart_enabled_checkbox.setChecked(self.auto_restart_enabled)
        self.restart_time_input.setText(str(self.output_timeout))
        self.restart_time_input.setEnabled(self.auto_restart_enabled)

        run_settings_config = self.config_data.get("run_settings", {})
        max_run_duration = run_settings_config.get("max_run_duration", 0) // 60
        max_battle_count = run_settings_config.get("max_battle_count", 0)
        force_close = run_settings_config.get("force_close", False)
        self.run_duration_input.setText(str(max_run_duration))
        self.battle_count_input.setText(str(max_battle_count))

        current_strategy = self.config_data.get("game", {}).get(
            "card_replacement_strategy", "3费档次"
        )
        index = self.strategy_combo.findText(current_strategy)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        return

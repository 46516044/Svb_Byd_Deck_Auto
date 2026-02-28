#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Card priority and mode options page."""

from __future__ import annotations

import json
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.config.paths import get_config_path
from src.config.config_repository import ConfigRepository
from src.config.strategy_effects import (
    get_card_effect_steps,
    parse_select_option,
    parse_target_type,
)
from src.ui.common import get_exe_dir
from src.utils.card_filename import parse_card_filename, make_enhance_key


SPECIAL_TARGET_OPTIONS = [
    ("空选项", ""),
    ("打脸", "enemy_player"),
    ("双破坏", "double_enemy"),
    ("护盾/最高血", "shield_or_highest_hp"),
    ("敌随从HP<=5", "enemy_followers_hp_less_than_6"),
    ("护盾/最高血(不消耗)", "shield_or_highest_hp_no_enemy_retrun_point"),
    ("扫我方随从选项", "scan_our_follower_to_choose"),
]


class CardPriorityPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.config_data = self.load_config()
        self.card_widgets = []
        # Enhance rows share evolve priority with the base card row.
        self._base_evolve_priority_inputs = {}
        self._enhance_evolve_priority_views = {}
        self.init_ui()

    def _sync_enhance_evolve_priority_views(self, base_name: str, text: str) -> None:
        views = self._enhance_evolve_priority_views.get(str(base_name), [])
        for v in list(views):
            try:
                v.setText(text)
            except Exception:
                pass

    def init_ui(self):
        self.setObjectName("CardPriorityPage")
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        title_label = QLabel("卡牌设置")
        title_label.setStyleSheet("font-size: 20px; color: #88AAFF; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 说明文字和帮助按钮
        desc_layout = QHBoxLayout()
        desc_label = QLabel(
            "为卡组中的卡片设置优先级和模式选项。数字越小优先级越高，优先级上限是999（默认所有卡牌999）。出牌优先级支持进化前/进化后两个阶段。模式选项默认是空选项（不执行任何特殊操作）。"
        )
        desc_label.setStyleSheet("font-size: 12px; color: #AACCFF;")
        desc_layout.addWidget(desc_label)
        desc_layout.addStretch()
        self.help_btn = QPushButton("帮助")
        self.help_btn.clicked.connect(self.show_card_settings_help)
        desc_layout.addWidget(self.help_btn)
        main_layout.addLayout(desc_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_content.setObjectName("ScrollContent")
        main_layout.addWidget(self.scroll_area)

        # 设置滚动区域样式与主窗口一致
        self.scroll_area.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QWidget#ScrollContent {
                background-color: transparent;
            }
        """
        )
        self.scroll_content.setObjectName("ScrollContent")

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

        self.load_card_priority_settings()

    def show_card_settings_help(self):
        """显示卡牌设置帮助"""
        help_text = """
卡牌设置详细说明

一、优先级设置

1. 出牌优先级（进化前/进化后）
   作用：控制出牌顺序，会根据进化是否解锁切换不同阶段的优先级
   数值含义：数字越小优先级越高
   默认值：999（最低优先级）
   示例：若“进化前=1、进化后=5”，则前期更倾向优先打出；进化解锁后优先级会降低

2. 进化优先级
   作用：控制进化/超进化时的选择顺序
   数值含义：数字越小优先级越高
   默认值：999（最低优先级）
   示例：进化时会优先选择进化优先级更高（数字更小）的随从

二、模式选项设置

1. 模式选项
   作用：为双选择的模式卡牌选择对应的选项
   空选项：不会把这张卡认作模式卡，将以普通卡牌处理

2. 进化选项
   作用：为双选择的模式卡牌选择进化时对于的选项
   空选项：不会把这张卡认作进化时模式卡，将以普通卡牌处理
   

建议及后续更新：
   1. 模式选项和进化选项的设置是独立的，互不影响
   2. 为了避免错误操作，建议先设置好优先级，再设置模式选项和进化选项
   3. 后续如果会有空，会添加三模式或四模式卡牌的选项设置（不保证一定有）
"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("卡牌设置帮助")
        msg_box.setText(help_text)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.addButton(QMessageBox.Ok)

        msg_box.setStyleSheet(
            """
            QMessageBox {
                background-color: white;
            }
            QMessageBox QLabel {
                color: black;
                font-size: 12px;
            }
            QPushButton {
                background-color: #4A4A7F;
                color: white;
                border-radius: 5px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #5A5A8F;
            }
        """
        )

        msg_box.exec_()

    def load_config(self):
        config_path = get_config_path()
        cfg, _, _ = ConfigRepository(config_path).load_existing(allow_default_on_error=True)
        return cfg if isinstance(cfg, dict) else {}

    def load_card_priority_settings(self):
        # 清空现有内容
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.card_widgets = []
        self._base_evolve_priority_inputs = {}
        self._enhance_evolve_priority_views = {}

        card_dir = os.path.join(get_exe_dir(), "shadowverse_cards_cost")
        if not os.path.exists(card_dir):
            no_card_label = QLabel("未找到卡组卡片，请先在'卡组选择'页面选择卡片")
            no_card_label.setStyleSheet("color: #FF8888; font-size: 14px;")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.scroll_layout.addWidget(no_card_label)
            return

        card_files = [
            f
            for f in os.listdir(card_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ]
        if not card_files:
            no_card_label = QLabel("没有找到卡片，请先在'卡组选择'页面选择卡片")
            no_card_label.setStyleSheet("color: #FF8888; font-size: 14px;")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.scroll_layout.addWidget(no_card_label)
            return

        # Build display entries (base + enhance tiers) from filenames.
        entries = []
        for card_file in card_files:
            try:
                base_cost, enhance_costs, base_name = parse_card_filename(card_file)
            except Exception:
                base_cost, enhance_costs, base_name = 0, [], card_file.split("_", 1)[-1].rsplit(".", 1)[0]

            base_name = str(base_name or "").strip()
            if not base_name:
                continue
            enhance_costs = list(enhance_costs or [])

            entries.append(
                {
                    "file": card_file,
                    "base_name": base_name,
                    "config_key": base_name,
                    "base_cost": int(base_cost or 0),
                    "variant_cost": int(base_cost or 0),
                    "is_enhance": False,
                    "enhance_costs": enhance_costs,
                }
            )
            for c in enhance_costs:
                entries.append(
                    {
                        "file": card_file,
                        "base_name": base_name,
                        "config_key": make_enhance_key(base_name, c),
                        "base_cost": int(base_cost or 0),
                        "variant_cost": int(c),
                        "is_enhance": True,
                        "enhance_costs": enhance_costs,
                    }
                )

        entries.sort(
            key=lambda e: (
                int(e.get("base_cost", 0)),
                str(e.get("base_name", "")),
                1 if bool(e.get("is_enhance")) else 0,
                int(e.get("variant_cost", 0)),
            )
        )

        for entry in entries:
            card_file = entry["file"]
            base_name = entry["base_name"]
            config_key = entry["config_key"]
            is_enhance = bool(entry.get("is_enhance"))
            variant_cost = int(entry.get("variant_cost", 0))

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

            if is_enhance:
                display_name = f"{base_name} (爆能{variant_cost})"
            else:
                display_name = f"{base_name}"

            name_label = QLabel(display_name)
            name_label.setStyleSheet("color: #FFFFFF; font-weight: bold; min-width: 140px;")
            name_label.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(name_label)

            # 出牌优先级（进化前/进化后） - key is base or enhance-variant.
            high_priority = self.config_data.get("high_priority_cards", {}).get(config_key, {})

            row_layout.addWidget(QLabel("出牌(进化前):"))
            play_priority_pre_input = QLineEdit()
            play_priority_pre_input.setStyleSheet(
                "background-color: rgba(80, 80, 120, 180); color: white;"
            )
            play_priority_pre_input.setMaximumWidth(50)
            if isinstance(high_priority, dict):
                pre_priority = high_priority.get(
                    "priority_pre_evolution", high_priority.get("priority", "")
                )
                play_priority_pre_input.setText(str(pre_priority) if pre_priority != "" else "")
            row_layout.addWidget(play_priority_pre_input)

            row_layout.addWidget(QLabel("出牌(进化后):"))
            play_priority_post_input = QLineEdit()
            play_priority_post_input.setStyleSheet(
                "background-color: rgba(80, 80, 120, 180); color: white;"
            )
            play_priority_post_input.setMaximumWidth(50)
            if isinstance(high_priority, dict):
                post_priority = high_priority.get(
                    "priority_post_evolution", high_priority.get("priority", "")
                )
                play_priority_post_input.setText(
                    str(post_priority) if post_priority != "" else ""
                )
            row_layout.addWidget(play_priority_post_input)

            force_keep_checkbox = None
            evolve_priority_input = None
            evolve_mode_combo = None

            if not is_enhance:
                # 强制留牌（仅基础卡）
                row_layout.addWidget(QLabel("必留:"))
                force_keep_checkbox = QCheckBox()
                force_keep_checkbox.setStyleSheet(
                    "QCheckBox::indicator { width: 18px; height: 18px; }"
                )
                base_cfg = self.config_data.get("high_priority_cards", {}).get(base_name, {})
                if isinstance(base_cfg, dict) and base_cfg.get("force_keep") is True:
                    force_keep_checkbox.setChecked(True)
                row_layout.addWidget(force_keep_checkbox)

                # 进化优先级（仅基础卡）
                row_layout.addWidget(QLabel("进化优先级:"))
                evolve_priority_input = QLineEdit()
                evolve_priority_input.setStyleSheet(
                    "background-color: rgba(80, 80, 120, 180); color: white;"
                )
                evolve_priority_input.setMaximumWidth(50)
                evolve_priority = self.config_data.get("evolve_priority_cards", {}).get(
                    base_name, {}
                )
                if isinstance(evolve_priority, dict):
                    evolve_priority_input.setText(str(evolve_priority.get("priority", "")))
                row_layout.addWidget(evolve_priority_input)

                # Keep enhance rows in sync with this base evolve priority input.
                self._base_evolve_priority_inputs[base_name] = evolve_priority_input
                evolve_priority_input.textChanged.connect(
                    lambda text, n=base_name: self._sync_enhance_evolve_priority_views(n, text)
                )

            else:
                # 爆能档位不支持独立进化优先级（进化按随从名判定）。这里显示共用值，避免误解。
                row_layout.addWidget(QLabel("进化优先级(共用):"))
                evolve_priority_view = QLineEdit()
                evolve_priority_view.setStyleSheet(
                    "background-color: rgba(80, 80, 120, 120); color: white;"
                )
                evolve_priority_view.setMaximumWidth(50)
                evolve_priority_view.setReadOnly(True)
                evolve_priority_view.setToolTip("进化优先级按随从名共用，请在基础卡行设置")
                evolve_priority = self.config_data.get("evolve_priority_cards", {}).get(
                    base_name, {}
                )
                if isinstance(evolve_priority, dict):
                    evolve_priority_view.setText(str(evolve_priority.get("priority", "")))
                row_layout.addWidget(evolve_priority_view)

                self._enhance_evolve_priority_views.setdefault(base_name, []).append(
                    evolve_priority_view
                )
                try:
                    base_input = self._base_evolve_priority_inputs.get(base_name)
                    if base_input is not None:
                        evolve_priority_view.setText(base_input.text())
                except Exception:
                    pass

            # 模式选项（on_play）
            row_layout.addWidget(QLabel("模式选项:"))
            mode_combo = QComboBox()
            mode_combo.addItems(["空选项", "选项1", "选项2"])
            mode_combo.setStyleSheet(
                "background-color: rgba(80, 80, 120, 180); color: white;"
            )
            mode_combo.setMaximumWidth(80)

            steps_play = get_card_effect_steps(
                self.config_data, card_name=config_key, trigger="on_play"
            )
            eff_opt = parse_select_option(steps_play)
            if eff_opt == 1:
                mode_option = "选项1"
            elif eff_opt == 2:
                mode_option = "选项2"
            else:
                mode_option = self.config_data.get("card_mode_options", {}).get(
                    config_key, "空选项"
                )
            index = mode_combo.findText(mode_option)
            if index >= 0:
                mode_combo.setCurrentIndex(index)
            row_layout.addWidget(mode_combo)

            # 进化模式选项（仅基础卡）
            if not is_enhance:
                row_layout.addWidget(QLabel("进化选项:"))
                evolve_mode_combo = QComboBox()
                evolve_mode_combo.addItems(["空选项", "选项1 (进化)", "选项2 (进化)"])
                evolve_mode_combo.setStyleSheet(
                    "background-color: rgba(80, 80, 120, 180); color: white;"
                )
                evolve_mode_combo.setMaximumWidth(100)

                steps_evo = get_card_effect_steps(
                    self.config_data, card_name=base_name, trigger="on_evolve"
                )
                eff_evo_opt = parse_select_option(steps_evo)
                if eff_evo_opt == 1:
                    evolve_mode_option = "选项1"
                elif eff_evo_opt == 2:
                    evolve_mode_option = "选项2"
                else:
                    evolve_mode_option = self.config_data.get(
                        "card_evolve_mode_options", {}
                    ).get(base_name, "空选项")

                if evolve_mode_option == "选项1":
                    display_option = "选项1 (进化)"
                elif evolve_mode_option == "选项2":
                    display_option = "选项2 (进化)"
                else:
                    display_option = "空选项"
                index = evolve_mode_combo.findText(display_option)
                if index >= 0:
                    evolve_mode_combo.setCurrentIndex(index)
                row_layout.addWidget(evolve_mode_combo)

            # 特殊目标（on_play.target_type）
            row_layout.addWidget(QLabel("特殊目标:"))
            special_combo = QComboBox()
            for text, value in SPECIAL_TARGET_OPTIONS:
                special_combo.addItem(text, value)
            special_combo.setStyleSheet(
                "background-color: rgba(80, 80, 120, 180); color: white;"
            )
            special_combo.setMaximumWidth(120)

            eff_target = parse_target_type(steps_play)
            eff_target = eff_target or ""
            idx = special_combo.findData(eff_target)
            if idx >= 0:
                special_combo.setCurrentIndex(idx)
            row_layout.addWidget(special_combo)

            self.card_widgets.append(
                {
                    "card_name": base_name,
                    "config_key": config_key,
                    "is_enhance": is_enhance,
                    "play_priority_pre": play_priority_pre_input,
                    "play_priority_post": play_priority_post_input,
                    "force_keep": force_keep_checkbox,
                    "evolve_priority": evolve_priority_input,
                    "evolve_priority_view": evolve_priority_view if is_enhance else None,
                    "mode_option": mode_combo,
                    "evolve_mode_option": evolve_mode_combo,
                    "special_target": special_combo,
                }
            )

            self.scroll_layout.addWidget(card_row)

        self.scroll_layout.addStretch()

    def refresh_card_priority(self):
        # 重新加载配置文件
        self.config_data = self.load_config()
        # 重新加载卡牌优先级设置
        self.load_card_priority_settings()

    def get_current_config(self):
        # 仅返回通用参数（卡牌优先级已拆分至 CardPriorityPage，完整配置可从磁盘读取）
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

    def save_config(self):
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(
                    self,
                    "运行中",
                    "脚本运行中，禁止修改卡牌设置/配置。请先停止脚本后再保存。",
                )
                return
        except Exception:
            pass

        # 仅保存卡牌优先级部分，合并磁盘上的其余配置
        high_priority_cards = {}
        evolve_priority_cards = {}
        card_mode_options = {}
        card_evolve_mode_options = {}
        # Unified effects schema
        effects_updates = {}
        for card in self.card_widgets:
            base_name = card.get("card_name", "")
            config_key = card.get("config_key") or base_name
            is_enhance = bool(card.get("is_enhance"))

            name_for_msg = str(config_key or base_name)
            if is_enhance:
                try:
                    _b, _c = str(config_key).rsplit("@", 1)
                    if str(_b) == str(base_name):
                        name_for_msg = f"{base_name}(爆能{_c})"
                except Exception:
                    name_for_msg = str(config_key or base_name)

            play_pre_text = card["play_priority_pre"].text().strip()
            play_post_text = card["play_priority_post"].text().strip()
            if play_pre_text or play_post_text:
                pre_val = None
                post_val = None
                if play_pre_text:
                    try:
                        pre_val = int(play_pre_text)
                        if pre_val < 0 or pre_val > 999:
                            raise ValueError("优先级必须在0-999之间")
                    except Exception as e:
                        QMessageBox.warning(
                            self,
                            "输入错误",
                            f"卡片 '{name_for_msg}' 的出牌优先级(进化前)设置错误: {str(e)}",
                        )
                        return
                if play_post_text:
                    try:
                        post_val = int(play_post_text)
                        if post_val < 0 or post_val > 999:
                            raise ValueError("优先级必须在0-999之间")
                    except Exception as e:
                        QMessageBox.warning(
                            self,
                            "输入错误",
                            f"卡片 '{name_for_msg}' 的出牌优先级(进化后)设置错误: {str(e)}",
                        )
                        return

                # 只填了一个阶段时，默认另一阶段同值，避免出现999导致策略异常
                if pre_val is None and post_val is not None:
                    pre_val = post_val
                if post_val is None and pre_val is not None:
                    post_val = pre_val

                high_priority_cards[config_key] = {
                    "priority_pre_evolution": pre_val,
                    "priority_post_evolution": post_val,
                }

            # 强制留牌（仅基础卡）
            try:
                force_keep_widget = card.get("force_keep")
                force_keep_checked = bool(
                    force_keep_widget is not None and force_keep_widget.isChecked()
                )
            except Exception:
                force_keep_checked = False

            if force_keep_checked:
                base_cfg = high_priority_cards.get(base_name)
                if not isinstance(base_cfg, dict):
                    base_cfg = {}
                    high_priority_cards[base_name] = base_cfg
                base_cfg["force_keep"] = True

            # 进化优先级（仅基础卡；爆能档位不单独配置）
            evolve_widget = card.get("evolve_priority")
            if evolve_widget is not None:
                evolve_priority_text = evolve_widget.text().strip()
                if evolve_priority_text:
                    try:
                        priority = int(evolve_priority_text)
                        if priority < 0 or priority > 999:
                            raise ValueError("优先级必须在0-999之间")
                        evolve_priority_cards[base_name] = {"priority": priority}
                    except Exception as e:
                        QMessageBox.warning(
                            self,
                            "输入错误",
                            f"卡片 '{base_name}' 的进化优先级设置错误: {str(e)}",
                        )
                        return

            # 保存模式选项
            mode_option = card["mode_option"].currentText()
            if mode_option != "空选项":
                card_mode_options[config_key] = mode_option

            # effects.on_play.select_option
            if mode_option == "选项1":
                effects_updates.setdefault(config_key, {}).setdefault("on_play", []).insert(
                    0, {"select_option": 1}
                )
            elif mode_option == "选项2":
                effects_updates.setdefault(config_key, {}).setdefault("on_play", []).insert(
                    0, {"select_option": 2}
                )

            # 保存进化模式选项（仅基础卡）
            evolve_mode_widget = card.get("evolve_mode_option")
            if evolve_mode_widget is not None:
                evolve_mode_option = evolve_mode_widget.currentText()
                if evolve_mode_option == "选项1 (进化)":
                    save_option = "选项1"
                elif evolve_mode_option == "选项2 (进化)":
                    save_option = "选项2"
                else:
                    save_option = "空选项"
                if save_option != "空选项":
                    card_evolve_mode_options[base_name] = save_option

                # effects.on_evolve/on_super_evolve.select_option
                if save_option == "选项1":
                    effects_updates.setdefault(base_name, {}).setdefault(
                        "on_evolve", []
                    ).insert(0, {"select_option": 1})
                    effects_updates.setdefault(base_name, {}).setdefault(
                        "on_super_evolve", []
                    ).insert(0, {"select_option": 1})
                elif save_option == "选项2":
                    effects_updates.setdefault(base_name, {}).setdefault(
                        "on_evolve", []
                    ).insert(0, {"select_option": 2})
                    effects_updates.setdefault(base_name, {}).setdefault(
                        "on_super_evolve", []
                    ).insert(0, {"select_option": 2})

            # effects.on_play.target_type (only update when explicitly set)
            try:
                target_type = card["special_target"].currentData() or ""
            except Exception:
                target_type = ""
            if isinstance(target_type, str) and target_type:
                effects_updates.setdefault(config_key, {}).setdefault("on_play", []).append(
                    {"target_type": target_type}
                )

        config_path = get_config_path()
        repo = ConfigRepository(config_path)
        existing, parse_ok, parse_err = repo.load_existing(allow_default_on_error=False)
        if existing is None:
            QMessageBox.warning(
                self,
                "保存失败",
                f"config.json解析失败，已拒绝覆盖写入: {str(parse_err or '')}",
            )
            return

        if high_priority_cards:
            existing["high_priority_cards"] = high_priority_cards
        elif "high_priority_cards" in existing:
            del existing["high_priority_cards"]

        if evolve_priority_cards:
            existing["evolve_priority_cards"] = evolve_priority_cards
        elif "evolve_priority_cards" in existing:
            del existing["evolve_priority_cards"]

        if card_mode_options:
            existing["card_mode_options"] = card_mode_options
        elif "card_mode_options" in existing:
            del existing["card_mode_options"]

        if card_evolve_mode_options:
            existing["card_evolve_mode_options"] = card_evolve_mode_options
        elif "card_evolve_mode_options" in existing:
            del existing["card_evolve_mode_options"]

        # Merge effects updates into strategy.effects without clobbering unknown future keys.
        if effects_updates:
            strategy = existing.get("strategy")
            if not isinstance(strategy, dict):
                strategy = {}
                existing["strategy"] = strategy
            effects = strategy.get("effects")
            if not isinstance(effects, dict):
                effects = {}
                strategy["effects"] = effects

            for card_name, upd in effects_updates.items():
                if not isinstance(upd, dict):
                    continue
                card_eff = effects.get(card_name)
                if not isinstance(card_eff, dict):
                    card_eff = {}
                    effects[card_name] = card_eff

                for trigger, upd_steps in upd.items():
                    if not isinstance(upd_steps, list):
                        continue
                    steps = card_eff.get(trigger)
                    if not isinstance(steps, list):
                        steps = []

                    # Replace select_option steps for this trigger (UI owns them)
                    steps = [
                        s
                        for s in steps
                        if not (isinstance(s, dict) and "select_option" in s)
                    ]
                    for s in upd_steps:
                        if isinstance(s, dict) and "select_option" in s:
                            steps.insert(0, s)

                    # Only update target_type when explicitly provided
                    if any(isinstance(s, dict) and "target_type" in s for s in upd_steps):
                        steps = [
                            s
                            for s in steps
                            if not (isinstance(s, dict) and "target_type" in s)
                        ]
                        for s in upd_steps:
                            if isinstance(s, dict) and "target_type" in s:
                                steps.append(s)

                    # Dedup exact dict steps while preserving order
                    deduped = []
                    seen = set()
                    for s in steps:
                        if not isinstance(s, dict):
                            continue
                        key = json.dumps(s, ensure_ascii=False, sort_keys=True)
                        if key in seen:
                            continue
                        seen.add(key)
                        deduped.append(s)

                    if deduped:
                        card_eff[trigger] = deduped
                    elif trigger in card_eff:
                        del card_eff[trigger]

        try:
            res = repo.replace_with_snapshot(existing, indent=4, ensure_ascii=False)
            if not res.ok:
                raise RuntimeError(res.error or "config write failed")
            QMessageBox.information(self, "成功", "卡牌设置已保存！")
            if hasattr(self.parent, "log_output"):
                self.parent.log_output.append("[配置] 卡牌设置已更新")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存卡牌设置失败: {str(e)}")

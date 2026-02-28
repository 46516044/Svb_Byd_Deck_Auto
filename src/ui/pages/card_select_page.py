#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Card selection page."""

from __future__ import annotations

import json
import os
import shutil
import time

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from src.config.paths import get_config_path
from src.config.config_repository import ConfigRepository
from src.ui.common import get_exe_dir
from src.ui.deck_io import save_deck_snapshot
from src.utils.card_filename import parse_card_filename


class CardSelectPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.deck_store = getattr(parent, "deck_store", None)
        self.current_page = 0
        self.selected_cards = []
        self.cards_per_row = 4
        self.card_size = QSize(100, 140)  # 减小卡片尺寸以显示更多图片
        self.cost_filters = {}  # 存储费用筛选按钮
        self.all_cards = []  # 所有卡片
        self.filtered_cards = []  # 筛选后的卡片
        self.card_categories = []  # 卡片分类
        self.current_category = None  # 当前选择的分类
        if self.deck_store is not None:
            try:
                self.deck_store.decks_changed.connect(self._on_decks_changed)
            except Exception:
                self.deck_store = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        # 标题
        title_label = QLabel("卡组选择")
        title_label.setStyleSheet("font-size: 20px; color: #88AAFF; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 加载已保存卡组下拉框
        deck_layout = QHBoxLayout()
        deck_layout.addWidget(QLabel("已保存卡组:"))
        self.saved_decks_combo = QComboBox()
        self.saved_decks_combo.setStyleSheet(
            """
            QComboBox {
                background-color: rgba(80, 80, 120, 180);
                color: white;
                border: 1px solid #5A5A8F;
                border-radius: 5px;
                padding: 5px;
                min-width: 150px;
            }
            QComboBox:hover {
                background-color: rgba(90, 90, 140, 180);
            }
        """
        )
        self.saved_decks_combo.addItem("选择卡组", None)
        self.saved_decks_combo.currentIndexChanged.connect(self.load_saved_deck)
        deck_layout.addWidget(self.saved_decks_combo)

        self.refresh_saved_decks()  # 加载已保存的卡组列表
        main_layout.addLayout(deck_layout)

        # 搜索框和分类选择
        search_layout = QHBoxLayout()

        # 分类选择下拉框
        self.category_combo = QComboBox()
        self.category_combo.addItem("所有分类", None)
        self.category_combo.setStyleSheet(
            """
            QComboBox {
                background-color: rgba(80, 80, 120, 180);
                color: white;
                border: 1px solid #5A5A8F;
                border-radius: 5px;
                padding: 5px;
                min-width: 120px;
            }
            QComboBox:hover {
                background-color: rgba(90, 90, 140, 180);
            }
        """
        )
        self.category_combo.currentIndexChanged.connect(self.on_category_changed)
        search_layout.addWidget(QLabel("分类:"))
        search_layout.addWidget(self.category_combo)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索卡牌...")
        self.search_input.setStyleSheet(
            """
            QLineEdit {
                background-color: rgba(80, 80, 120, 180);
                color: white;
                border: 1px solid #5A5A8F;
                border-radius: 5px;
                padding: 5px;
            }
        """
        )
        self.search_input.textChanged.connect(self.on_search_text_changed)
        search_layout.addWidget(QLabel("搜索:"))
        search_layout.addWidget(self.search_input)

        main_layout.addLayout(search_layout)

        # 费用筛选栏
        self.init_cost_filter(main_layout)

        # 说明标签
        desc_label = QLabel("从以下卡牌中选择您的卡组，点击保存应用选择")
        desc_label.setStyleSheet("font-size: 14px; color: #AACCFF;")
        desc_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(desc_label)

        # 卡片显示区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

        # 设置滚动区域样式
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
        main_layout.addWidget(self.scroll_area)

        # 翻页控制
        page_control_layout = QHBoxLayout()
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.page_label = QLabel("第1页")
        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self.next_page)

        page_control_layout.addStretch()
        page_control_layout.addWidget(self.prev_btn)
        page_control_layout.addWidget(self.page_label)
        page_control_layout.addWidget(self.next_btn)
        page_control_layout.addStretch()
        main_layout.addLayout(page_control_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存卡组")
        self.save_btn.clicked.connect(self.save_selection)
        self.save_as_btn = QPushButton("另存为...")
        self.save_as_btn.clicked.connect(self.save_deck_as)
        self.back_btn = QPushButton("返回主界面")
        self.back_btn.clicked.connect(lambda: self.parent.stacked_widget.setCurrentIndex(0))

        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.save_as_btn)
        btn_layout.addWidget(self.back_btn)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

        # 加载卡片
        self.load_cards()

    def init_cost_filter(self, main_layout):
        """初始化费用筛选控件"""
        cost_filter_layout = QHBoxLayout()
        cost_filter_layout.addWidget(QLabel("费用筛选:"))

        # 添加0-10费选项
        for cost in range(0, 11):
            btn = QPushButton(f"{cost}费")
            btn.setCheckable(True)
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #4A4A7F;
                    color: white;
                    border: none;
                    padding: 5px 8px;
                    min-width: 40px;
                    border-radius: 4px;
                    margin: 2px;
                }
                QPushButton:checked {
                    background-color: #88AAFF;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #5A5A9F;
                }
            """
            )
            btn.clicked.connect(self.update_card_display)
            self.cost_filters[cost] = btn
            cost_filter_layout.addWidget(btn)

        # 添加"全部"按钮
        all_btn = QPushButton("全部")
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #88AAFF;
                color: white;
                font-weight: bold;
                padding: 5px 10px;
                border-radius: 4px;
                margin: 2px;
            }
        """
        )
        all_btn.clicked.connect(self.select_all_costs)
        cost_filter_layout.addWidget(all_btn)

        cost_filter_layout.addStretch()
        main_layout.addLayout(cost_filter_layout)

    def load_cards(self):
        """加载所有卡片和分类"""
        card_dir = os.path.join(get_exe_dir(), "quanka")
        self.all_cards = []
        self.card_categories = []

        if os.path.exists(card_dir):
            # 获取所有分类文件夹
            self.card_categories = [
                d
                for d in os.listdir(card_dir)
                if os.path.isdir(os.path.join(card_dir, d))
            ]

            # 更新分类下拉框
            self.category_combo.clear()
            self.category_combo.addItem("所有分类", None)

            for category in sorted(self.card_categories):
                self.category_combo.addItem(category, category)

            # 加载所有卡片
            for root, _, files in os.walk(card_dir):
                for file in files:
                    if file.lower().endswith((".png", ".jpg", ".jpeg")):
                        rel_path = os.path.relpath(os.path.join(root, file), card_dir)
                        self.all_cards.append(
                            {
                                "path": rel_path,
                                "file": file,
                                "category": os.path.basename(root)
                                if root != card_dir
                                else None,
                            }
                        )

        # 按费用和名称排序
        self.all_cards.sort(key=lambda x: (self.get_card_cost(x["file"]), x["file"].lower()))

        self.filtered_cards = self.all_cards
        self.display_page(0)

    def on_category_changed(self, index):
        """分类选择改变事件"""
        self.current_category = self.category_combo.itemData(index)
        self.update_card_display()

    def on_search_text_changed(self, text):
        """搜索文本改变事件"""
        self.update_card_display()

    def select_all_costs(self):
        """选择全部费用"""
        sender = self.sender()
        if sender.isChecked():
            for cost, btn in self.cost_filters.items():
                btn.setChecked(False)
            self.update_card_display()
            sender.setChecked(True)

    def update_card_display(self):
        """根据分类、搜索和费用筛选更新卡片显示"""
        selected_costs = [
            cost for cost, btn in self.cost_filters.items() if btn.isChecked()
        ]

        all_btn = (
            self.sender()
            if isinstance(self.sender(), QPushButton) and self.sender().text() == "全部"
            else None
        )
        if not all_btn:
            for btn in self.findChildren(QPushButton):
                if btn.text() == "全部":
                    btn.setChecked(False)
                    break

        search_text = self.search_input.text().strip().lower()

        self.filtered_cards = []
        for card in self.all_cards:
            if self.current_category and card["category"] != self.current_category:
                continue

            if selected_costs and self.get_card_cost(card["file"]) not in selected_costs:
                continue

            if search_text and search_text not in card["file"].lower():
                continue

            self.filtered_cards.append(card)

        self.current_page = 0
        self.display_page(self.current_page)

    def get_card_cost(self, card_file):
        """从文件名提取费用数字"""
        try:
            return int(card_file.split("_")[0])
        except Exception:
            return 0

    def resizeEvent(self, event):
        """窗口大小改变时调整布局"""
        super().resizeEvent(event)
        self.adjust_card_layout()

    def adjust_card_layout(self):
        """根据窗口大小调整卡片布局"""
        scroll_width = self.scroll_area.width() - 30
        self.cards_per_row = max(2, scroll_width // (self.card_size.width() + 20))
        self.display_page(self.current_page)

    def display_page(self, page):
        """显示指定页码的卡片"""
        self.current_page = page
        cards_per_page = self.cards_per_row * 3  # 每页3行

        self.total_pages = max(
            1, (len(self.filtered_cards) + cards_per_page - 1) // cards_per_page
        )
        self.page_label.setText(f"第{page+1}/{self.total_pages}页")
        self.prev_btn.setEnabled(page > 0)
        self.next_btn.setEnabled(page < self.total_pages - 1)

        for i in reversed(range(self.grid_layout.count())):
            if widget := self.grid_layout.itemAt(i).widget():
                widget.deleteLater()

        start_index = page * cards_per_page
        end_index = min(start_index + cards_per_page, len(self.filtered_cards))

        row, col = 0, 0
        for i in range(start_index, end_index):
            card_data = self.filtered_cards[i]
            card_path = os.path.join(get_exe_dir(), "quanka", card_data["path"])

            card_container = QWidget()
            card_container.setStyleSheet(
                """
                background-color: rgba(60, 60, 90, 150);
                border-radius: 10px;
            """
            )
            card_layout = QVBoxLayout(card_container)
            card_layout.setAlignment(Qt.AlignCenter)
            card_layout.setSpacing(5)
            card_layout.setContentsMargins(5, 5, 5, 5)

            card_label = QLabel()
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.card_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)
            card_label.mousePressEvent = (
                lambda event, f=card_data["file"]: self.toggle_card_selection_by_click(f)
            )

            try:
                _, _, base_name = parse_card_filename(card_data["file"])
                card_name = " ".join(str(base_name or "").split("_"))
            except Exception:
                card_name = " ".join(
                    card_data["file"].split("_", 1)[-1].rsplit(".", 1)[0].split("_")
                )
            name_label = QLabel(card_name)
            name_label.setStyleSheet(
                """
                QLabel {
                    color: #FFFFFF;
                    background-color: transparent;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 2px;
                    max-width: %dpx;
                }
            """
                % (self.card_size.width() - 10)
            )
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)

            checkbox = QCheckBox("选择")
            checkbox.setStyleSheet(
                """
                QCheckBox {
                    color: #FFFFFF;
                    background-color: rgba(80, 80, 120, 180);
                    border-radius: 5px;
                    padding: 2px 5px;
                    font-size: 12px;
                }
                QCheckBox::indicator {
                    width: 15px;
                    height: 15px;
                }
            """
            )
            checkbox.setChecked(card_data["file"] in self.selected_cards)
            checkbox.stateChanged.connect(
                lambda state, f=card_data["file"]: self.toggle_card_selection(f, state)
            )

            card_layout.addWidget(card_label)
            card_layout.addWidget(name_label)
            card_layout.addWidget(checkbox)
            self.grid_layout.addWidget(card_container, row, col)

            col += 1
            if col >= self.cards_per_row:
                col = 0
                row += 1

    def toggle_card_selection(self, card_file, state):
        """复选框选择卡片"""
        if state == Qt.Checked:
            if card_file not in self.selected_cards:
                if len(self.selected_cards) < 100:
                    self.selected_cards.append(card_file)
                else:
                    self.sender().setChecked(False)
                    QMessageBox.warning(self, "警告", "最多只能选择100张卡片！")
        else:
            if card_file in self.selected_cards:
                self.selected_cards.remove(card_file)

    def toggle_card_selection_by_click(self, card_file):
        """点击图片选择卡片"""
        if card_file in self.selected_cards:
            self.selected_cards.remove(card_file)
        else:
            if len(self.selected_cards) < 100:
                self.selected_cards.append(card_file)
            else:
                QMessageBox.warning(self, "警告", "最多只能选择100张卡片！")
        self.display_page(self.current_page)

    def prev_page(self):
        """上一页"""
        if self.current_page > 0:
            self.display_page(self.current_page - 1)

    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages - 1:
            self.display_page(self.current_page + 1)

    def save_selection(self):
        """保存选择的卡组"""
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(
                    self,
                    "运行中",
                    "脚本运行中，禁止修改当前卡组。请先停止脚本后再保存卡组选择。",
                )
                return
        except Exception:
            pass

        if not self.selected_cards:
            QMessageBox.warning(self, "警告", "请至少选择一张卡片！")
            return

        target_dir = os.path.join(get_exe_dir(), "shadowverse_cards_cost")
        os.makedirs(target_dir, exist_ok=True)

        for file in os.listdir(target_dir):
            file_path = os.path.join(target_dir, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"删除文件失败: {file_path} - {e}")

        success_count = 0
        for card_file in self.selected_cards:
            src = None
            for card in self.all_cards:
                if card["file"] == card_file:
                    src = os.path.join(get_exe_dir(), "quanka", card["path"])
                    break

            if src and os.path.exists(src):
                dst = os.path.join(target_dir, card_file)
                try:
                    shutil.copy2(src, dst)
                    success_count += 1
                except Exception as e:
                    print(f"复制文件失败: {src} -> {dst} - {e}")

        if success_count > 0:
            QMessageBox.information(self, "成功", f"已保存 {success_count} 张卡片到卡组！")
            self.parent.log_output.append(f"[卡组] 已保存 {success_count} 张卡片")

            if hasattr(self.parent, "card_priority_page"):
                self.parent.card_priority_page.refresh_card_priority()

            if hasattr(self.parent, "my_deck_page"):
                self.parent.my_deck_page.load_deck()

    def load_selected_deck(self):
        """加载选中的已保存卡组"""
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(
                    self,
                    "运行中",
                    "脚本运行中，禁止切换卡组/恢复配置。请先停止脚本后再加载卡组。",
                )
                return
        except Exception:
            pass

        deck_file = self.saved_decks_combo.itemData(self.saved_decks_combo.currentIndex())
        if not deck_file:
            QMessageBox.warning(self, "警告", "请选择要加载的卡组！")
            return

        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            deck_path = os.path.join(decks_dir, deck_file)

            with open(deck_path, "r", encoding="utf-8") as f:
                deck_data = json.load(f)

            card_dir = os.path.join(get_exe_dir(), "shadowverse_cards_cost")
            for file in os.listdir(card_dir):
                file_path = os.path.join(card_dir, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"删除文件失败: {file_path} - {e}")

            source_dir = os.path.join(get_exe_dir(), "quanka")
            success_count = 0
            for card_file in deck_data.get("cards", []):
                src = None
                for root, _, files in os.walk(source_dir):
                    if card_file in files:
                        src = os.path.join(root, card_file)
                        break

                if src and os.path.exists(src):
                    dst = os.path.join(card_dir, card_file)
                    try:
                        shutil.copy2(src, dst)
                        success_count += 1
                    except Exception as e:
                        print(f"复制文件失败: {src} -> {dst} - {e}")

            if success_count > 0:
                self.load_deck()

                if "config" in deck_data:
                    if isinstance(deck_data.get("config"), dict):
                        config_path = get_config_path()
                        res = ConfigRepository(config_path).replace_with_snapshot(
                            deck_data["config"], ensure_ascii=False, indent=2
                        )
                        if not res.ok:
                            raise RuntimeError(res.error or "config write failed")
                        self.parent.log_output.append(
                            f"[卡组] 已恢复卡组 '{deck_data.get('name')}' 的配置文件"
                        )

                QMessageBox.information(
                    self,
                    "成功",
                    f"已加载卡组 '{deck_data.get('name')}'，共 {success_count} 张卡片",
                )
                self.parent.log_output.append(f"[卡组] 已加载卡组 '{deck_data.get('name')}'")

                if hasattr(self.parent, "card_priority_page"):
                    self.parent.card_priority_page.refresh_card_priority()

                if hasattr(self.parent, "share_page"):
                    self.parent.share_page.refresh_preview()

        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载卡组失败: {str(e)}")
            self.parent.log_output.append(f"[卡组] 加载卡组失败: {str(e)}")

    def delete_selected_deck(self):
        """删除选中的已保存卡组"""
        deck_file = self.saved_decks_combo.itemData(self.saved_decks_combo.currentIndex())
        deck_name = self.saved_decks_combo.currentText()

        if not deck_file:
            QMessageBox.warning(self, "警告", "请选择要删除的卡组！")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f'确定要删除卡组 "{deck_name}" 吗？此操作不可撤销！',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                decks_dir = os.path.join(get_exe_dir(), "saved_decks")
                deck_path = os.path.join(decks_dir, deck_file)

                if os.path.exists(deck_path):
                    os.remove(deck_path)

                    QMessageBox.information(self, "成功", f"卡组 '{deck_name}' 已删除！")
                    self.parent.log_output.append(f"[卡组] 已删除卡组 '{deck_name}'")

                    if self.deck_store is not None:
                        self.deck_store.refresh()
                    else:
                        self.refresh_saved_decks()

            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除卡组失败: {str(e)}")
                self.parent.log_output.append(f"[卡组] 删除卡组失败: {str(e)}")

    def save_deck_as(self):
        """将当前选择的卡组另存为"""
        if not self.selected_cards:
            QMessageBox.warning(self, "警告", "请至少选择一张卡片！")
            return

        deck_name, ok = QInputDialog.getText(self, "保存卡组", "请输入卡组名称:")
        if not ok or not deck_name.strip():
            return

        self.save_named_deck(deck_name.strip())

    def save_named_deck(self, deck_name):
        """保存命名卡组"""
        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            save_deck_snapshot(
                deck_name=deck_name,
                cards=list(self.selected_cards or []),
                decks_dir=decks_dir,
                config_path=get_config_path(),
            )

            QMessageBox.information(self, "成功", f"卡组 '{deck_name}' 已保存！")
            self.parent.log_output.append(f"[卡组] 已保存卡组 '{deck_name}'")

            if self.deck_store is not None:
                self.deck_store.refresh()
            else:
                self.refresh_saved_decks()

        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存卡组失败: {str(e)}")
            self.parent.log_output.append(f"[卡组] 保存卡组失败: {str(e)}")

    def refresh_saved_decks(self, *, propagate: bool = True):
        """刷新已保存卡组列表"""
        decks = []
        if self.deck_store is not None:
            try:
                decks = list(self.deck_store.get_decks() or [])
            except Exception:
                decks = []
        else:
            # Fallback: scan directory directly.
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            if os.path.exists(decks_dir):
                for file in os.listdir(decks_dir):
                    if not file.endswith(".json"):
                        continue
                    deck_file = os.path.join(decks_dir, file)
                    try:
                        with open(deck_file, "r", encoding="utf-8") as f:
                            deck_data = json.load(f)
                        decks.append((deck_data.get("name", file[:-5]), file))
                    except Exception as e:
                        print(f"读取卡组文件失败: {deck_file} - {e}")

        self._populate_saved_decks(decks)

    def _on_decks_changed(self):
        try:
            self.refresh_saved_decks(propagate=False)
        except Exception:
            pass

    def _populate_saved_decks(self, decks):
        if not hasattr(self, "saved_decks_combo"):
            return

        current = None
        try:
            current = self.saved_decks_combo.itemData(self.saved_decks_combo.currentIndex())
        except Exception:
            current = None

        self.saved_decks_combo.blockSignals(True)
        try:
            self.saved_decks_combo.clear()
            self.saved_decks_combo.addItem("选择卡组", None)
            for display_name, filename in list(decks or []):
                self.saved_decks_combo.addItem(str(display_name), filename)

            # Restore selection if possible.
            if current:
                idx = self.saved_decks_combo.findData(current)
                if idx >= 0:
                    self.saved_decks_combo.setCurrentIndex(idx)
        finally:
            self.saved_decks_combo.blockSignals(False)

    def load_saved_deck(self, index):
        """加载选中的已保存卡组"""
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(
                    self,
                    "运行中",
                    "脚本运行中，禁止切换卡组/恢复配置。请先停止脚本后再加载卡组。",
                )
                try:
                    self.saved_decks_combo.blockSignals(True)
                    self.saved_decks_combo.setCurrentIndex(0)
                finally:
                    self.saved_decks_combo.blockSignals(False)
                return
        except Exception:
            pass

        deck_file = self.saved_decks_combo.itemData(index)
        if not deck_file:
            return

        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            deck_path = os.path.join(decks_dir, deck_file)

            with open(deck_path, "r", encoding="utf-8") as f:
                deck_data = json.load(f)

            self.selected_cards = []
            for card_file in deck_data.get("cards", []):
                self.selected_cards.append(card_file)

            self.display_page(self.current_page)

            if "config" in deck_data:
                if isinstance(deck_data.get("config"), dict):
                    config_path = get_config_path()
                    res = ConfigRepository(config_path).replace_with_snapshot(
                        deck_data["config"], ensure_ascii=False, indent=2
                    )
                    if not res.ok:
                        raise RuntimeError(res.error or "config write failed")
                    self.parent.log_output.append(
                        f"[卡组] 已恢复卡组 '{deck_data.get('name')}' 的配置文件"
                    )

            QMessageBox.information(self, "成功", f"已加载卡组 '{deck_data.get('name')}'")
            self.parent.log_output.append(f"[卡组] 已加载卡组 '{deck_data.get('name')}'")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载卡组失败: {str(e)}")
            self.parent.log_output.append(f"[卡组] 加载卡组失败: {str(e)}")

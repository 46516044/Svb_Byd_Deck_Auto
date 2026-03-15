#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""My deck page (view/manage current deck)."""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportIncompatibleMethodOverride=false

import json
import os
import shutil

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.config.paths import get_card_cost_dir, get_config_path
from src.config.config_repository import ConfigRepository
from src.ui.common import get_exe_dir
from src.ui.deck_io import (
    apply_strategy_config,
    build_card_variant_index,
    build_card_source_index,
    extract_strategy_config,
    filter_non_evo_cards,
    resolve_runtime_card_paths,
    save_deck_snapshot,
)
from src.utils.card_filename import normalize_card_base_name, parse_card_filename


class MyDeckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.deck_store = getattr(parent, "deck_store", None)
        self.card_size = QSize(100, 140)  # 标准卡片尺寸
        self.cards_per_row = 4
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
        title_label = QLabel("我的卡组")
        title_label.setStyleSheet("font-size: 20px; color: #88AAFF; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 卡组保存管理布局
        save_layout = QHBoxLayout()
        save_layout.addWidget(QLabel("卡组名称:"))
        self.save_deck_name = QLineEdit()
        self.save_deck_name.setPlaceholderText("输入卡组名称")
        self.save_deck_name.setStyleSheet(
            """
            QLineEdit {
                background-color: rgba(80, 80, 120, 180);
                color: white;
                border: 1px solid #5A5A8F;
                border-radius: 5px;
                padding: 5px;
                min-width: 150px;
            }
        """
        )
        save_layout.addWidget(self.save_deck_name)

        self.save_current_btn = QPushButton("保存")
        self.save_current_btn.clicked.connect(self.save_current_deck)
        save_layout.addWidget(self.save_current_btn)

        main_layout.addLayout(save_layout)

        # 已保存卡组加载布局
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
        deck_layout.addWidget(self.saved_decks_combo)

        self.load_deck_btn = QPushButton("加载")
        self.load_deck_btn.clicked.connect(self.load_selected_deck)
        deck_layout.addWidget(self.load_deck_btn)

        self.delete_deck_btn = QPushButton("删除")
        self.delete_deck_btn.clicked.connect(self.delete_selected_deck)
        deck_layout.addWidget(self.delete_deck_btn)

        main_layout.addLayout(deck_layout)

        # 说明
        desc_label = QLabel("当前卡组中的卡片，右键点击卡片可移除")
        desc_label.setStyleSheet("font-size: 14px; color: #AACCFF;")
        desc_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(desc_label)

        # 刷新已保存卡组列表
        self.refresh_saved_decks()

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

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.back_btn = QPushButton("返回主界面")
        self.back_btn.clicked.connect(lambda: self.parent.stacked_widget.setCurrentIndex(0))

        btn_layout.addStretch()
        btn_layout.addWidget(self.back_btn)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

        # 加载卡组
        self.load_deck()

    def save_current_deck(self):
        """保存当前卡组"""
        deck_name = self.save_deck_name.text().strip()
        if not deck_name:
            QMessageBox.warning(self, "警告", "请输入卡组名称！")
            return

        # 获取当前卡组中的卡片
        card_dir = get_card_cost_dir(ensure=True)
        if not os.path.exists(card_dir):
            QMessageBox.warning(self, "警告", "当前卡组为空！")
            return

        card_files = [
            f
            for f in os.listdir(card_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
        card_files = filter_non_evo_cards(card_files)
        if not card_files:
            QMessageBox.warning(self, "警告", "当前卡组为空！")
            return

        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            save_deck_snapshot(
                deck_name=deck_name,
                cards=card_files,
                decks_dir=decks_dir,
                config_path=get_config_path(),
            )

            QMessageBox.information(self, "成功", f"卡组 '{deck_name}' 已保存！")
            self.parent.log_output.append(f"[卡组] 已保存卡组 '{deck_name}'")

            # 清空输入框
            self.save_deck_name.clear()

            # 刷新已保存卡组列表
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

            if current:
                idx = self.saved_decks_combo.findData(current)
                if idx >= 0:
                    self.saved_decks_combo.setCurrentIndex(idx)
        finally:
            self.saved_decks_combo.blockSignals(False)

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

            # 清空当前卡组
            card_dir = get_card_cost_dir(ensure=True)
            for file in os.listdir(card_dir):
                file_path = os.path.join(card_dir, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"删除文件失败: {file_path} - {e}")

            # 复制卡片到当前卡组
            source_dir = os.path.join(get_exe_dir(), "quanka")
            exact_index, stem_index = build_card_source_index(source_dir)
            variant_index = build_card_variant_index(source_dir)
            success_count = 0
            loaded_base_count = 0
            for card_file in filter_non_evo_cards(list(deck_data.get("cards", []))):
                runtime_paths = resolve_runtime_card_paths(
                    source_dir,
                    card_file,
                    exact_index=exact_index,
                    stem_index=stem_index,
                    variant_index=variant_index,
                )
                if runtime_paths:
                    loaded_base_count += 1
                for src in runtime_paths:
                    if not os.path.exists(src):
                        continue
                    dst = os.path.join(card_dir, os.path.basename(src))
                    try:
                        shutil.copy2(src, dst)
                        success_count += 1
                    except Exception as e:
                        print(f"复制文件失败: {src} -> {dst} - {e}")

            if success_count > 0:
                # 重新加载卡组显示
                self.load_deck()

                # 如果卡组数据中包含策略配置，只应用“卡组相关策略”（不覆盖设备/ADB等机器相关配置）
                sc = deck_data.get("strategy_config")
                if not isinstance(sc, dict) and isinstance(deck_data.get("config"), dict):
                    # Backward compatibility: legacy decks stored full config snapshot.
                    sc = extract_strategy_config(
                        deck_data["config"],
                        cards=list(deck_data.get("cards") or []),
                    )

                if isinstance(sc, dict) and sc:
                    config_path = get_config_path()
                    repo = ConfigRepository(config_path)
                    existing, _, _ = repo.load_existing(allow_default_on_error=True)
                    existing_cfg = existing if isinstance(existing, dict) else {}
                    merged = apply_strategy_config(existing_cfg, strategy_config=sc)
                    res = repo.replace_with_snapshot(merged, ensure_ascii=False, indent=2)
                    if not res.ok:
                        raise RuntimeError(res.error or "config write failed")
                    self.parent.log_output.append(
                        f"[卡组] 已应用卡组 '{deck_data.get('name')}' 的策略配置"
                    )

                QMessageBox.information(
                    self,
                    "成功",
                    f"已加载卡组 '{deck_data.get('name')}'，共 {loaded_base_count} 张卡片",
                )
                self.parent.log_output.append(f"[卡组] 已加载卡组 '{deck_data.get('name')}'")

                # 刷新卡牌优先级页面（已迁移）
                if hasattr(self.parent, "card_priority_page"):
                    self.parent.card_priority_page.refresh_card_priority()

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

                    # 刷新已保存卡组列表
                    if self.deck_store is not None:
                        self.deck_store.refresh()
                    else:
                        self.refresh_saved_decks()

            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除卡组失败: {str(e)}")
                self.parent.log_output.append(f"[卡组] 删除卡组失败: {str(e)}")

    def load_deck(self):
        """加载当前卡组"""
        # 清空现有内容
        for i in reversed(range(self.grid_layout.count())):
            if widget := self.grid_layout.itemAt(i).widget():
                widget.deleteLater()

        # 获取卡组目录
        card_dir = get_card_cost_dir(ensure=True)
        if not os.path.exists(card_dir):
            no_card_label = QLabel("卡组为空，请添加卡片")
            no_card_label.setStyleSheet("color: #FF8888; font-size: 14px;")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(no_card_label, 0, 0)
            return

        # 获取所有卡片文件
        card_files = [
            f
            for f in os.listdir(card_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
        card_files = filter_non_evo_cards(card_files)

        if not card_files:
            no_card_label = QLabel("卡组为空，请添加卡片")
            no_card_label.setStyleSheet("color: #FF8888; font-size: 14px;")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(no_card_label, 0, 0)
            return

        # 刷新已保存卡组列表
        self.refresh_saved_decks()

        # 添加卡片
        row, col = 0, 0
        for card_file in card_files:
            card_path = os.path.join(card_dir, card_file)

            # 创建卡片容器
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

            # 卡片图片
            card_label = QLabel()
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.card_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)
            card_label.setContextMenuPolicy(Qt.CustomContextMenu)
            card_label.customContextMenuRequested.connect(
                lambda pos, f=card_file: self.show_context_menu(pos, f)
            )

            # 卡片名称（支持 Enhance/爆能 文件名）
            try:
                _, _, card_name = parse_card_filename(card_file)
            except Exception:
                card_name = card_file.split("_", 1)[-1].rsplit(".", 1)[0]
            card_name = " ".join(normalize_card_base_name(str(card_name or "")).split("_"))
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

            card_layout.addWidget(card_label)
            card_layout.addWidget(name_label)
            self.grid_layout.addWidget(card_container, row, col)

            col += 1
            if col >= self.cards_per_row:
                col = 0
                row += 1

    def show_context_menu(self, pos, card_file):
        """显示右键菜单"""
        menu = QMenu(self)

        remove_action = QAction("移除", self)
        remove_action.triggered.connect(lambda: self.remove_card(card_file))

        menu.addAction(remove_action)
        menu.exec_(self.sender().mapToGlobal(pos))

    def remove_card(self, card_file):
        """移除指定卡片"""
        card_path = os.path.join(get_card_cost_dir(ensure=True), card_file)
        if os.path.exists(card_path):
            try:
                os.remove(card_path)
                self.load_deck()
                self.parent.log_output.append(f"[卡组] 已移除卡片: {card_file}")

                if hasattr(self.parent, "card_priority_page"):
                    self.parent.card_priority_page.refresh_card_priority()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"移除卡片失败: {str(e)}")

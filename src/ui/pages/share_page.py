#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Share/apply deck page."""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportIncompatibleMethodOverride=false

import base64
import json
import os
import re
import shutil
import time
import zlib

from PyQt5.QtCore import Qt, QSize, QTimer

CUSTOM_DICT = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"


def decode_shortcode(shortcode: str) -> int:
    if len(shortcode) != 4:
        return 0
    return (
        CUSTOM_DICT.index(shortcode[0]) << 18
        | CUSTOM_DICT.index(shortcode[1]) << 12
        | CUSTOM_DICT.index(shortcode[2]) << 6
        | CUSTOM_DICT.index(shortcode[3])
    )


def extract_card_id_from_filename(filename: str) -> int:
    stem = os.path.splitext(os.path.basename(filename))[0]
    parts = stem.split("_")
    for part in parts:
        if part.isdigit() and len(part) >= 7 and len(part) <= 9:
            return int(part)
    return 0


from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    normalize_deck_cards,
    resolve_runtime_card_paths,
    save_deck_snapshot,
)
from src.utils.card_filename import normalize_card_base_name, parse_card_filename


class SharePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def showEvent(self, event):
        """页面显示时自动刷新预览"""
        super().showEvent(event)
        self.refresh_preview()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        # 标题
        title_label = QLabel("卡组应用和分享")
        title_label.setStyleSheet("font-size: 20px; color: #88AAFF; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 卡组预览部分
        preview_group = QGroupBox("当前卡组预览")
        preview_layout = QVBoxLayout(preview_group)

        preview_header_layout = QHBoxLayout()
        preview_title = QLabel("当前卡组中的卡片:")
        preview_title.setStyleSheet("font-size: 14px; color: #AACCFF;")

        preview_header_layout.addWidget(preview_title)
        preview_header_layout.addStretch()

        self.preview_scroll_area = QScrollArea()
        self.preview_scroll_area.setWidgetResizable(True)
        self.preview_scroll_content = QWidget()
        self.preview_grid_layout = QGridLayout(self.preview_scroll_content)
        self.preview_grid_layout.setAlignment(Qt.AlignTop)
        self.preview_scroll_area.setWidget(self.preview_scroll_content)

        self.preview_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: 1px solid #555555;
                border-radius: 5px;
            }
            QWidget#PreviewScrollContent {
                background-color: rgba(60, 60, 80, 180);
            }
        """)
        self.preview_scroll_content.setObjectName("PreviewScrollContent")

        self.preview_scroll_area.setFixedHeight(180)

        preview_layout.addLayout(preview_header_layout)
        preview_layout.addWidget(self.preview_scroll_area)

        # 卡组应用部分
        apply_group = QGroupBox("卡组应用")
        apply_layout = QVBoxLayout(apply_group)

        self.share_code_input = QLineEdit()
        self.share_code_input.setPlaceholderText("在此输入分享码...")
        self.share_code_input.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )

        apply_btn = QPushButton("应用")
        apply_btn.clicked.connect(self.apply_share_code)

        apply_layout.addWidget(QLabel("输入分享码:"))
        apply_layout.addWidget(self.share_code_input)
        apply_layout.addWidget(apply_btn)

        # 卡组分享部分
        share_group = QGroupBox("卡组分享")
        share_layout = QVBoxLayout(share_group)

        self.share_code_output = QLineEdit()
        self.share_code_output.setReadOnly(True)
        self.share_code_output.setStyleSheet(
            "background-color: rgba(80, 80, 120, 180); color: white;"
        )

        share_btn = QPushButton("生成分享码")
        share_btn.clicked.connect(self.generate_share_code)

        copy_btn = QPushButton("复制分享码")
        copy_btn.clicked.connect(self.copy_share_code)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(share_btn)
        btn_layout.addWidget(copy_btn)

        share_layout.addWidget(QLabel("您的分享码:"))
        share_layout.addWidget(self.share_code_output)
        share_layout.addLayout(btn_layout)

        back_btn = QPushButton("返回主界面")
        back_btn.clicked.connect(lambda: self.parent.stacked_widget.setCurrentIndex(0))

        main_layout.addWidget(preview_group)
        main_layout.addWidget(apply_group)
        main_layout.addWidget(share_group)
        main_layout.addStretch()
        main_layout.addWidget(back_btn)

    def generate_share_code(self):
        """生成分享码（旧格式：base64压缩）"""
        try:
            card_files = []
            card_dir = get_card_cost_dir(ensure=True)
            if os.path.exists(card_dir):
                card_files = [
                    f
                    for f in os.listdir(card_dir)
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
                ]
            card_files = filter_non_evo_cards(card_files)
            card_refs = normalize_deck_cards(card_files)

            config_path = get_config_path()
            config_data = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                except Exception:
                    config_data = {}

            strategy_config = (
                extract_strategy_config(config_data, cards=list(card_refs or []))
                if isinstance(config_data, dict)
                else {}
            )

            share_data = {
                "version": 3,
                "cards": card_refs,
                "strategy_config": strategy_config,
                "timestamp": int(time.time()),
            }

            json_data = json.dumps(share_data, ensure_ascii=False)
            compressed = zlib.compress(json_data.encode("utf-8"))

            share_code = base64.b64encode(compressed).decode("ascii")

            self.share_code_output.setText(share_code)
            self.parent.log_output.append("[分享] 分享码已生成")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"生成分享码失败: {str(e)}")
            self.parent.log_output.append(f"[分享] 生成分享码失败: {str(e)}")

    def copy_share_code(self):
        """复制分享码到剪贴板"""
        if self.share_code_output.text():
            clipboard = QApplication.clipboard()
            clipboard.setText(self.share_code_output.text())
            self.parent.log_output.append("[分享] 分享码已复制到剪贴板")
            QMessageBox.information(self, "成功", "分享码已复制到剪贴板！")

    def apply_share_code(self):
        """应用分享码（兼容旧格式base64和新格式4位Hash短码）"""
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(
                    self,
                    "运行中",
                    "脚本运行中，禁止应用分享码（会修改卡组/配置）。请先停止脚本后再操作。",
                )
                return
        except Exception:
            pass

        share_code = self.share_code_input.text().strip()
        if not share_code:
            QMessageBox.warning(self, "警告", "请输入有效的分享码！")
            return

        share_code = re.sub(r"#.*?#", "", share_code).strip()

        try:
            if self._apply_old_format(share_code):
                return
        except Exception:
            pass

        try:
            if self._apply_new_format(share_code):
                return
        except Exception as e:
            QMessageBox.warning(self, "错误", f"应用分享码失败: {str(e)}")
            self.parent.log_output.append(f"[分享] 应用分享码失败: {str(e)}")

    def _apply_old_format(self, share_code):
        """应用旧格式分享码（base64压缩）"""
        compressed = base64.b64decode(share_code.encode("ascii"))
        json_data = zlib.decompress(compressed).decode("utf-8")
        share_data = json.loads(json_data)

        version = share_data.get("version", 1)
        if version not in [1, 2, 3]:
            raise ValueError("不支持的分享码版本")

        card_dir = get_card_cost_dir(ensure=True)
        os.makedirs(card_dir, exist_ok=True)

        for f in os.listdir(card_dir):
            os.remove(os.path.join(card_dir, f))

        source_dir = os.path.join(get_exe_dir(), "quanka\SV_WB_Cards")
        exact_index, stem_index = build_card_source_index(source_dir)
        variant_index = build_card_variant_index(source_dir)
        for card_file in filter_non_evo_cards(list(share_data.get("cards", []))):
            runtime_paths = resolve_runtime_card_paths(
                source_dir,
                card_file,
                exact_index=exact_index,
                stem_index=stem_index,
                variant_index=variant_index,
            )

            if not runtime_paths:
                self.parent.log_output.append(f"[分享] 未找到卡片: {card_file}")
                continue

            for src in runtime_paths:
                if not os.path.exists(src):
                    continue
                dst = os.path.join(card_dir, os.path.basename(src))
                shutil.copy2(src, dst)

        config_path = get_config_path()
        sc = share_data.get("strategy_config")
        if not isinstance(sc, dict) and isinstance(share_data.get("config"), dict):
            sc = extract_strategy_config(
                share_data["config"], cards=list(share_data.get("cards") or [])
            )

        if isinstance(sc, dict) and sc:
            repo = ConfigRepository(config_path)
            existing, _, _ = repo.load_existing(allow_default_on_error=True)
            existing_cfg = existing if isinstance(existing, dict) else {}
            merged = apply_strategy_config(existing_cfg, strategy_config=sc)
            res = repo.replace_with_snapshot(merged, indent=4, ensure_ascii=False)
            if not res.ok:
                raise RuntimeError(res.error or "config write failed")

        if hasattr(self.parent, "config_page"):
            self.parent.config_page.refresh_config_display()
        if hasattr(self.parent, "card_priority_page"):
            self.parent.card_priority_page.refresh_card_priority()

        if hasattr(self.parent, "my_deck_page"):
            self.parent.my_deck_page.load_deck()

        self.refresh_preview()

        self._auto_save_deck()

        QMessageBox.information(self, "成功", "卡组和配置已成功应用！")
        self.parent.log_output.append("[分享] 已成功应用分享码中的卡组和配置")
        return True

    def _apply_new_format(self, share_code):
        """应用新格式分享码（4位Hash短码）"""
        shortcode_parts = share_code.split(".")
        if len(shortcode_parts) < 3:
            raise ValueError("分享码格式非法")

        card_shortcodes = shortcode_parts[2:]

        card_id_map = {}
        for sc in card_shortcodes:
            cid = decode_shortcode(sc)
            if cid > 0:
                cid_str = str(cid)
                if cid_str not in card_id_map:
                    card_id_map[cid_str] = sc

        if not card_id_map:
            raise ValueError("分享码无效或已损坏")

        card_dir = get_card_cost_dir(ensure=True)
        os.makedirs(card_dir, exist_ok=True)

        for f in os.listdir(card_dir):
            os.remove(os.path.join(card_dir, f))

        source_dir = os.path.join(get_exe_dir(), "quanka\SV_WB_Cards")
        id_to_files = {}
        if os.path.isdir(source_dir):
            all_files = []
            for root, dirs, files in os.walk(source_dir):
                for fn in files:
                    if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        all_files.append(os.path.join(root, fn))

            for fp in all_files:
                fn = os.path.basename(fp)
                cid = extract_card_id_from_filename(fn)
                if cid > 0:
                    cid_str = str(cid)
                    if cid_str not in id_to_files:
                        id_to_files[cid_str] = []
                    id_to_files[cid_str].append(fp)

        variant_index = build_card_variant_index(source_dir)
        applied_count = 0
        for cid_str in card_id_map:
            matching_files = id_to_files.get(cid_str, [])
            if not matching_files:
                shortcode = card_id_map[cid_str]
                self.parent.log_output.append(
                    f"[分享] 未找到卡牌: {shortcode} -> {cid_str}"
                )
                print(f"[分享] 未找到卡牌: {shortcode} -> {cid_str}")
                continue

            card_file = matching_files[0]
            runtime_paths = resolve_runtime_card_paths(
                source_dir,
                card_file,
                variant_index=variant_index,
            )

            for src in runtime_paths:
                if not os.path.exists(src):
                    continue
                dst = os.path.join(card_dir, os.path.basename(src))
                shutil.copy2(src, dst)
                applied_count += 1

        if hasattr(self.parent, "config_page"):
            self.parent.config_page.refresh_config_display()
        if hasattr(self.parent, "card_priority_page"):
            self.parent.card_priority_page.refresh_card_priority()

        if hasattr(self.parent, "my_deck_page"):
            self.parent.my_deck_page.load_deck()

        self.refresh_preview()

        self._auto_save_deck()

        QMessageBox.information(
            self, "成功", f"卡组已成功应用！（{applied_count}张卡牌）"
        )
        self.parent.log_output.append(
            f"[分享] 已成功应用分享码（共{applied_count}张卡牌）"
        )
        return True

    def _auto_save_deck(self):
        """自动保存应用的卡组"""
        try:
            card_dir = get_card_cost_dir(ensure=True)
            if not os.path.exists(card_dir):
                return

            card_files = [
                f
                for f in os.listdir(card_dir)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            card_files = filter_non_evo_cards(card_files)
            if not card_files:
                return

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            deck_name = f"导入卡组_{timestamp}"

            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            save_deck_snapshot(
                deck_name=deck_name,
                cards=card_files,
                decks_dir=decks_dir,
                config_path=get_config_path(),
            )

            self.parent.log_output.append(f"[卡组] 已自动保存卡组 '{deck_name}'")

            if hasattr(self.parent, "deck_store"):
                try:
                    self.parent.deck_store.refresh()
                except Exception:
                    pass

            QTimer.singleShot(500, self._refresh_deck_list)

        except Exception as e:
            self.parent.log_output.append(f"[卡组] 自动保存卡组失败: {str(e)}")

    def _refresh_deck_list(self):
        """延迟刷新卡组列表"""
        if hasattr(self.parent, "my_deck_page"):
            my_page = self.parent.my_deck_page
            try:
                my_page.refresh_saved_decks()
            except Exception:
                pass

        if hasattr(self.parent, "card_select_page"):
            cs_page = self.parent.card_select_page
            try:
                cs_page.refresh_saved_decks()
            except Exception:
                pass

    def refresh_preview(self):
        """刷新卡组预览"""
        for i in reversed(range(self.preview_grid_layout.count())):
            if widget := self.preview_grid_layout.itemAt(i).widget():
                widget.deleteLater()

        card_dir = get_card_cost_dir(ensure=True)
        if not os.path.exists(card_dir):
            no_card_label = QLabel("卡组为空")
            no_card_label.setStyleSheet("color: #FF8888; font-size: 14px;")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.preview_grid_layout.addWidget(no_card_label, 0, 0)
            return

        card_files = [
            f
            for f in os.listdir(card_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
        card_files = filter_non_evo_cards(card_files)

        if not card_files:
            no_card_label = QLabel("卡组为空")
            no_card_label.setStyleSheet("color: #FF8888; font-size: 14px;")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.preview_grid_layout.addWidget(no_card_label, 0, 0)
            return

        row, col = 0, 0
        max_cols = 4
        card_size = QSize(100, 140)

        for card_file in card_files:
            card_path = os.path.join(card_dir, card_file)

            card_container = QWidget()
            card_container.setStyleSheet("""
                background-color: rgba(60, 60, 90, 150);
                border-radius: 10px;
            """)
            card_layout = QVBoxLayout(card_container)
            card_layout.setAlignment(Qt.AlignCenter)
            card_layout.setSpacing(5)
            card_layout.setContentsMargins(5, 5, 5, 5)

            card_label = QLabel()
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    card_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)

            try:
                _, _, card_name = parse_card_filename(card_file)
            except Exception:
                card_name = card_file.split("_", 1)[-1].rsplit(".", 1)[0]
            card_name = " ".join(
                normalize_card_base_name(str(card_name or "")).split("_")
            )
            name_label = QLabel(card_name)
            name_label.setStyleSheet("""
                QLabel {
                    color: #FFFFFF;
                    background-color: transparent;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 2px;
                    max-width: %dpx;
                }
            """ % (card_size.width() - 10))
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)

            card_layout.addWidget(card_label)
            card_layout.addWidget(name_label)
            self.preview_grid_layout.addWidget(card_container, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        self.preview_scroll_content.setLayout(self.preview_grid_layout)
        self.parent.log_output.append("[预览] 卡组预览已刷新")

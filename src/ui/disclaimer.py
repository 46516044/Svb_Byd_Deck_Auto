"""统一展示启动免责声明、风险提示和交流群信息。"""

from __future__ import annotations

from html import escape

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import (
    COMMUNITY_GROUPS,
    DISCLAIMER_RISK_ITEMS,
    DISCLAIMER_VERSION,
)
from src.utils.consent_utils import (
    accept_consent_for_session,
    check_consent_file,
    remove_consent,
    save_consent,
)


class DisclaimerDialog(QDialog):
    """免责声明对话框；启动模式下必须明确勾选同意。"""

    def __init__(self, parent=None, *, require_acceptance: bool = False):
        super().__init__(parent)
        self.require_acceptance = bool(require_acceptance)
        self.setWindowTitle("免责声明与交流信息")
        self.setModal(True)
        self.resize(660, 620)
        self.setMinimumSize(560, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("免责声明")
        title.setObjectName("DisclaimerTitle")
        root.addWidget(title)

        subtitle = QLabel("请在使用前确认以下风险与发布说明")
        subtitle.setObjectName("SubtleText")
        root.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setObjectName("DisclaimerScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("DisclaimerContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)

        risk_panel = QFrame()
        risk_panel.setObjectName("DisclaimerRiskPanel")
        risk_layout = QVBoxLayout(risk_panel)
        risk_layout.setContentsMargins(16, 14, 16, 14)
        risk_layout.setSpacing(10)
        for index, text in enumerate(DISCLAIMER_RISK_ITEMS):
            if index == 0:
                body = (
                    "本工具仅供<strong style='color:#f38ba8;'>个人学习研究</strong>使用，"
                    "严禁用于任何<strong style='color:#f38ba8;'>商业盈利</strong>目的。"
                )
            elif index == 1:
                body = (
                    "使用本工具可能违反游戏用户协议，并可能导致"
                    "<strong style='color:#f38ba8;'>账号被封禁</strong>等严重后果。"
                )
            elif index == 3:
                body = (
                    "本工具免费发布，"
                    "<strong style='color:#f38ba8;'>禁止任何形式倒卖！！！</strong>"
                )
            else:
                body = escape(text)
            label = QLabel(f"<span>{index + 1}. {body}</span>")
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            label.setObjectName("DisclaimerRiskText")
            risk_layout.addWidget(label)
        content_layout.addWidget(risk_panel)

        community_title = QLabel("交流与反馈")
        community_title.setObjectName("SectionTitle")
        content_layout.addWidget(community_title)
        for group_name, group_number in COMMUNITY_GROUPS:
            row = QFrame()
            row.setObjectName("CommunityRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 8, 8)
            name = QLabel(group_name)
            name.setObjectName("SubtleText")
            number = QLabel(group_number)
            number.setObjectName("CommunityNumber")
            copy_button = QPushButton("复制")
            copy_button.setObjectName("LinkButton")
            copy_button.setToolTip(f"复制{group_name}群号")
            copy_button.clicked.connect(
                lambda _checked=False, value=group_number, button=copy_button: self._copy_group(
                    value, button
                )
            )
            row_layout.addWidget(name)
            row_layout.addStretch()
            row_layout.addWidget(number)
            row_layout.addWidget(copy_button)
            content_layout.addWidget(row)
        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        if self.require_acceptance:
            self.acceptance_checkbox = QCheckBox(
                "我已阅读并理解上述风险，自愿承担使用本工具可能产生的后果"
            )
            root.addWidget(self.acceptance_checkbox)
            self.remember_checkbox = QCheckBox("同意一次后不再显示此弹窗")
            self.remember_checkbox.setChecked(True)
            root.addWidget(self.remember_checkbox)
        else:
            self.acceptance_checkbox = None
            self.remember_checkbox = None

        actions = QHBoxLayout()
        actions.addStretch()
        if self.require_acceptance:
            reject_button = QPushButton("退出")
            reject_button.setObjectName("SecondaryButton")
            reject_button.clicked.connect(self.reject)
            self.accept_button = QPushButton("同意并继续")
            self.accept_button.setObjectName("PrimaryButton")
            self.accept_button.setEnabled(False)
            self.accept_button.clicked.connect(self.accept)
            self.acceptance_checkbox.toggled.connect(self.accept_button.setEnabled)
            actions.addWidget(reject_button)
            actions.addWidget(self.accept_button)
        else:
            self.accept_button = QPushButton("关闭")
            self.accept_button.setObjectName("PrimaryButton")
            self.accept_button.clicked.connect(self.accept)
            actions.addWidget(self.accept_button)
        root.addLayout(actions)

        version_label = QLabel(f"声明版本 {DISCLAIMER_VERSION}")
        version_label.setObjectName("DisclaimerVersion")
        version_label.setAlignment(Qt.AlignRight)
        root.addWidget(version_label)

    @staticmethod
    def _copy_group(value: str, button: QPushButton) -> None:
        QApplication.clipboard().setText(str(value))
        button.setText("已复制")
        QTimer.singleShot(1200, lambda: button.setText("复制"))


def show_disclaimer_dialog(parent=None, *, require_acceptance: bool = False) -> bool:
    """显示免责声明，返回用户是否通过对话框。"""

    dialog = DisclaimerDialog(parent, require_acceptance=require_acceptance)
    return dialog.exec_() == QDialog.Accepted


def request_disclaimer_consent(parent=None) -> tuple[bool, bool]:
    """请求启动同意，返回 ``(是否同意, 是否持久记住)``。"""

    dialog = DisclaimerDialog(parent, require_acceptance=True)
    QTimer.singleShot(0, dialog.raise_)
    QTimer.singleShot(0, dialog.activateWindow)
    accepted = dialog.exec_() == QDialog.Accepted
    remember = bool(dialog.remember_checkbox and dialog.remember_checkbox.isChecked())
    return accepted, remember


def request_startup_disclaimer(parent=None) -> bool:
    """在主窗口创建前完成免责声明确认与同意状态持久化。"""

    if check_consent_file():
        return True

    accepted, remember = request_disclaimer_consent(parent)
    if not accepted:
        return False

    if remember and not save_consent(persist_to_config=True):
        QMessageBox.warning(
            parent,
            "同意状态未保存",
            "本次可以继续使用，但下次启动仍会显示免责声明。",
        )
        accept_consent_for_session()
    elif not remember:
        cleared = remove_consent()
        accept_consent_for_session()
        if not cleared:
            QMessageBox.warning(
                parent,
                "旧同意状态未完全清除",
                "部分持久化记录无法删除，下次启动可能仍不会显示免责声明。",
            )
    return True

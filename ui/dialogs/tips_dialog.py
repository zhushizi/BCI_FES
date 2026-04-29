"""
提示框对话框：单按钮用 tips_sigle.ui，双按钮（否+确定）用 tips.ui。
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QFile, QIODevice
from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtUiTools import QUiLoader

from ui.core.resource_loader import ensure_resources_loaded
from ui.core.utils import get_ui_attr, safe_connect

UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH_SINGLE = UI_ROOT / "tips_sigle.ui"   # 仅「确定」
UI_PATH_QUESTION = UI_ROOT / "tips.ui"       # 「否」+「确定」


class TipsDialog(QDialog):
    """单按钮提示用 tips_sigle.ui，双按钮确认用 tips.ui，无顶栏，pushButton_close 关闭。"""

    def __init__(self, parent=None, message: str = "", question: bool = False):
        super().__init__(parent)
        ensure_resources_loaded()
        self._logger = logging.getLogger(__name__)
        ui_path = UI_PATH_QUESTION if question else UI_PATH_SINGLE
        ui_file = QFile(str(ui_path))
        if not ui_file.open(QIODevice.ReadOnly):
            raise FileNotFoundError(f"无法打开 UI 文件: {ui_path}")
        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        ui_file.close()
        if self.ui is None:
            raise RuntimeError(f"无法加载 UI 文件: {ui_path}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        close_btn = get_ui_attr(self.ui, "pushButton_close")
        safe_connect(self._logger, getattr(close_btn, "clicked", None), self.reject)
        confirm_btn = get_ui_attr(self.ui, "pushButton_confirm")
        if question:
            cancel_btn = get_ui_attr(self.ui, "pushButton_cancel")
            if cancel_btn is not None:
                safe_connect(self._logger, getattr(cancel_btn, "clicked", None), self.reject)
            safe_connect(self._logger, getattr(confirm_btn, "clicked", None), self.accept)
        else:
            safe_connect(self._logger, getattr(confirm_btn, "clicked", None), self.reject)

        self.set_message(message)

    def set_message(self, text: str) -> None:
        msg_label = get_ui_attr(self.ui, "label_message")
        if msg_label is not None:
            msg_label.setText(str(text or ""))

    @staticmethod
    def show_tips(parent=None, message: str = "", title: str = "") -> None:
        """显示单按钮提示框（点击确定/关闭后返回）。"""
        d = TipsDialog(parent, message=message, question=False)
        if title:
            d.setWindowTitle(title)
        d.exec()

    @staticmethod
    def show_confirm(parent=None, message: str = "") -> bool:
        """显示双按钮确认框（否+确定），使用 tips.ui。返回 True 表示点击「确定」，False 表示「否」或关闭。"""
        d = TipsDialog(parent, message=message, question=True)
        return d.exec() == QDialog.DialogCode.Accepted

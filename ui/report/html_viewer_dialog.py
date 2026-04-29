"""
报告网页展示对话框。
点击 PDF 时在软件内用 QTextBrowser 展示报告 HTML（不依赖 WebEngine，避免退出卡死）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextBrowser


class HtmlViewerDialog(QDialog):
    """在软件内用 QTextBrowser 展示报告 HTML。"""

    def __init__(
        self,
        html_content: str,
        parent=None,
        title: str = "诊疗报告",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._view = QTextBrowser(self)
        self._view.setReadOnly(True)
        self._view.setOpenExternalLinks(False)
        self._view.setHtml(html_content or "<p>暂无报告内容</p>")
        layout.addWidget(self._view)

        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(8, 8, 8, 8)
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

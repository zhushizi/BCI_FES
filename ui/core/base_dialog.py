"""
通用对话框基类：统一 UI 加载与布局嵌入流程。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtUiTools import QUiLoader

from ui.core.resource_loader import ensure_resources_loaded


class BaseUiDialog(QDialog):
    """通用对话框：负责加载 .ui 并嵌入布局。"""

    def __init__(
        self,
        parent=None,
        ui_path: str | Path = "",
        layout_margins: Sequence[int] = (0, 0, 0, 0),
        layout_spacing: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        ensure_resources_loaded()
        self._logger = logging.getLogger(__name__)
        self.ui = self._load_ui(ui_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*layout_margins)
        if layout_spacing is not None:
            layout.setSpacing(layout_spacing)
        layout.addWidget(self.ui)
        self._content_layout = layout

    def _load_ui(self, ui_path: str | Path):
        ui_file = QFile(str(ui_path))
        if not ui_file.open(QIODevice.ReadOnly):
            raise FileNotFoundError(f"无法打开 UI 文件: {ui_path}")
        loader = QUiLoader()
        form = loader.load(ui_file)
        ui_file.close()
        if form is None:
            raise RuntimeError(f"无法加载 UI 文件: {ui_path}")
        return form

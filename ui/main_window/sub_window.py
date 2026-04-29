"""
副屏窗口加载与显示。
"""

import logging
from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtGui import QGuiApplication
from PySide6.QtUiTools import QUiLoader

from ui.core.app_icon import apply_window_icon
from ui.core.resource_loader import ensure_resources_loaded
from ui.core.utils import get_ui_attr, safe_call

UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = UI_ROOT / "sub_window.ui"


class SubWindow:
    """
    副屏显示窗口（从 .ui 加载）。
    作为轻量封装，内部持有真实的 QWidget 实例。
    """

    def __init__(self):
        ensure_resources_loaded()
        self._logger = logging.getLogger(__name__)
        ui_loader = QUiLoader()
        ui_file = QFile(str(UI_PATH))
        self.widget = ui_loader.load(ui_file)
        ui_file.close()
        if self.widget is None:
            raise RuntimeError(f"加载副屏 UI 失败: {UI_PATH}")
        apply_window_icon(self.widget)

        tab_widget = get_ui_attr(self.widget, "tabWidget")
        if tab_widget:
            safe_call(self._logger, tab_widget.tabBar().hide)

    def show_on_screen(self, screen_index: int = 1) -> None:
        """
        在指定屏幕显示，默认第二块屏幕（index=1）。
        若屏幕不足，则使用最后一块屏幕。
        """
        screens = QGuiApplication.screens()
        if not screens:
            self._logger.warning("未检测到屏幕，无法显示副屏窗口")
            return

        if 0 <= screen_index < len(screens):
            target = screens[screen_index]
        else:
            target = screens[-1]

        if self.widget.windowHandle():
            self.widget.windowHandle().setScreen(target)
        geo = target.geometry()
        self.widget.setGeometry(geo)
        self.widget.showFullScreen()

    def close(self) -> None:
        """关闭副屏窗口。"""
        if self.widget:
            try:
                self.widget.close()
            except RuntimeError:
                pass
            self.widget = None

    def minimize(self) -> None:
        """最小化副屏窗口。"""
        if self.widget:
            self.widget.showMinimized()

    def hide(self) -> None:
        """隐藏副屏窗口。"""
        if self.widget:
            self.widget.hide()

    def safe_close(self) -> None:
        """安全关闭（幂等），防止重复关闭导致异常。"""
        self.close()

    def switch_tab(self, tab_index: int) -> None:
        """
        切换标签页

        Args:
            tab_index: 标签页索引（从0开始）
        """
        if self.widget is None:
            return

        tab_widget = get_ui_attr(self.widget, "tabWidget")
        if tab_widget and 0 <= tab_index < tab_widget.count():
            safe_call(self._logger, tab_widget.setCurrentIndex, tab_index)
            self._logger.debug("副窗口切换到标签页 %s", tab_index)
        else:
            count = tab_widget.count() if tab_widget else 0
            self._logger.warning("副窗口标签页索引 %s 无效，共有 %s 个标签页", tab_index, count)

"""
登录窗口 - 用户登录界面
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QWidget, QMessageBox, QLineEdit
from PySide6.QtCore import Signal, QFile
from PySide6.QtUiTools import QUiLoader

from ui.core.app_icon import apply_window_icon
from ui.core.utils import get_ui_attr, safe_call, safe_connect
from ui.dialogs.tips_dialog import TipsDialog

# UI 文件路径
UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = UI_ROOT / "login.ui"


class LoginWindow(QWidget):
    """登录窗口类"""

    # 定义信号
    login_success = Signal(dict)  # 登录成功信号，传递用户信息
    login_cancelled = Signal()    # 取消登录信号

    def __init__(self, user_app):
        """
        初始化登录窗口

        Args:
            user_app: 用户应用层实例，必须由外部传入（通过 main.py）
        """
        super().__init__()
        self._logger = logging.getLogger(__name__)

        ui_loader = QUiLoader()
        ui_file = QFile(str(UI_PATH))
        self.ui = ui_loader.load(ui_file, self)
        ui_file.close()

        if user_app is None:
            raise ValueError("user_app 参数不能为 None，必须通过 main.py 传入")
        self.user_app = user_app
        apply_window_icon(self)

        password_input = get_ui_attr(self.ui, "lineEdit_upwd")
        safe_call(self._logger, getattr(password_input, "setEchoMode", None), QLineEdit.Password)

        if get_ui_attr(self.ui, "pushButton_pwdvision"):
            self._update_password_vision_button(False)

        self._setup_connections()
        self._load_saved_credentials()

    def _setup_connections(self):
        login_button = get_ui_attr(self.ui, "pushButton_login")
        safe_connect(self._logger, getattr(login_button, "clicked", None), self._handle_login)

        password_input = get_ui_attr(self.ui, "lineEdit_upwd")
        safe_connect(self._logger, getattr(password_input, "returnPressed", None), self._handle_login)

        vision_btn = get_ui_attr(self.ui, "pushButton_pwdvision")
        safe_connect(self._logger, getattr(vision_btn, "clicked", None), self._toggle_password_visibility)

    def _load_saved_credentials(self):
        username = self.user_app.get_saved_username()
        if username:
            line_edit_uid = get_ui_attr(self.ui, "lineEdit_uid")
            safe_call(self._logger, getattr(line_edit_uid, "setText", None), username)

        if self.user_app.has_saved_credentials():
            password = self.user_app.get_saved_password()
            if password:
                line_edit_pwd = get_ui_attr(self.ui, "lineEdit_upwd")
                safe_call(self._logger, getattr(line_edit_pwd, "setText", None), password)
            checkbox = get_ui_attr(self.ui, "checkBox_remember")
            safe_call(self._logger, getattr(checkbox, "setChecked", None), True)

    def _handle_login(self):
        username_input = get_ui_attr(self.ui, "lineEdit_uid")
        password_input = get_ui_attr(self.ui, "lineEdit_upwd")
        username = (username_input.text().strip() if username_input else "")
        password = (password_input.text().strip() if password_input else "")

        if not username:
            TipsDialog.show_tips(self, "请输入用户名")
            safe_call(self._logger, getattr(username_input, "setFocus", None))
            return

        if not password:
            TipsDialog.show_tips(self, "请输入密码")
            safe_call(self._logger, getattr(password_input, "setFocus", None))
            return

        result = self.user_app.login(username, password)

        if result["success"]:
            remember = False
            checkbox = get_ui_attr(self.ui, "checkBox_remember")
            if checkbox:
                remember = bool(checkbox.isChecked())
            self.user_app.save_credentials(username, password, remember)
            self.login_success.emit(result["user"])
            self.close()
        else:
            TipsDialog.show_tips(self, result["message"])
            safe_call(self._logger, getattr(password_input, "clear", None))
            safe_call(self._logger, getattr(password_input, "setFocus", None))

    def _toggle_password_visibility(self):
        password_input = get_ui_attr(self.ui, "lineEdit_upwd")
        if not password_input:
            return
        current_mode = password_input.echoMode()
        if current_mode == QLineEdit.Password:
            password_input.setEchoMode(QLineEdit.Normal)
            self._update_password_vision_button(True)
        else:
            password_input.setEchoMode(QLineEdit.Password)
            self._update_password_vision_button(False)

    def _update_password_vision_button(self, is_visible: bool):
        button = get_ui_attr(self.ui, "pushButton_pwdvision")
        if not button:
            return
        icon_path = ":/login/pic/login_pwdopen.png" if is_visible else ":/login/pic/login_pwdclose.png"
        button.setStyleSheet(
            f"QPushButton#pushButton_pwdvision {{"
            f"    border-image: url({icon_path});"
            f"    background: transparent;"
            f"    border: none;"
            f"}}"
        )

    def closeEvent(self, event):
        if not self.user_app.is_authenticated:
            self.login_cancelled.emit()
        event.accept()

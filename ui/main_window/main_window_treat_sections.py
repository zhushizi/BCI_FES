"""
治疗页拆分模块：导航、阻抗/WS联动、会话确认。
"""

from __future__ import annotations

from PySide6.QtCore import QRect

from ui.dialogs.tips_dialog import TipsDialog
from ui.core.utils import get_ui_attr, safe_call, safe_connect


class TreatWsBridge:
    def __init__(self, host):
        self._host = host
        self.ui = host.ui
        self._logger = host._logger

    def send_impedance_close(self) -> None:
        if not self._host.ws_service:
            return
        try:
            self._host.ws_service.send_notification(
                "main.set_ImpedanceMode",
                {"open_or_close": "close"},
            )
        except Exception:
            self._logger.exception("发送阻抗关闭通知失败")

    def send_impedance_open(self) -> None:
        if not self._host.ws_service:
            return
        try:
            self._host.ws_service.send_notification(
                "main.set_ImpedanceMode",
                {"open_or_close": "open"},
            )
        except Exception:
            self._logger.exception("发送阻抗开启通知失败")

    def close_impedance_mode(self) -> None:
        try:
            self._host.impedance_ctrl.stop_impedance()
        except Exception:
            self._logger.exception("关闭阻抗检测失败")
        self.send_impedance_close()


class TreatSessionGuard:
    def __init__(self, host):
        self._host = host

    def confirm_exit_if_session_active(self) -> bool:
        if not self._host.session_app or not self._host.session_app.has_active_session():
            return True
        parent = self._host.ui.window() if self._host.ui else None
        if not TipsDialog.show_confirm(parent, "本次治疗还未完成，确认退出？"):
            return False
        self._host.session_app.end_session("manual_exit")
        return True


class TreatNavigation:
    def __init__(self, host):
        self._host = host
        self.ui = host.ui
        self._logger = host._logger

    def bind(self) -> None:
        return_btn = get_ui_attr(self.ui, "pushButton_return")
        safe_connect(self._logger, getattr(return_btn, "clicked", None), self.on_preprocess_return)
        next_btn = get_ui_attr(self.ui, "pushButton_next")
        safe_connect(self._logger, getattr(next_btn, "clicked", None), self.on_preprocess_next)

        main_tab = get_ui_attr(self.ui, "tabWidget_main")
        safe_connect(self._logger, getattr(main_tab, "currentChanged", None), self.on_main_tab_changed)
        sub_tab = get_ui_attr(self.ui, "tabWidget_2")
        safe_connect(self._logger, getattr(sub_tab, "currentChanged", None), self.on_sub_tab_changed)

    def enter_preprocess_page(self) -> None:
        self._host.stim_ctrl.reset_stimulus_grades()
        radio_checksafe = get_ui_attr(self.ui, "radioButton_checksafe")
        if radio_checksafe is not None:
            safe_call(self._logger, getattr(radio_checksafe, "setChecked", None), False)
        main_tab = get_ui_attr(self.ui, "tabWidget_main")
        if main_tab:
            main_tab.setCurrentIndex(1)
        sub_tab = get_ui_attr(self.ui, "tabWidget_2")
        if sub_tab:
            sub_tab.setCurrentIndex(0)
        self.update_preprocess_title("preprocess_eletitle.png")
        self._host.stim_ctrl.on_enter()

    def _get_grade_from_label(self, name: str) -> int:
        label = get_ui_attr(self.ui, name)
        if label is None:
            return 0
        try:
            grade_str = (label.text() or "").replace("级", "").strip()
            return int(grade_str) if grade_str else 0
        except (ValueError, AttributeError):
            return 0

    def on_preprocess_next(self) -> None:
        sub_tab = get_ui_attr(self.ui, "tabWidget_2")
        if sub_tab and sub_tab.currentIndex() == 0:
            left_grade = self._get_grade_from_label("label_left_grade")
            right_grade = self._get_grade_from_label("label_right_grade")
            if left_grade == 0 or right_grade == 0:
                TipsDialog.show_tips(self.ui, "请进行电刺激强度测试")
                return
        if not self._host.stim_ctrl.ensure_stopped_before_next():
            return
        if sub_tab:
            sub_tab.setCurrentIndex(1)
        self.update_preprocess_title("preprocess_bciImpeTitle.png")
        self._host.impedance_ctrl.on_enter()

    def on_preprocess_return(self) -> None:
        sub_tab = get_ui_attr(self.ui, "tabWidget_2")
        if sub_tab:
            current = sub_tab.currentIndex()
            if current == 2:
                try:
                    if not self._host.training_main_ctrl.is_paused_state():
                        TipsDialog.show_tips(self.ui, "请先暂停")
                        return
                except Exception:
                    self._logger.exception("检查训练暂停状态失败")
                self._host._ws_bridge.send_impedance_open()
                sub_tab.setCurrentIndex(1)
                self.update_preprocess_title("preprocess_bciImpeTitle.png")
                self._host.training_sub_ctrl.show_welcome_tab()
                return
            if current == 1:
                self._host._ws_bridge.close_impedance_mode()
                sub_tab.setCurrentIndex(0)
                self.update_preprocess_title("preprocess_eletitle.png")
                return

        if not self._host._session_guard.confirm_exit_if_session_active():
            return
        if callable(self._host._on_return_home):
            self._host._on_return_home()
        self._host.stim_ctrl.on_exit()

    def on_main_tab_changed(self, index: int) -> None:
        if index == 0:
            sub_tab = get_ui_attr(self.ui, "tabWidget_2")
            if sub_tab:
                sub_tab.setCurrentIndex(0)
            self.update_preprocess_title("preprocess_eletitle.png")

    def on_sub_tab_changed(self, index: int) -> None:
        if index == 2:
            try:
                self._host.training_main_ctrl.on_enter()
            except Exception:
                self._logger.exception("进入训练主屏失败")

    def update_preprocess_title(self, image_name: str) -> None:
        label = get_ui_attr(self.ui, "label_title")
        if label is None:
            return
        if image_name == "preprocess_bciImpeTitle.png":
            x, y, w, h = 784, 20, 333, 59
        else:
            x, y, w, h = 520, 20, 840, 59
        label.setGeometry(QRect(x, y, w, h))
        label.setMinimumSize(w, h)
        label.setMaximumSize(w, h)
        label.setStyleSheet(f"border-image: url(:/preprocess/pic/{image_name});")

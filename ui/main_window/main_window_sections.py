"""
主窗口拆分模块：导航、用户信息、设备状态、治疗流程。
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QRect, QTimer, QObject, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox, QGraphicsDropShadowEffect

from ui.core.utils import get_ui_attr, safe_call, safe_connect
from ui.dialogs.patient_select import PatientSelectDialog
from ui.dialogs.tips_dialog import TipsDialog


class MainWindowNavigation:
    def __init__(self, host):
        self._host = host
        self.ui = host.ui
        self.logger = host.logger

    def bind(self) -> None:
        def connect_click(name: str, slot: Callable[[], None]) -> None:
            button = get_ui_attr(self.ui, name)
            safe_connect(self.logger, getattr(button, "clicked", None), slot)

        connect_click("pushButton_treat", lambda: self.switch_tab(0))
        connect_click("pushButton_patient", lambda: self.switch_tab(1))
        connect_click("pushButton_plan", lambda: self.switch_tab(2))
        connect_click("pushButton_set", lambda: self.switch_tab(3))
        connect_click("pushButton_tab2home", self.switch_treat_tab_to_first)

        tab_widget = get_ui_attr(self.ui, "tabWidget")
        if tab_widget:
            safe_connect(self.logger, getattr(tab_widget, "currentChanged", None), self.on_tab_changed)
            safe_call(self.logger, tab_widget.tabBar().hide)
        tab_main = get_ui_attr(self.ui, "tabWidget_main")
        if tab_main:
            safe_call(self.logger, tab_main.tabBar().hide)

    def init_ui(self) -> None:
        self._host.setWindowTitle("BCI硬件控制系统")
        tab_widget = get_ui_attr(self.ui, "tabWidget")
        if tab_widget:
            tab_widget.setCurrentIndex(0)
            self._host._current_tab_index = 0
        tab_widget2 = get_ui_attr(self.ui, "tabWidget_2")
        if tab_widget2:
            safe_call(self.logger, tab_widget2.tabBar().hide)
            tab_widget2.setCurrentIndex(0)
        tab_main = get_ui_attr(self.ui, "tabWidget_main")
        if tab_main:
            tab_main.setCurrentIndex(0)
        label_patient = get_ui_attr(self.ui, "label_patient")
        safe_call(self.logger, getattr(label_patient, "setAlignment", None), Qt.AlignCenter)

    def switch_tab(self, tab_index: int) -> None:
        tab_widget = get_ui_attr(self.ui, "tabWidget")
        if tab_widget is None:
            return
        if getattr(self._host, "_current_tab_index", 0) == 0 and tab_index != 0:
            self._host.treat_controller.on_exit_treat_page()
        if 0 <= tab_index < tab_widget.count():
            tab_widget.setCurrentIndex(tab_index)
            self._host._current_tab_index = tab_index
            self.update_button_states()
            if tab_index == 1:
                self._host.patient_controller.refresh()
            elif tab_index == 2:
                self._host.plan_controller.refresh()
            elif tab_index == 3:
                self._host.set_controller.refresh()

    def on_tab_changed(self, index: int) -> None:
        previous_index = getattr(self._host, "_current_tab_index", 0)
        self._host._current_tab_index = index
        if previous_index == 0 and index != 0:
            self._host.treat_controller.on_exit_treat_page()
        self.update_button_states()
        if index == 1:
            self._host.patient_controller.refresh()
        elif index == 2:
            self._host.plan_controller.refresh()
        elif index == 3:
            self._host.set_controller.refresh()

    def switch_treat_tab_to_first(self) -> None:
        tab_widget = get_ui_attr(self.ui, "tabWidget")
        if tab_widget:
            tab_widget.setCurrentIndex(0)
        tab_main = get_ui_attr(self.ui, "tabWidget_main")
        if tab_main:
            tab_main.setCurrentIndex(0)
        self._host._current_tab_index = 0
        self.update_button_states()

    def update_button_states(self) -> None:
        button_configs = [
            ("pushButton_treat", "main_treat_on.png", "main_treat_off.png"),
            ("pushButton_patient", "main_patient_on.png", "main_patient_off.png"),
            ("pushButton_plan", "main_plan_on.png", "main_plan_off.png"),
            ("pushButton_set", "main_set_on.png", "main_set_off.png"),
        ]
        for idx, (button_name, on_image, off_image) in enumerate(button_configs):
            button = get_ui_attr(self.ui, button_name)
            if button is None:
                continue
            image_path = f":/main/pic/{on_image}" if idx == self._host._current_tab_index else f":/main/pic/{off_image}"
            button.setStyleSheet(
                f"QPushButton#{button_name} {{"
                f"    border-image: url({image_path});"
                f"    background: transparent;"
                f"    border: none;"
                f"}}"
            )


class MainWindowUserInfo:
    def __init__(self, host):
        self._host = host
        self.ui = host.ui

    def get_first_char(self, text: str) -> str:
        if not text:
            return ""
        first_char = text[0]
        if "\u4e00" <= first_char <= "\u9fff":
            return first_char
        if first_char.isalnum():
            return first_char
        return first_char

    def display_user_info(self) -> None:
        if not self._host.user_app.is_authenticated:
            return
        current_user = self._host.user_app.current_user
        if not current_user:
            return
        username = current_user.get("UserName", "")
        label_username = get_ui_attr(self.ui, "label_username")
        safe_call(self._host.logger, getattr(label_username, "setText", None), username)
        first_char = self.get_first_char(username)
        label_photo = get_ui_attr(self.ui, "label_userProphoto")
        if label_photo:
            label_photo.setText(first_char)
            label_photo.setStyleSheet(
                "color: rgba(149, 149, 149, 1);"
                "border-image: url(:/main/pic/main_name_rect.png);"
            )
        user_type = current_user.get("UserType", 1)
        user_title_map = {0: "管理员", 1: "普通用户", 2: "操作员"}
        user_title = user_title_map.get(user_type, "用户")
        label_title = get_ui_attr(self.ui, "label_usertitle")
        safe_call(self._host.logger, getattr(label_title, "setText", None), user_title)


class MainWindowDeviceStatus:
    def __init__(self, host):
        self._host = host
        self.ui = host.ui
        self._ws_timer: Optional[QTimer] = None

    def init_device_status(self) -> None:
        label_pingpong = get_ui_attr(self.ui, "label_pingpong")
        if label_pingpong:
            label_pingpong.setText("")
            self.set_pingpong_indicator(is_alive=False)
            self.update_treat_controls_by_pingpong()
        label_wifi = get_ui_attr(self.ui, "label_wifi")
        safe_call(self._host.logger, getattr(label_wifi, "setText", None), "")
        self._init_ws_status()

        if self._host.pingpong_service:
            try:
                interval_sec = 3.0
                if getattr(self._host, "config_app", None):
                    try:
                        interval_sec = float(self._host.config_app.get("pingpong_interval_sec", 3.0))
                    except Exception:
                        interval_sec = 3.0
                self._host.pingpong_service.configure(interval_sec=interval_sec, timeout_sec=5.0)

                def _cb(alive: bool, last_seen_sec):
                    self._host.pingpong_status_changed.emit(bool(alive), last_seen_sec)

                self._host.pingpong_service.set_status_callback(_cb)
                self._host.pingpong_service.enable()
                alive, last_seen_sec = self._host.pingpong_service.get_current_status()
                self._host.pingpong_status_changed.emit(alive, last_seen_sec)
            except Exception as e:
                self._host.logger.error(f"心跳服务初始化失败: {e}")

    def set_pingpong_indicator(self, is_alive: bool) -> None:
        label_pingpong = get_ui_attr(self.ui, "label_pingpong")
        if label_pingpong is None:
            return
        if is_alive:
            label_pingpong.setStyleSheet("border-image: url(:/main/pic/main_pingpong_on.png);")
            label_pingpong.setToolTip("心跳正常")
        else:
            label_pingpong.setStyleSheet("border-image: url(:/main/pic/main_pingpong_off.png);")
            label_pingpong.setToolTip("心跳超时")

    def _init_ws_status(self) -> None:
        self._set_wifi_indicator(False)
        if not self._host.ws_service:
            return
        if self._ws_timer is None:
            self._ws_timer = QTimer(self.ui)
            self._ws_timer.setInterval(1000)
            safe_connect(self._host.logger, self._ws_timer.timeout, self._poll_ws_status)
        if not self._ws_timer.isActive():
            self._ws_timer.start()

    def _poll_ws_status(self) -> None:
        if not self._host.ws_service:
            self._set_wifi_indicator(False)
            return
        try:
            self._set_wifi_indicator(self._host.ws_service.is_connected())
        except Exception:
            self._set_wifi_indicator(False)

    def _set_wifi_indicator(self, is_connected: bool) -> None:
        label_wifi = get_ui_attr(self.ui, "label_wifi")
        if label_wifi is None:
            return
        if is_connected:
            label_wifi.setStyleSheet("border-image: url(:/main/pic/main_wifi_on.png);")
            label_wifi.setToolTip("服务器连接正常")
        else:
            label_wifi.setStyleSheet("border-image: url(:/main/pic/main_wifi_off.png);")
            label_wifi.setToolTip("服务器未连接")

    def on_pingpong_status_changed(self, is_alive: bool, last_seen_sec) -> None:
        self.set_pingpong_indicator(bool(is_alive))
        self.update_treat_controls_by_pingpong()

    def is_pingpong_online(self) -> bool:
        label_pingpong = get_ui_attr(self.ui, "label_pingpong")
        if label_pingpong is None:
            return True
        try:
            return label_pingpong.toolTip() == "心跳正常"
        except Exception:
            return True

    def update_treat_controls_by_pingpong(self) -> None:
        try:
            is_online = self.is_pingpong_online()
            if self._host.treat_controller and self._host.treat_controller.stim_ctrl:
                self._host.treat_controller.stim_ctrl.set_hardware_online(is_online)
        except Exception:
            pass


class MainWindowTreatFlow:
    def __init__(self, host):
        self._host = host
        self.ui = host.ui
        self.logger = host.logger
        self._hover_filters: list[_HoverShadowFilter] = []

    def bind(self) -> None:
        def connect_click(name: str, slot: Callable[[], None]) -> None:
            button = get_ui_attr(self.ui, name)
            safe_connect(self.logger, getattr(button, "clicked", None), slot)

        connect_click("pushButton_tab1select", self.open_patient_select_dialog)

        treat_buttons = [
            "pushButton_gou_ssvep",
            "pushButton_gou_ssmvep",
            "pushButton_gou_mi",
            "pushButton_tai_ssvep",
            "pushButton_tai_ssmvep",
            "pushButton_tai_mi",
        ]
        for button_name in treat_buttons:
            button = get_ui_attr(self.ui, button_name)
            if button:
                self._attach_hover_shadow(button)
                safe_connect(
                    self.logger,
                    getattr(button, "clicked", None),
                    lambda checked=False, name=button_name: self.open_treat_page(name),
                )
        if not any(get_ui_attr(self.ui, name) for name in treat_buttons):
            connect_click("pushButton", self.open_treat_page)
            connect_click("pushButton_3", self.open_treat_page)

        start_evaluate_btn = get_ui_attr(self.ui, "pushButton_startevaluate")
        safe_connect(self.logger, getattr(start_evaluate_btn, "clicked", None), self.on_start_evaluate_clicked)

    def _attach_hover_shadow(self, button) -> None:
        effect = QGraphicsDropShadowEffect(button)
        effect.setBlurRadius(18)
        effect.setOffset(0, 0)
        effect.setColor(QColor(0, 0, 0, 90))
        effect.setEnabled(False)
        button.setGraphicsEffect(effect)
        hover_filter = _HoverShadowFilter(button, effect)
        button.installEventFilter(hover_filter)
        self._hover_filters.append(hover_filter)


    def open_patient_select_dialog(self) -> None:
        dialog = PatientSelectDialog(self._host, self._host.patient_app)
        dialog.patient_selected.connect(self.on_patient_selected)
        dialog.exec()

    def on_patient_selected(self, patient: dict) -> None:
        patient_name = patient.get("Name", "")
        label_patient = get_ui_attr(self.ui, "label_patient")
        if label_patient:
            label_patient.setText(patient_name)
        else:
            label_fallback = get_ui_attr(self.ui, "label_11")
            safe_call(self.logger, getattr(label_fallback, "setText", None), patient_name)
        self._host._selected_patient = patient
        self._host.treat_controller.set_current_patient(patient)

    @staticmethod
    def extract_patient_id(patient: dict | None) -> str | None:
        if not patient:
            return None
        pid = patient.get("PatientId") or patient.get("Name") or ""
        pid = str(pid).strip()
        return pid or None

    def open_treat_page(self, button_name: str | None = None) -> None:
        if not self._host._selected_patient:
            TipsDialog.show_tips(self._host, "请先选择患者")
            return
        if getattr(self._host, "treat_flow_app", None) and button_name:
            self._host.treat_flow_app.start_treat_from_button(self._host._selected_patient, button_name)
        if hasattr(self._host.treat_controller, "set_treat_entry_button"):
            self._host.treat_controller.set_treat_entry_button(button_name)
        self._host.treat_controller.set_current_patient(self._host._selected_patient)
        self._host.treat_controller.enter_preprocess_page()

    def start_treatment_both_channels(self) -> None:
        try:
            if self._host.hardware_app:
                self._host.hardware_app.start_treatment_dual()
        except Exception as e:
            self.logger.error(f"发送治疗开始命令失败: {e}")

    def on_start_evaluate_clicked(self) -> None:
        try:
            impedance_ctrl = getattr(self._host.treat_controller, "impedance_ctrl", None)
        except Exception:
            impedance_ctrl = None
        if impedance_ctrl is not None and not impedance_ctrl.is_checksafe_checked():
            TipsDialog.show_tips(self.ui, "请先勾选安全提示确认")
            return
        try:
            if self._host.treat_controller and self._host.treat_controller.impedance_ctrl:
                self._host.treat_controller.impedance_ctrl.stop_impedance()
        except Exception:
            pass
        if getattr(self._host, "treat_flow_app", None):
            self._host.treat_flow_app.send_impedance_close()
            exe_path, paradigm_class = self._host.treat_flow_app.resolve_paradigm_exe_from_session()
        else:
            exe_path, paradigm_class = None, None
        if exe_path and self._host.treat_controller and self._host.treat_controller.training_sub_ctrl:
            self._host.treat_controller.training_sub_ctrl.set_paradigm_exe_path(exe_path)
        # if self._host.ws_service:
        #     try:
        #         self._host.ws_service.send_notification(
        #             "paradigm.paradigm_class",
        #             {"paradigm_class": paradigm_class or "SSVEP", "target_class": [9, 12]},
        #         )
        #     except Exception:
        #         pass
        tab_widget2 = get_ui_attr(self.ui, "tabWidget_2")
        if tab_widget2:
            tab_widget2.setCurrentIndex(2)
        try:
            if self._host.treat_controller and self._host.treat_controller.training_sub_ctrl:
                self._host.treat_controller.training_sub_ctrl.start_paradigm_service(
                    switch_tab=False,
                    show_screen=False,
                )
        except Exception:
            pass
        self.update_title_to_practising()

    def update_title_to_practising(self, x: int = None, y: int = None, width: int = None, height: int = None) -> None:
        label_title = get_ui_attr(self.ui, "label_title")
        if label_title is None:
            return
        default_x = 860 if x is None else x
        default_y = 20 if y is None else y
        default_width = 270 if width is None else width
        default_height = 59 if height is None else height
        label_title.setGeometry(QRect(default_x, default_y, default_width, default_height))
        label_title.setMinimumSize(default_width, default_height)
        label_title.setMaximumSize(default_width, default_height)
        label_title.setStyleSheet("border-image: url(:/treat/pic/treat_practising.png);")


class _HoverShadowFilter(QObject):
    def __init__(self, target, effect: QGraphicsDropShadowEffect):
        super().__init__(target)
        self._target = target
        self._effect = effect

    def eventFilter(self, obj, event):
        if obj is self._target:
            if event.type() == QEvent.Enter:
                self._effect.setEnabled(True)
            elif event.type() == QEvent.Leave:
                self._effect.setEnabled(False)
        return super().eventFilter(obj, event)

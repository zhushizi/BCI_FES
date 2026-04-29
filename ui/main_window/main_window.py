"""
主窗口 - 应用程序主界面
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QWidget, QMessageBox
from PySide6.QtCore import Signal, QFile
from PySide6.QtUiTools import QUiLoader

from ui.core.app_icon import apply_window_icon
from ui.core.resource_loader import ensure_resources_loaded
from ui.core.utils import get_ui_attr, safe_call, safe_connect
from ui.main_window.main_window_treat import TreatPageController
from ui.main_window.main_window_patient import PatientPageController
from ui.main_window.main_window_plan import PlanPageController
from ui.main_window.main_window_set import SetPageController
from ui.main_window.main_window_sections import (
    MainWindowNavigation,
    MainWindowUserInfo,
    MainWindowDeviceStatus,
    MainWindowTreatFlow,
)
from application.session_app import SessionApp

# UI 文件路径
UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = UI_ROOT / "main_window.ui"


class MainWindow(QWidget):
    """主窗口类：负责用户信息、患者选择、设备状态与子模块管理"""

    logout_requested = Signal()  # 登出请求信号
    pingpong_status_changed = Signal(bool, object)  # alive, last_seen_sec(None 或 float)
    impedance_value_received = Signal(object)  # params dict
    eeg_frame_received = Signal(object)  # EEG 波形帧
    intent_result_received = Signal(object)  # intent_result 指标
    start_decoding_received = Signal()
    stop_session_received = Signal()
    stage_rest_received = Signal()  # paradigm.Stage stage=rest，暂停倒计时

    def __init__(
        self,
        user_app,
        patient_app,
        scheme_app,
        sub_window=None,
        report_app=None,
        session_app: SessionApp | None = None,
        hardware_app=None,
        pingpong_service=None,
        stim_test_app=None,
        impedance_app=None,
        training_main_app=None,
        training_sub_app=None,
        ws_service=None,
        paradigm_exe_path: str | None = None,
        decoder_port: str | None = None,
        decoder_app=None,
        config_app=None,
        reaction_time_app=None,
        treat_flow_app=None,
        training_flow_app=None,
        hardware_config_app=None,
        hide_subprocess_console: bool = False,
    ):
        super().__init__()

        ensure_resources_loaded()
        self.logger = logging.getLogger(__name__)

        if user_app is None:
            raise ValueError("user_app 参数不能为 None")
        if patient_app is None:
            raise ValueError("patient_app 参数不能为 None")
        if scheme_app is None:
            raise ValueError("scheme_app 参数不能为 None")

        self.user_app = user_app
        self.patient_app = patient_app
        self.scheme_app = scheme_app
        self.report_app = report_app  # 报告应用层
        self.session_app = session_app  # 治疗会话应用层
        self.sub_window = sub_window  # 副窗口引用
        self.hardware_app = hardware_app  # 硬件应用层（推荐）
        self.pingpong_service = pingpong_service  # 硬件心跳保活服务（可选）
        self.ws_service = ws_service
        self.config_app = config_app
        self.reaction_time_app = reaction_time_app
        self.treat_flow_app = treat_flow_app
        self.training_flow_app = training_flow_app
        self.hardware_config_app = hardware_config_app
        # 新的四模块应用层（框架阶段）
        self.stim_test_app = stim_test_app
        self.impedance_app = impedance_app
        self.training_main_app = training_main_app
        self.training_sub_app = training_sub_app

        self._selected_patient = None
        self._current_tab_index = 0
        # 关闭主窗口时需要向下位机发送左右通道关闭命令；用一次性标记避免重复发送
        self._hw_shutdown_sent = False

        ui_loader = QUiLoader()
        ui_file = QFile(str(UI_PATH))
        self.ui = ui_loader.load(ui_file, self)
        ui_file.close()
        apply_window_icon(self)

        # 子模块控制器
        self.treat_controller = TreatPageController(
            self.ui,
            on_return_home=self._switch_treat_tab_to_first,
            sub_window=self.sub_window,
            patient_app=self.patient_app,
            session_app=self.session_app,
            stim_test_app=self.stim_test_app,
            impedance_app=self.impedance_app,
            training_main_app=self.training_main_app,
            training_sub_app=self.training_sub_app,
            ws_service=self.ws_service,
            config_app=self.config_app,
            reaction_time_app=self.reaction_time_app,
            training_flow_app=self.training_flow_app,
            paradigm_exe_path=paradigm_exe_path,
            hide_subprocess_console=hide_subprocess_console,
        )
        self.patient_controller = PatientPageController(
            self, self.ui, self.patient_app, self.user_app, self.logger,
            on_patient_selected=self._on_patient_selected, report_app=self.report_app
        )
        self.plan_controller = PlanPageController(self, self.ui, self.scheme_app, self.logger)
        self.decoder_port = decoder_port
        self.set_controller = SetPageController(
            self,
            self.ui,
            self.logger,
            decoder_port=self.decoder_port,
            hardware_config_app=self.hardware_config_app,
        )

        # 主窗口拆分模块
        self._nav = MainWindowNavigation(self)
        self._user_info = MainWindowUserInfo(self)
        self._device_status = MainWindowDeviceStatus(self)
        self._treat_flow = MainWindowTreatFlow(self)

        self._setup_connections()
        self._init_ui()
        self._display_user_info()
        self._bind_session_events()

    def _setup_connections(self):
        """设置信号和槽的连接"""
        # 导航与治疗入口
        self._nav.bind()
        self._treat_flow.bind()

        # 登出
        button_logout = get_ui_attr(self.ui, "pushButton_logout")
        safe_connect(self.logger, getattr(button_logout, "clicked", None), self._handle_logout)

        # 心跳在线/离线：跨线程用 signal 串到 UI 线程更新
        self.pingpong_status_changed.connect(self._on_pingpong_status_changed)
        self.impedance_value_received.connect(self._on_impedance_value_received)

        # 窗口控制
        minimize_btn = get_ui_attr(self.ui, "pushButton_small") or get_ui_attr(self.ui, "pushButton_2")
        quit_btn = get_ui_attr(self.ui, "pushButton_quit") or get_ui_attr(self.ui, "pushButton")
        safe_connect(self.logger, getattr(minimize_btn, "clicked", None), self.showMinimized)
        safe_connect(self.logger, getattr(quit_btn, "clicked", None), self.close)

        # 子模块自身信号
        self.treat_controller.bind_signals()
        self.patient_controller.bind_signals()
        self.plan_controller.bind_signals()
        self.set_controller.bind_signals()

        # EEG 波形数据
        try:
            self.eeg_frame_received.connect(self.treat_controller.training_main_ctrl.on_eeg_frame)
        except Exception:
            pass
        try:
            self.intent_result_received.connect(self.treat_controller.training_main_ctrl.on_intent_result)
        except Exception:
            pass

        try:
            # 开始/暂停仅由「开始」「暂停」按钮触发，不再响应 paradigm.start_decoding / paradigm.Stage
            # self.start_decoding_received.connect(self.treat_controller.training_main_ctrl.start_countdown)
            self.stop_session_received.connect(self.treat_controller.training_main_ctrl.stop_countdown)
            # self.stage_rest_received.connect(self.treat_controller.training_main_ctrl.pause_countdown)
        except Exception:
            pass
        try:
            if self.training_main_app and hasattr(self.training_main_app, "set_on_pretrain_full_completed"):
                self.training_main_app.set_on_pretrain_full_completed(
                    self.treat_controller.training_main_ctrl.set_pretrain_full_completed
                )
        except Exception:
            pass

    def _bind_session_events(self) -> None:
        try:
            if self.training_sub_app and hasattr(self.training_sub_app, "set_on_start_decoding"):
                self.training_sub_app.set_on_start_decoding(self.start_decoding_received.emit)
        except Exception:
            pass
        try:
            if self.training_sub_app and hasattr(self.training_sub_app, "set_on_stage_rest"):
                self.training_sub_app.set_on_stage_rest(self.stage_rest_received.emit)
        except Exception:
            pass
        try:
            if self.session_app and hasattr(self.session_app, "set_on_stop_session"):
                self.session_app.set_on_stop_session(self.stop_session_received.emit)
        except Exception:
            pass

    def _init_ui(self):
        """初始化UI状态"""
        self._nav.init_ui()
        self._update_button_states()
        self._init_device_status()

        # 初始化各子页
        self.patient_controller.init_ui()
        self.plan_controller.init_ui()
        self.set_controller.init_ui()

    def _switch_tab(self, tab_index: int):
        """切换顶级标签页 (0=治疗, 1=患者, 2=方案, 3=设置)"""
        self._nav.switch_tab(tab_index)

    def _on_tab_changed(self, index: int):
        self._nav.on_tab_changed(index)

    def _switch_treat_tab_to_first(self):
        """切换到治疗标签页（tab_treat）"""
        self._nav.switch_treat_tab_to_first()

    def _update_button_states(self):
        """更新导航按钮的状态（on/off图片）"""
        self._nav.update_button_states()

    def _open_patient_select_dialog(self):
        """打开患者选择弹窗"""
        self._treat_flow.open_patient_select_dialog()

    def _on_patient_selected(self, patient: dict):
        self._treat_flow.on_patient_selected(patient)

    def _open_treat_page(self, button_name: str | None = None):
        """打开治疗页面（需要先选择患者）"""
        self._treat_flow.open_treat_page(button_name)

    def _start_treatment_both_channels(self):
        """发送左右通道的开始治疗命令帧（保留位区分通道）"""
        self._treat_flow.start_treatment_both_channels()

    def _get_first_char(self, text: str) -> str:
        return self._user_info.get_first_char(text)

    def _extract_patient_id(self, patient: dict | None) -> str | None:
        return self._treat_flow.extract_patient_id(patient)

    def clear_treat_context_if_patient_removed(self, removed_patient_id: str) -> None:
        """
        在患者管理删除患者后调用：若删除的是当前已选患者，则清空治疗区选择、会话缓存与活动会话，
        避免治疗详情仍显示已删患者并可继续治疗。
        """
        rid = str(removed_patient_id or "").strip()
        if not rid:
            return
        selected = self._selected_patient
        if not selected:
            return
        sid = str(selected.get("PatientId") or selected.get("Name") or "").strip()
        if sid != rid:
            return

        label_patient = get_ui_attr(self.ui, "label_patient")
        if label_patient:
            safe_call(self.logger, getattr(label_patient, "setText", None), "未选择患者")
        else:
            label_fallback = get_ui_attr(self.ui, "label_11")
            safe_call(self.logger, getattr(label_fallback, "setText", None), "未选择患者")
        self._selected_patient = None

        if self.session_app:
            try:
                cur = self.session_app.get_current_patient_id()
                cur_s = str(cur or "").strip()
                if cur_s == rid and self.session_app.has_active_session():
                    self.session_app.end_session("patient_deleted")
                self.session_app.set_current_patient("")
            except Exception:
                self.logger.exception("患者删除后清理会话状态失败")

        if self.treat_controller:
            try:
                self.treat_controller.set_current_patient(None)
            except Exception:
                self.logger.exception("患者删除后清空治疗页患者失败")

    def _parse_treat_button_info(self, button_name: str) -> tuple[str, str, str]:
        return self._treat_flow.parse_treat_button_info(button_name)

    def _display_user_info(self):
        self._user_info.display_user_info()

    def _init_device_status(self):
        """初始化设备连接状态显示"""
        self._device_status.init_device_status()

    def _set_pingpong_indicator(self, is_alive: bool) -> None:
        """更新 UI 上 pingpong 图标（占位：在线用资源图，离线用红点）"""
        self._device_status.set_pingpong_indicator(is_alive)

    def _on_pingpong_status_changed(self, is_alive: bool, last_seen_sec) -> None:
        """
        心跳状态变化回调（已在 UI 线程）

        TODO(占位)：后续可在离线时弹窗/写日志/触发重连等操作
        """
        self._device_status.on_pingpong_status_changed(bool(is_alive), last_seen_sec)

    def _on_impedance_value_received(self, params) -> None:
        """接收阻抗值并更新阻抗页 UI（已在 UI 线程）"""
        try:
            p = params or {}
            if self.treat_controller and self.treat_controller.impedance_ctrl:
                self.treat_controller.impedance_ctrl.apply_impedance_values(p)
            electrodes = p.get("electrode") or p.get("Electrode")
            if (
                isinstance(electrodes, list)
                and len(electrodes) > 0
                and self.treat_controller
                and self.treat_controller.training_main_ctrl
            ):
                self.treat_controller.training_main_ctrl.set_wave_channel_labels_from_impedance(electrodes)
        except Exception:
            pass

    def _is_pingpong_online(self) -> bool:
        return self._device_status.is_pingpong_online()

    def _update_treat_controls_by_pingpong(self) -> None:
        """根据 pingpong 状态更新电刺激控件可用性"""
        self._device_status.update_treat_controls_by_pingpong()

    def _handle_logout(self):
        reply = QMessageBox.question(
            self,
            "确认登出",
            "确定要退出登录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.user_app.logout()
            self.logout_requested.emit()
            self.close()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _on_start_evaluate_clicked(self):
        """开始评估按钮点击事件：切换主窗口和副窗口的标签页"""
        self._treat_flow.on_start_evaluate_clicked()

    def _send_impedance_close(self) -> None:
        self._treat_flow.send_impedance_close()

    def _update_title_to_practising(self, x: int = None, y: int = None, width: int = None, height: int = None):
        """
        设置 label_title 为训练中图片

        Args:
            x: 标签的 x 坐标（可选，默认使用图片原始尺寸）
            y: 标签的 y 坐标（可选，默认使用图片原始尺寸）
            width: 标签的宽度（可选，默认使用图片原始尺寸）
            height: 标签的高度（可选，默认使用图片原始尺寸）
        """
        self._treat_flow.update_title_to_practising(x=x, y=y, width=width, height=height)

    def closeEvent(self, event):
        # 主窗口关闭（销毁前）统一收口：尽量停止各模块 + 发送 paradigm.shut_down + 下位机左右通道关闭命令
        if not getattr(self, "_hw_shutdown_sent", False):
            self._hw_shutdown_sent = True
            try:
                # 发送 main.tigger paradigm.shut_down，确保范式也退出
                if self.ws_service:
                    try:
                        self.ws_service.send_notification(
                            "main.tigger",
                            {"tigger_target": "paradigm.shut_down"},
                        )
                    except Exception as e:
                        self.logger.warning("发送 paradigm.shut_down 失败: %s", e)
                # 若当前在治疗页/预处理页，确保先走一遍“离开治疗页”收口逻辑
                if hasattr(self, "treat_controller") and self.treat_controller:
                    self.treat_controller.on_exit_treat_page()
            except Exception as e:
                self.logger.error(f"主窗口关闭时停止模块失败: {e}")
            # 注意：treat_controller.on_exit_treat_page() 内部会调用电刺激模块的 stop_dual()，
            # 已经发送过左右通道停止命令；这里不再重复发送，避免退出时发两次。

        event.accept()
        super().closeEvent(event)

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout

from ui.dialogs.tips_dialog import TipsDialog
from ui.widgets.circle_level_widget import CircleLevelWidget
from application.session_app import SessionApp, PatientTreatParams
from application.stim_test_app import StimTestApp
from ui.core.utils import get_ui_attr, safe_call, safe_connect


class StimTestController:
    """
    电刺激测试模块（tabWidget_2 index=0 / tab_3）。

    目标：把电刺激相关的 UI 逻辑从 `TreatPageController` 剥离出来，
    让上层只负责导航与页面编排。
    """

    _NEXT_CONFIRM = "确认"
    _NEXT_ITEM = "下一项"
    _FREQ_MIN_MS = 20
    _FREQ_MAX_MS = 100
    _FREQ_DEFAULT_MS = 20
    _TIME_MIN_TENTHS = 1
    _TIME_MAX_TENTHS = 20
    _TIME_DEFAULT_TENTHS = 12

    _STYLE_LEG_SELECTED = (
        "QPushButton { background-color: rgb(219, 233, 247); color: rgb(88, 122, 244); "
        "border: 2px solid rgb(88, 122, 244); border-radius: 10px; }"
    )
    _STYLE_LEG_NORMAL = (
        "QPushButton { background-color: rgb(240, 242, 245); color: rgb(120, 120, 120); "
        "border: 1px solid rgb(200, 200, 200); border-radius: 10px; }"
    )

    def __init__(self, ui, session_app: Optional[SessionApp] = None, stim_app: Optional[StimTestApp] = None):
        self.ui = ui
        self.session_app = session_app
        self.stim_app = stim_app
        self._logger = logging.getLogger(__name__)
        self._treat_entry_button: Optional[str] = None
        self._current_patient_for_leg: dict | None = None
        self._dual_leg_flow_step: int = 0
        self._active_leg_channel: str = "left"

        # True=开始状态（stop可用/start不可用/next不可用）；False=停止状态（start可用/stop不可用/next可用）
        self._test_running = False
        # 设备在线状态（影响控件可用性）
        self._hardware_online = True

        # 频率默认 20ms。这里在绑定信号前设置，避免触发下发指令。
        self._set_default_freq()

        # 记录 UI 初始默认的方案/频率值（用于患者第一次进入时初始化）
        self._default_params = {
            "left_scheme_idx": self._get_combo_index("comboBox_left_scheme") or 0,
            "left_freq_idx": self._get_freq_value(),
        }

        self._current_patient_id: Optional[str] = None
        self._left_circle_widget: Optional[CircleLevelWidget] = None
        self._right_circle_widget: Optional[CircleLevelWidget] = None
        self._time_scroll_widgets: dict[str, dict[str, object]] = {}

    def set_treat_entry_button(self, button_name: Optional[str]) -> None:
        self._treat_entry_button = (button_name or "").strip() or None

    def _stim_leg_part_label(self) -> str:
        """范式按钮名含 gou→小腿，含 tai→大腿；默认小腿。"""
        n = (self._treat_entry_button or "").lower()
        if "tai" in n:
            return "大腿"
        if "gou" in n:
            return "小腿"
        return "小腿"

    def _patient_leg_display_mode(self) -> str:
        """双腿：both；仅左腿/右腿：只展示单侧。"""
        p = self._current_patient_for_leg
        if not p:
            return "both"
        leg = str(p.get("Leg") or "").strip()
        if leg == "左腿":
            return "left"
        if leg == "右腿":
            return "right"
        return "both"

    def refresh_stim_leg_bar(self) -> None:
        """刺激位置栏始终展示；文案随范式 gou/tai；单侧只显示对应腿。"""
        bar = get_ui_attr(self.ui, "widget_stim_leg_bar")
        safe_call(self._logger, getattr(bar, "setVisible", None), True)
        part = self._stim_leg_part_label()
        btn_l = get_ui_attr(self.ui, "pushButton_stim_leg_left")
        btn_r = get_ui_attr(self.ui, "pushButton_stim_leg_right")
        if btn_l:
            safe_call(self._logger, getattr(btn_l, "setText", None), f"左腿（{part}）")
        if btn_r:
            safe_call(self._logger, getattr(btn_r, "setText", None), f"右腿（{part}）")
        mode = self._patient_leg_display_mode()
        if btn_l:
            safe_call(self._logger, getattr(btn_l, "setVisible", None), mode in ("both", "left"))
        if btn_r:
            safe_call(self._logger, getattr(btn_r, "setVisible", None), mode in ("both", "right"))
        self._dual_leg_flow_step = 0
        self._set_leg_highlight(left_selected=(mode != "right"))
        self._set_preprocess_next_button_text(self._NEXT_CONFIRM if mode == "both" else self._NEXT_ITEM)
        self._hide_right_channel_widgets()

    def reset_dual_leg_flow(self) -> None:
        """重置“确认/下一项”流程：双腿为确认，单腿为下一项。"""
        self._dual_leg_flow_step = 0
        mode = self._patient_leg_display_mode()
        self._set_preprocess_next_button_text(self._NEXT_CONFIRM if mode == "both" else self._NEXT_ITEM)

    def on_completed_leave_stim_tab(self) -> None:
        """离开电刺激子页进入阻抗页后：重置确认/下一项流程。"""
        self._dual_leg_flow_step = 0
        self.reset_dual_leg_flow()

    def _set_preprocess_next_button_text(self, text: str) -> None:
        btn = get_ui_attr(self.ui, "pushButton_next")
        safe_call(self._logger, getattr(btn, "setText", None), text)

    def _set_leg_highlight(self, left_selected: bool) -> None:
        btn_l = get_ui_attr(self.ui, "pushButton_stim_leg_left")
        btn_r = get_ui_attr(self.ui, "pushButton_stim_leg_right")
        mode = self._patient_leg_display_mode()
        if mode == "left":
            self._active_leg_channel = "left"
            if btn_l:
                safe_call(self._logger, getattr(btn_l, "setChecked", None), True)
                safe_call(self._logger, getattr(btn_l, "setStyleSheet", None), self._STYLE_LEG_SELECTED)
            if btn_r:
                safe_call(self._logger, getattr(btn_r, "setStyleSheet", None), self._STYLE_LEG_NORMAL)
            return
        if mode == "right":
            self._active_leg_channel = "right"
            if btn_r:
                safe_call(self._logger, getattr(btn_r, "setChecked", None), True)
                safe_call(self._logger, getattr(btn_r, "setStyleSheet", None), self._STYLE_LEG_SELECTED)
            if btn_l:
                safe_call(self._logger, getattr(btn_l, "setStyleSheet", None), self._STYLE_LEG_NORMAL)
            return
        self._active_leg_channel = "left" if left_selected else "right"
        if btn_l:
            safe_call(self._logger, getattr(btn_l, "setChecked", None), left_selected)
            safe_call(self._logger, getattr(btn_l, "setStyleSheet", None), self._STYLE_LEG_SELECTED if left_selected else self._STYLE_LEG_NORMAL)
        if btn_r:
            safe_call(self._logger, getattr(btn_r, "setChecked", None), not left_selected)
            safe_call(self._logger, getattr(btn_r, "setStyleSheet", None), self._STYLE_LEG_NORMAL if left_selected else self._STYLE_LEG_SELECTED)

    def handle_dual_leg_next_click(self) -> bool:
        """双腿患者需先点“确认”，再点“下一项”才允许跳页。"""
        if self._patient_leg_display_mode() != "both":
            return False
        if self._dual_leg_flow_step == 0:
            if self._test_running:
                TipsDialog.show_tips(self.ui, "请先点击“停止测试”，停止后才能确认当前侧")
                return True
            if self._get_left_grade() <= 0:
                TipsDialog.show_tips(self.ui, f"请完成{self._leg_text(self._selected_leg_channel())}（{self._stim_leg_part_label()}）侧电刺激强度测试")
                return True
            self._save_current_params()
            self._dual_leg_flow_step = 1
            self._switch_active_leg(left=False, save_current=False)
            self._set_preprocess_next_button_text(self._NEXT_ITEM)
            return True
        return False

    def stim_grades_satisfied_for_next(self) -> bool:
        """离开电刺激页前：检查当前患者需要测试的腿部档位。"""
        self._save_current_params()
        part = self._stim_leg_part_label()
        mode = self._patient_leg_display_mode()
        params = self._load_current_treat_params()
        if mode == "both":
            checks = (
                ("left", getattr(params, "left_grade", 0) if params else 0),
                ("right", getattr(params, "right_grade", 0) if params else 0),
            )
        else:
            channel = "right" if mode == "right" else "left"
            checks = ((channel, self._get_left_grade()),)
        for channel, grade in checks:
            if int(grade or 0) <= 0:
                TipsDialog.show_tips(self.ui, f"请完成{self._leg_text(channel)}（{part}）侧电刺激强度测试")
                return False
        return True

    @property
    def is_test_running(self) -> bool:
        return bool(self._test_running)

    def bind_signals(self) -> None:
        leg_l = get_ui_attr(self.ui, "pushButton_stim_leg_left")
        leg_r = get_ui_attr(self.ui, "pushButton_stim_leg_right")
        if leg_l is not None and leg_r is not None:
            safe_connect(self._logger, getattr(leg_l, "clicked", None), lambda: self._on_stim_leg_clicked(True))
            safe_connect(self._logger, getattr(leg_r, "clicked", None), lambda: self._on_stim_leg_clicked(False))

        # 开始/停止合并到同一按钮：点击切换
        start_btn = get_ui_attr(self.ui, "pushButton_start_test")
        safe_connect(self._logger, getattr(start_btn, "clicked", None), self._on_start_stop_test_clicked)
        stop_btn = get_ui_attr(self.ui, "pushButton_stop_test")
        if stop_btn is not None:
            stop_btn.setVisible(False)

        # 左通道等级调整按钮
        left_big = get_ui_attr(self.ui, "pushButton_left_turnbig")
        safe_connect(self._logger, getattr(left_big, "clicked", None), self._on_left_grade_increase)
        left_small = get_ui_attr(self.ui, "pushButton_left_turnsmall")
        safe_connect(self._logger, getattr(left_small, "clicked", None), self._on_left_grade_decrease)

        # 左通道频率/方案选择
        left_freq = get_ui_attr(self.ui, "comboBox_left_freq")
        safe_connect(self._logger, getattr(left_freq, "valueChanged", None), self._on_left_freq_value_changed)
        safe_connect(self._logger, getattr(left_freq, "sliderReleased", None), self._on_left_freq_released)
        safe_connect(self._logger, getattr(left_freq, "currentIndexChanged", None), self._on_left_freq_changed)
        left_scheme = get_ui_attr(self.ui, "comboBox_left_scheme")
        safe_connect(self._logger, getattr(left_scheme, "currentIndexChanged", None), self._on_left_scheme_changed)

        self._init_left_circle_widget()
        self._hide_right_channel_widgets()
        self._update_freq_value_label()
        self._init_time_scrollbars()

    def _on_stim_leg_clicked(self, left: bool) -> None:
        self._switch_active_leg(left=left)

    def _switch_active_leg(self, left: bool, save_current: bool = True) -> None:
        target = "left" if left else "right"
        if save_current and target != self._active_leg_channel:
            self._save_current_params()
        self._set_leg_highlight(left_selected=left)
        self._apply_cached_params(channel=self._selected_leg_channel())

    def _selected_leg_channel(self) -> str:
        mode = self._patient_leg_display_mode()
        if mode == "right":
            return "right"
        if mode == "left":
            return "left"
        return self._active_leg_channel if self._active_leg_channel in ("left", "right") else "left"

    def _leg_text(self, channel: str) -> str:
        return "右腿" if channel == "right" else "左腿"

    def _hide_right_channel_widgets(self) -> None:
        # 单通道模式下隐藏右通道区域控件
        for name in (
            "widget_circle_level_right",
            "label_right_grade",
            "pushButton_right_turnsmall",
            "pushButton_right_turnbig",
            "comboBox_right_freq",
            "comboBox_right_scheme",
            "label_right_channel",
            "label_right_channel_2",
            "label_34",
            "label_50",
            "label_51",
            "label_49",
        ):
            widget = get_ui_attr(self.ui, name)
            safe_call(self._logger, getattr(widget, "setVisible", None), False)

    def _init_left_circle_widget(self) -> None:
        """在 widget_circle_level_left 中放入只读圆环，与 label_left_grade 联动，并裁剪为圆形区域。"""
        host = get_ui_attr(self.ui, "widget_circle_level_left")
        if host is None:
            return
        layout = host.layout()
        if layout is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
        self._left_circle_widget = CircleLevelWidget(host)
        self._left_circle_widget.set_level_range(0, 99)
        self._left_circle_widget.set_read_only(True)
        self._left_circle_widget.set_level(self._get_left_grade())
        layout.addWidget(self._left_circle_widget)

        host.installEventFilter(_CircleMaskResizeFilter(host))
        QTimer.singleShot(0, lambda: self._apply_circle_mask_to_host(host))

    def _apply_circle_mask_to_host(self, host) -> None:
        """将 host 裁剪为圆形显示与点击区域（以短边为直径居中）。"""
        w, h = host.width(), host.height()
        if w <= 0 or h <= 0:
            return
        d = min(w, h)
        x = (w - d) // 2
        y = (h - d) // 2
        region = QRegion(x, y, d, d, QRegion.Ellipse)
        host.setMask(region)

    def set_current_patient(self, patient: dict | None) -> None:
        """设置当前患者并恢复缓存参数（患者绑定）。"""
        self._current_patient_for_leg = patient
        self._current_patient_id = self._extract_patient_id(patient)
        if self.session_app:
            try:
                if self._current_patient_id:
                    self.session_app.set_current_patient(self._current_patient_id)
                else:
                    self.session_app.set_current_patient("")
            except Exception:
                self._logger.exception("设置当前患者失败")
        self.refresh_stim_leg_bar()
        self._apply_cached_params()

    def on_enter(self) -> None:
        """进入电刺激页：强制回到停止态。"""
        self._set_running_state(running=False)
        self.refresh_stim_leg_bar()
        self._apply_cached_params()

    def on_exit(self) -> None:
        """离开电刺激页：保存当前档位并停止。"""
        self._save_current_params()
        self._stop_treatment_safe()

    def reset_stimulus_grades(self) -> None:
        """清零单通道刺激强度（0级）并同步到硬件与 session。"""
        self._set_left_grade(0)
        self._send_left_channel_params(current_value=0)
        self._save_current_params()

    # ----------------- UI 状态管理 -----------------
    def _set_default_freq(self) -> None:
        """将频率拖条默认设置为 20ms。"""
        self._set_freq_value(self._FREQ_DEFAULT_MS)

    def _set_running_state(self, running: bool) -> None:
        self._test_running = bool(running)

        start_btn = get_ui_attr(self.ui, "pushButton_start_test")
        if start_btn is not None:
            safe_call(self._logger, getattr(start_btn, "setEnabled", None), self._hardware_online)
            safe_call(
                self._logger,
                getattr(start_btn, "setText", None),
                "停止测试" if self._test_running else "开始测试",
            )
            # 开始测试：背景 #789EFF、白色字体；停止测试：背景 #F48438、白色字体；保留倒角与 .ui 一致
            bg = "#F48438" if self._test_running else "#789EFF"
            safe_call(
                self._logger,
                getattr(start_btn, "setStyleSheet", None),
                f"QPushButton {{ background-color: {bg}; color: white; border-radius: 12.6px; }} "
                f"QPushButton:disabled {{ background-color: #707070; color: white; border-radius: 12.6px; }}",
            )

        # 单通道档位调节按钮：在线即可点，未开始测试时点击会弹提示
        for btn_name in (
            "pushButton_left_turnbig",
            "pushButton_left_turnsmall",
        ):
            button = get_ui_attr(self.ui, btn_name)
            safe_call(self._logger, getattr(button, "setEnabled", None), self._hardware_online)

    def set_hardware_online(self, is_online: bool) -> None:
        """根据下位机在线状态更新控件可用性"""
        self._hardware_online = bool(is_online)
        self._update_device_dependent_controls()

    def _update_device_dependent_controls(self) -> None:
        """更新依赖下位机在线状态的控件"""
        enabled = bool(self._hardware_online)

        if not enabled:
            # 离线：重置档位为 0，恢复默认方案/频率
            self._set_left_grade(0)
            self._set_combo_index("comboBox_left_scheme", self._default_params.get("left_scheme_idx", 0))
            self._set_freq_value(self._default_params.get("left_freq_idx", self._FREQ_DEFAULT_MS))

        # 方案/频率控件：离线时不可选
        for name in (
            "comboBox_left_freq",
            "comboBox_left_scheme",
            "comboBox_pulse_width",
            "horizontalScrollBar_time_stim",
            "horizontalScrollBar_time_rise",
            "horizontalScrollBar_time_down",
        ):
            combo = get_ui_attr(self.ui, name)
            safe_call(self._logger, getattr(combo, "setEnabled", None), enabled)
        self._set_time_aux_controls_enabled(enabled)

        # 档位增减按钮：在线即可点，未开始测试时点击会弹提示
        for btn_name in (
            "pushButton_left_turnbig",
            "pushButton_left_turnsmall",
        ):
            button = get_ui_attr(self.ui, btn_name)
            safe_call(self._logger, getattr(button, "setEnabled", None), enabled)

        # 开始/停止合一按钮：在线即可点，点击在开始/停止间切换
        if hasattr(self.ui, "pushButton_start_test"):
            safe_call(
                self._logger,
                getattr(self.ui.pushButton_start_test, "setEnabled", None),
                enabled,
            )


    # ----------------- 开始/停止测试（同一按钮切换）-----------------
    def _on_start_stop_test_clicked(self) -> None:
        """点击开始测试按钮：当前运行则停止，当前停止则开始。"""
        if self._test_running:
            self._on_stop_test_clicked()
        else:
            self._on_start_test_clicked()

    def _on_start_test_clicked(self) -> None:
        try:
            # 进入开始测试时：当前侧档位重置为 0
            self._set_left_grade(0)
            # 同步保存（当前患者）
            self._save_current_params()
            # 下发一次当前参数（保证下位机拿到 current=0）
            self._send_left_channel_params(current_value=0)

            if self.stim_app:
                self.stim_app.start_treatment_channel(self._selected_leg_channel())
        finally:
            self._set_running_state(running=True)

    def _on_stop_test_clicked(self) -> None:
        try:
            if self.stim_app:
                self.stim_app.stop_treatment_channel(self._selected_leg_channel())
        finally:
            self._set_running_state(running=False)

    def stop_safe(self) -> None:
        self._stop_treatment_safe()

    def _stop_treatment_safe(self) -> None:
        try:
            if self.stim_app:
                self.stim_app.stop_treatment_channel(self._selected_leg_channel())
        except Exception:
            self._logger.exception("停止治疗失败")

    # ----------------- 档位/参数下发 -----------------
    def _get_first_char(self, text: str) -> str:
        if not text:
            return ""
        first_char = text[0]
        if "\u4e00" <= first_char <= "\u9fff":
            return first_char
        if first_char.isalnum():
            return first_char
        return first_char

    def _get_left_grade(self) -> int:
        label = get_ui_attr(self.ui, "label_left_grade")
        if label is None:
            return 0
        text = label.text()
        try:
            grade_str = text.replace("级", "").strip()
            return int(grade_str)
        except (ValueError, AttributeError):
            return 0

    def _set_left_grade(self, grade: int) -> None:
        label = get_ui_attr(self.ui, "label_left_grade")
        if label is None:
            return
        grade = max(0, min(99, grade))
        safe_call(self._logger, getattr(label, "setText", None), f"{grade}级")
        if self._left_circle_widget is not None:
            self._left_circle_widget.set_level(grade)

    def _send_left_channel_params(self, current_value: int) -> None:
        if not self.stim_app:
            return
        channel = self._selected_leg_channel()
        scheme_idx = self._get_combo_index("comboBox_left_scheme") or 0
        scheme = 1 if scheme_idx <= 0 else 2
        frequency = self._get_freq_value()
        current = max(0, min(0x99, int(current_value)))
        try:
            self.stim_app.set_params(scheme=scheme, frequency=frequency, current=current, channel=channel)
        except Exception:
            self._logger.exception("下发%s通道参数失败", channel)

    # ----------------- UI 事件：频率/方案/按钮 -----------------
    def _on_left_freq_value_changed(self, value: int) -> None:
        self._update_freq_value_label(value)

    def _on_left_freq_released(self) -> None:
        current_grade = self._get_left_grade()
        self._send_left_channel_params(current_value=current_grade)
        self._save_current_params()

    def _on_left_freq_changed(self, index: int) -> None:
        self._update_freq_value_label()
        self._on_left_freq_released()

    def _on_left_scheme_changed(self, index: int) -> None:
        current_grade = self._get_left_grade()
        self._send_left_channel_params(current_value=current_grade)
        self._save_current_params()

    def _on_left_grade_increase(self) -> None:
        if not self._test_running:
            TipsDialog.show_tips(self.ui, "请先点击“开始测试”按钮")
            return
        current_grade = self._get_left_grade()
        new_grade = current_grade + 1
        self._set_left_grade(new_grade)
        self._send_left_channel_params(current_value=new_grade)
        self._save_current_params()

    def _on_left_grade_decrease(self) -> None:
        if not self._test_running:
            TipsDialog.show_tips(self.ui, "请先点击“开始测试”按钮")
            return
        current_grade = self._get_left_grade()
        new_grade = current_grade - 1
        self._set_left_grade(new_grade)
        self._send_left_channel_params(current_value=new_grade)
        self._save_current_params()

    # ----------------- 缓存：患者绑定 -----------------
    def _get_combo_index(self, name: str) -> int | None:
        combo = get_ui_attr(self.ui, name)
        if combo is None:
            return None
        try:
            return int(combo.currentIndex())
        except Exception:
            return None

    def _set_combo_index(self, name: str, idx: int | None) -> None:
        combo = get_ui_attr(self.ui, name)
        if idx is None or combo is None:
            return
        try:
            count = int(combo.count())
            if count <= 0:
                return
            idx = max(0, min(count - 1, int(idx)))
            old_block = combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(old_block)
        except Exception:
            self._logger.exception("设置下拉框索引失败: %s", name)

    def _get_freq_value(self) -> int:
        slider = get_ui_attr(self.ui, "comboBox_left_freq")
        if slider is None:
            return self._FREQ_DEFAULT_MS
        try:
            value_getter = getattr(slider, "value", None)
            if callable(value_getter):
                return self._normalize_freq_value(int(value_getter()))
            current_index_getter = getattr(slider, "currentIndex", None)
            if callable(current_index_getter):
                return self._normalize_freq_value(int(current_index_getter()))
        except Exception:
            self._logger.exception("读取频率值失败")
        return self._FREQ_DEFAULT_MS

    def _set_freq_value(self, value: int | None) -> None:
        slider = get_ui_attr(self.ui, "comboBox_left_freq")
        if slider is None:
            return
        freq = self._normalize_freq_value(value)
        try:
            if hasattr(slider, "setMinimum"):
                slider.setMinimum(self._FREQ_MIN_MS)
            if hasattr(slider, "setMaximum"):
                slider.setMaximum(self._FREQ_MAX_MS)
            old_block = slider.blockSignals(True)
            set_value = getattr(slider, "setValue", None)
            if callable(set_value):
                set_value(freq)
            else:
                set_index = getattr(slider, "setCurrentIndex", None)
                if callable(set_index):
                    set_index(freq)
            slider.blockSignals(old_block)
            self._update_freq_value_label(freq)
        except Exception:
            self._logger.exception("设置频率值失败")

    def _normalize_freq_value(self, value: int | None) -> int:
        if value is None:
            return self._FREQ_DEFAULT_MS
        return max(self._FREQ_MIN_MS, min(self._FREQ_MAX_MS, int(value)))

    def _update_freq_value_label(self, value: int | None = None) -> None:
        label = get_ui_attr(self.ui, "label_left_freq_value")
        if label is None:
            return
        freq = self._get_freq_value() if value is None else self._normalize_freq_value(value)
        safe_call(self._logger, getattr(label, "setText", None), f"{freq} ms")

    def _init_time_scrollbars(self) -> None:
        for name in (
            "horizontalScrollBar_time_stim",
            "horizontalScrollBar_time_rise",
            "horizontalScrollBar_time_down",
        ):
            scrollbar = get_ui_attr(self.ui, name)
            if scrollbar is None:
                continue
            try:
                scrollbar.setMinimum(self._TIME_MIN_TENTHS)
                scrollbar.setMaximum(self._TIME_MAX_TENTHS)
                scrollbar.setSingleStep(1)
                scrollbar.setPageStep(1)
                scrollbar.setValue(self._TIME_DEFAULT_TENTHS)
                scrollbar.setStyleSheet(self._time_scrollbar_style())
                safe_connect(
                    self._logger,
                    getattr(scrollbar, "valueChanged", None),
                    lambda value, n=name: self._on_time_scrollbar_changed(n, value),
                )
                self._ensure_time_scrollbar_aux_widgets(name)
                self._update_time_scrollbar_display(name, scrollbar.value())
            except Exception:
                self._logger.exception("初始化时间拖条失败: %s", name)

    def _time_scrollbar_style(self) -> str:
        return """
QScrollBar:horizontal {
    background: #EAF1FF;
    border: none;
    border-radius: 11px;
    height: 22px;
    margin: 0px;
}
QScrollBar::sub-page:horizontal {
    background: #AFC4FF;
    border-radius: 11px;
}
QScrollBar::add-page:horizontal {
    background: #EAF1FF;
    border-radius: 11px;
}
QScrollBar::handle:horizontal {
    background: #FFFFFF;
    border: 4px solid #7DA1FF;
    border-radius: 11px;
    min-width: 22px;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
}
"""

    def _ensure_time_scrollbar_aux_widgets(self, name: str) -> None:
        if name in self._time_scroll_widgets:
            return
        scrollbar = get_ui_attr(self.ui, name)
        parent = scrollbar.parent() if scrollbar is not None else None
        if scrollbar is None or parent is None:
            return

        tip = QLabel(parent)
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet(
            "QLabel { background: #789EFF; color: white; border-radius: 4px; padding: 2px 6px; }"
        )

        tick_labels: list[QLabel] = []
        for text in ("0.5s", "1s", "1.5s", "2s"):
            tick = QLabel(parent)
            tick.setText(text)
            tick.setAlignment(Qt.AlignCenter)
            tick.setStyleSheet("QLabel { color: #333333; font-size: 13px; }")
            tick_labels.append(tick)

        minus = QPushButton("-", parent)
        value_label = QLabel(parent)
        plus = QPushButton("+", parent)
        for button in (minus, plus):
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton { background: #F7F7F7; color: #789EFF; border: 1px solid #E5E5E5; "
                "font-size: 20px; } QPushButton:pressed { background: #EEF3FF; }"
            )
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(
            "QLabel { background: #F7F7F7; color: #789EFF; border-top: 1px solid #E5E5E5; "
            "border-bottom: 1px solid #E5E5E5; font-size: 18px; }"
        )
        safe_connect(self._logger, getattr(minus, "clicked", None), lambda _=False, n=name: self._step_time_scrollbar(n, -1))
        safe_connect(self._logger, getattr(plus, "clicked", None), lambda _=False, n=name: self._step_time_scrollbar(n, 1))

        self._time_scroll_widgets[name] = {
            "tip": tip,
            "ticks": tick_labels,
            "minus": minus,
            "value": value_label,
            "plus": plus,
        }
        self._layout_time_scrollbar_aux_widgets(name)

    def _layout_time_scrollbar_aux_widgets(self, name: str) -> None:
        scrollbar = get_ui_attr(self.ui, name)
        widgets = self._time_scroll_widgets.get(name)
        if scrollbar is None or not widgets:
            return
        geom = scrollbar.geometry()
        tick_y = geom.y() + geom.height() + 6
        tick_values = (5, 10, 15, 20)
        for tick, tick_value in zip(widgets["ticks"], tick_values):
            x = self._time_value_to_x(geom.x(), geom.width(), tick_value) - 24
            tick.setGeometry(x, tick_y, 48, 18)
            tick.show()

        panel_y = geom.y() + geom.height() + 36
        panel_x = geom.x() + max(0, (geom.width() - 210) // 2)
        widgets["minus"].setGeometry(panel_x, panel_y, 60, 34)
        widgets["value"].setGeometry(panel_x + 60, panel_y, 90, 34)
        widgets["plus"].setGeometry(panel_x + 150, panel_y, 60, 34)
        for key in ("minus", "value", "plus", "tip"):
            widgets[key].show()

    def _time_value_to_x(self, left: int, width: int, value: int) -> int:
        span = max(1, self._TIME_MAX_TENTHS - self._TIME_MIN_TENTHS)
        ratio = (self._normalize_time_tenths(value) - self._TIME_MIN_TENTHS) / span
        return int(left + ratio * width)

    def _on_time_scrollbar_changed(self, name: str, value: int) -> None:
        self._update_time_scrollbar_display(name, value)

    def _step_time_scrollbar(self, name: str, step: int) -> None:
        scrollbar = get_ui_attr(self.ui, name)
        if scrollbar is None:
            return
        scrollbar.setValue(self._normalize_time_tenths(int(scrollbar.value()) + int(step)))

    def _normalize_time_tenths(self, value: int | None) -> int:
        if value is None:
            return self._TIME_DEFAULT_TENTHS
        return max(self._TIME_MIN_TENTHS, min(self._TIME_MAX_TENTHS, int(value)))

    def _format_time_seconds(self, value: int) -> str:
        seconds = self._normalize_time_tenths(value) / 10
        return f"{seconds:g}s"

    def _update_time_scrollbar_display(self, name: str, value: int) -> None:
        scrollbar = get_ui_attr(self.ui, name)
        widgets = self._time_scroll_widgets.get(name)
        if scrollbar is None or not widgets:
            return
        value = self._normalize_time_tenths(value)
        text = self._format_time_seconds(value)
        widgets["value"].setText(text)
        widgets["tip"].setText(text)

        geom = scrollbar.geometry()
        tip_width = 58
        tip_x = self._time_value_to_x(geom.x(), geom.width(), value) - tip_width // 2
        tip_x = max(geom.x(), min(geom.x() + geom.width() - tip_width, tip_x))
        widgets["tip"].setGeometry(tip_x, geom.y() - 34, tip_width, 24)
        widgets["tip"].raise_()

    def _set_time_aux_controls_enabled(self, enabled: bool) -> None:
        for widgets in self._time_scroll_widgets.values():
            for key in ("minus", "plus"):
                widget = widgets.get(key)
                safe_call(self._logger, getattr(widget, "setEnabled", None), enabled)

    def _extract_patient_id(self, patient: dict | None) -> str | None:
        if not patient:
            return None
        return str(patient.get("PatientId") or patient.get("Name") or "")

    def _load_current_treat_params(self) -> Optional[PatientTreatParams]:
        pid = self._current_patient_id
        if not pid or not self.session_app:
            return None
        try:
            return self.session_app.load_treat_params(pid)
        except Exception:
            self._logger.exception("加载治疗参数失败: %s", pid)
            return None

    def _apply_cached_params(self, channel: Optional[str] = None) -> None:
        pid = self._current_patient_id
        if not pid:
            self._set_left_grade(0)
            return
        params = self._load_current_treat_params()

        if params is None:
            params = PatientTreatParams(
                patient_id=pid,
                left_grade=0,
                right_grade=0,
                left_scheme_idx=self._default_params.get("left_scheme_idx", 0),
                right_scheme_idx=self._default_params.get("left_scheme_idx", 0),
                left_freq_idx=self._default_params.get("left_freq_idx", 0),
                right_freq_idx=self._default_params.get("left_freq_idx", 0),
            )
            if self.session_app:
                try:
                    self.session_app.save_treat_params(params)
                except Exception:
                    self._logger.exception("初始化治疗参数失败: %s", pid)

        selected = channel or self._selected_leg_channel()
        if selected == "right":
            self._set_left_grade(getattr(params, "right_grade", 0))
            self._set_combo_index("comboBox_left_scheme", getattr(params, "right_scheme_idx", 0))
            self._set_freq_value(getattr(params, "right_freq_idx", self._FREQ_DEFAULT_MS))
            return
        self._set_left_grade(getattr(params, "left_grade", 0))
        self._set_combo_index("comboBox_left_scheme", getattr(params, "left_scheme_idx", 0))
        self._set_freq_value(getattr(params, "left_freq_idx", self._FREQ_DEFAULT_MS))

    def _save_current_params(self) -> None:
        pid = self._current_patient_id
        if not pid or not self.session_app:
            return
        try:
            params = self._load_current_treat_params()
            if params is None:
                params = PatientTreatParams(
                    patient_id=pid,
                    left_grade=0,
                    right_grade=0,
                    left_scheme_idx=self._default_params.get("left_scheme_idx", 0),
                    right_scheme_idx=self._default_params.get("left_scheme_idx", 0),
                    left_freq_idx=self._default_params.get("left_freq_idx", 0),
                    right_freq_idx=self._default_params.get("left_freq_idx", 0),
                )
            current_grade = self._get_left_grade()
            current_scheme_idx = self._get_combo_index("comboBox_left_scheme") or 0
            current_freq_idx = self._get_freq_value()
            if self._selected_leg_channel() == "right":
                left_grade = getattr(params, "left_grade", 0)
                left_scheme_idx = getattr(params, "left_scheme_idx", self._default_params.get("left_scheme_idx", 0))
                left_freq_idx = getattr(params, "left_freq_idx", self._default_params.get("left_freq_idx", 0))
                right_grade = current_grade
                right_scheme_idx = current_scheme_idx
                right_freq_idx = current_freq_idx
            else:
                left_grade = current_grade
                left_scheme_idx = current_scheme_idx
                left_freq_idx = current_freq_idx
                right_grade = getattr(params, "right_grade", 0)
                right_scheme_idx = getattr(params, "right_scheme_idx", self._default_params.get("left_scheme_idx", 0))
                right_freq_idx = getattr(params, "right_freq_idx", self._default_params.get("left_freq_idx", 0))
            self.session_app.save_treat_params(
                PatientTreatParams(
                    patient_id=pid,
                    left_grade=left_grade,
                    right_grade=right_grade,
                    left_scheme_idx=left_scheme_idx,
                    right_scheme_idx=right_scheme_idx,
                    left_freq_idx=left_freq_idx,
                    right_freq_idx=right_freq_idx,
                )
            )
        except Exception:
            self._logger.exception("保存治疗参数失败: %s", pid)

    # ----------------- 对外：用于上层导航判断 -----------------
    def ensure_stopped_before_next(self) -> bool:
        """若仍在运行，弹提示并返回 False。"""
        # 下位机离线：允许直接进入下一步（避免被运行态卡住）
        if not self._hardware_online:
            return True
        if not self._test_running:
            return True
        try:
            TipsDialog.show_tips(self.ui, "请先点击“停止测试”，停止后才能进入下一步")
        except Exception:
            self._logger.exception("弹出提示失败")
        return False


class _CircleMaskResizeFilter(QObject):
    """Resize 时重新为 host 设置圆形 mask。"""

    def __init__(self, host):
        super().__init__(host)
        self._host = host

    def eventFilter(self, obj, event) -> bool:
        if obj == self._host and event.type() == QEvent.Resize:
            w, h = self._host.width(), self._host.height()
            if w > 0 and h > 0:
                d = min(w, h)
                x, y = (w - d) // 2, (h - d) // 2
                self._host.setMask(QRegion(x, y, d, d, QRegion.Ellipse))
        return False

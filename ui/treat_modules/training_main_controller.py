from __future__ import annotations

import html
import logging
from typing import Callable, Optional

from application.patient_app import PatientApp
from application.session_app import SessionApp
from application.training_main_app import TrainingMainApp
from ui.widgets.bci_wave_widget import BCIWaveWidget
from ui.widgets.power_bar_widget import PowerBarWidget
from ui.core.utils import get_ui_attr, safe_call, safe_connect
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel

from ui.dialogs.tips_dialog import TipsDialog
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QFont
from PySide6.QtCore import QTimer, Qt, QObject, QEvent, QRect, QBuffer


class TrainingMainController:
    """
    训练模块主屏（tabWidget_2 index=2 / tab_5）。

    框架阶段：只负责 UI 交互 -> TrainingMainApp 的调用入口。

    需要负责显示脑电波形13个通道
    """

    def __init__(
        self,
        ui,
        patient_app: Optional[PatientApp] = None,
        session_app: Optional[SessionApp] = None,
        training_app: Optional[TrainingMainApp] = None,
        config_app=None,
        reaction_time_app=None,
        training_flow_app=None,
        on_countdown_finished: Optional[Callable[[], None]] = None,
        on_shut_down_return_home: Optional[Callable[[], None]] = None,
    ):
        self.ui = ui
        self.patient_app = patient_app
        self.session_app = session_app
        self.training_app = training_app
        self.config_app = config_app
        self.reaction_time_app = reaction_time_app
        self.training_flow_app = training_flow_app
        self._on_countdown_finished = on_countdown_finished
        self._on_shut_down_return_home = on_shut_down_return_home
        self._logger = logging.getLogger(__name__)
        self._current_patient_id: Optional[str] = None
        self._wave_widget: Optional[BCIWaveWidget] = None
        self._wave_label_panel: Optional[QWidget] = None
        self._wave_label_items: list[tuple[QLabel, QLabel]] = []
        self._wave_label_filter: Optional[_WaveLabelPanelFollower] = None
        self._wave_visible_rows_snapshot: int = 0
        self._power_widget: Optional[PowerBarWidget] = None
        self._reaction_sum = 0.0
        self._reaction_count = 0
        self._reaction_curve_points: list[float] = []
        self._reaction_time_points: list[tuple[int, Optional[float]]] = []  # (trial_index, reaction_time or None)
        self._reaction_time_missing_sec = 5.0  # 无记录试次在图中用 5s 表示
        self._last_session_id: Optional[int] = None
        self._countdown_timer = QTimer()
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_remaining = 0
        self._countdown_total = 0
        self._pretrain_full_completed = False  # decoder.Inform pretrain=pretrain_full_completed 后为 True
        self._has_sent_paradigm_shut_down = False  # 本 session 是否已发过 main.tigger paradigm.shut_down
        self._on_enter_session_id: Optional[int] = None  # 上次进入训练页时的 session_id，同一 session 内不重置预训练/结束状态
        self._init_wave_widget()
        self._init_power_widget()
        self._apply_countdown_emphasis_style()

    def bind_signals(self) -> None:
        start_stop_btn = get_ui_attr(self.ui, "pushButton_start_stop")
        if start_stop_btn:
            safe_connect(self._logger, getattr(start_stop_btn, "clicked", None), self._on_start_stop_clicked)
        shut_down_btn = get_ui_attr(self.ui, "pushButton_paradigm_shut_down")
        if shut_down_btn:
            safe_connect(self._logger, getattr(shut_down_btn, "clicked", None), self._on_paradigm_shut_down_clicked)

    def set_current_patient(self, patient_id: Optional[str]) -> None:
        self._current_patient_id = str(patient_id or "").strip() or None
        self._reaction_sum = 0.0
        self._reaction_count = 0
        self._reaction_curve_points = []
        self._reaction_time_points = []
        self._last_session_id = None
        if self.training_app:
            if self._current_patient_id:
                self.training_app.set_current_patient(self._current_patient_id)
            else:
                self.training_app.set_current_patient("")

    def on_enter(self) -> None:
        """进入训练页：同一 session 内不重置 _pretrain_full_completed / _has_sent_paradigm_shut_down。"""
        current_session_id = None
        if self.session_app:
            try:
                current_session_id = self.session_app.get_current_session_id()
            except Exception:
                pass
        if current_session_id != self._on_enter_session_id:
            self._on_enter_session_id = current_session_id
            self._pretrain_full_completed = False
            self._has_sent_paradigm_shut_down = False
        self._refresh_info_panel()

    def set_pretrain_full_completed(self) -> None:
        """收到 decoder.Inform pretrain=pretrain_full_completed 时调用（SSMVEP/MI 可暂停）。"""
        self._pretrain_full_completed = True

    def on_exit(self) -> None:
        self._reaction_sum = 0.0
        self._reaction_count = 0
        self._reaction_curve_points = []
        self._reaction_time_points = []
        self._last_session_id = None
        self.stop_countdown()
        return

    def _refresh_info_panel(self) -> None:
        label = get_ui_attr(self.ui, "label_PatientInfo")
        if label is None:
            return
        safe_call(self._logger, getattr(label, "setStyleSheet", None), "color: #939393;")
        safe_call(self._logger, label.setWordWrap, True)

        patient = None
        if self.patient_app and self._current_patient_id:
            try:
                patient = self.patient_app.get_patient_by_id(self._current_patient_id)
            except Exception:
                patient = None

        session_data = None
        if self.session_app:
            try:
                session_data = self.session_app.get_current_patient_treat_session()
            except Exception:
                session_data = None

        name = (patient or {}).get("Name", "") if patient else ""
        sex = (patient or {}).get("Sex", "") if patient else ""
        age = (patient or {}).get("Age", "") if patient else ""

        stim_a = (session_data or {}).get("StimChannelAIntensity", "")
        stim_b = (session_data or {}).get("StimChannelBIntensity", "")
        stim_scheme = (session_data or {}).get("StimSchemeAB", "")
        stim_freq = (session_data or {}).get("StimFreqAB", "")
        stim_position_raw = (session_data or {}).get("StimPosition", "")
        paradigm = (session_data or {}).get("Paradigm", "")

        # 刺激部位取值映射：up -> 上肢，down -> 下肢
        stim_position = {"up": "上肢", "down": "下肢"}.get(
            str(stim_position_raw).strip().lower(), stim_position_raw or ""
        )

        # 刺激方案：转 int 加一，显示为「方案2」；刺激频率：转 int 加一，单位「档」
        def _int_plus_one_unit(raw, unit: str, unit_before: bool = False) -> str:
            if raw is None or raw == "":
                return ""
            try:
                n = int(raw)
                val = str(n + 1)
                return f"{unit}{val}" if unit_before else f"{val}{unit}"
            except (TypeError, ValueError):
                return ""

        scheme_display = _int_plus_one_unit(stim_scheme, "方案", unit_before=True) or "方案1"
        freq_display = _int_plus_one_unit(stim_freq, "档") or "5档"

        def _fmt(v) -> str:
            return "" if v is None or v == "" else str(v)

        stim_a_display = _fmt(stim_a) if _fmt(stim_a) else "0"
        stim_b_display = _fmt(stim_b) if _fmt(stim_b) else "0"

        def _esc(s: str) -> str:
            return html.escape(s) if s else ""

        gap = "&nbsp;" * 10  # HTML 会合并普通空格，用 &nbsp; 保留同一行内间距
        line1 = f"姓名: {_esc(_fmt(name))}{gap}性别: {_esc(_fmt(sex))}{gap}年龄: {_esc(_fmt(age))}"
        rest = [
            f"范式: {_esc(_fmt(paradigm))}{gap}刺激部位: {_esc(_fmt(stim_position))}",
            f"A通道刺激强度: {_esc(stim_a_display)}{gap}B通道刺激强度: {_esc(stim_b_display)}",
            f"刺激方案: {_esc(scheme_display)}{gap}刺激频率: {_esc(freq_display)}",
        ]
        html_text = f'<div style="line-height: 2.0;"><b style="font-weight: bold;">{line1}</b><br/>' + "<br/>".join(rest) + "</div>"
        safe_call(self._logger, label.setTextFormat, Qt.TextFormat.RichText)
        safe_call(self._logger, label.setText, html_text)

    def _apply_countdown_emphasis_style(self) -> None:
        """训练时长标题与倒计时值使用醒目的红色加粗样式。"""
        style = "color: #E53935; font-weight: bold;"
        for name in ("label_43", "label_Countdown"):
            label = get_ui_attr(self.ui, name)
            if label is not None:
                safe_call(self._logger, getattr(label, "setStyleSheet", None), style)

    def _init_wave_widget(self) -> None:
        host = get_ui_attr(self.ui, "widget_BCIWave")
        if host is None:
            return
        layout = host.layout()
        if layout is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
        self._wave_widget = BCIWaveWidget(host)
        self._wave_widget.set_draw_labels(False)
        layout.addWidget(self._wave_widget)
        self._init_wave_label_panel(host)

    def _init_wave_label_panel(self, host: QWidget) -> None:
        parent = host.parentWidget()
        if parent is None or self._wave_widget is None:
            return
        if self._wave_label_panel is None:
            self._wave_label_panel = QWidget(parent)
            self._wave_label_panel.setObjectName("widget_BCIWaveLabels")
            self._wave_label_panel.setStyleSheet(
                "background-color: #ffffff; color: rgb(128, 146, 219); font-weight: bold;"
            )
            self._wave_label_panel.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._wave_label_panel.show()
        self._refresh_wave_label_panel()
        if self._wave_label_filter is None:
            self._wave_label_filter = _WaveLabelPanelFollower(host, self)
            host.installEventFilter(self._wave_label_filter)

    def _refresh_wave_label_panel(self) -> None:
        if self._wave_label_panel is None or self._wave_widget is None:
            return
        labels = self._wave_widget.get_visible_labels()
        n_rows = max(len(labels), 1)
        host = self._wave_widget.parentWidget()
        if host is None:
            return
        host_geo = host.geometry()
        panel_width = 50
        panel_x = max(host_geo.x() - panel_width - 8, 0)
        self._wave_label_panel.setGeometry(
            QRect(panel_x, host_geo.y(), panel_width, host_geo.height())
        )
        self._wave_label_panel.raise_()
        if len(self._wave_label_items) != len(labels):
            for text_item, dot_item in self._wave_label_items:
                text_item.deleteLater()
                dot_item.deleteLater()
            self._wave_label_items = []
            for label in labels:
                text_item = QLabel(self._wave_label_panel)
                text_item.setText(label)
                text_item.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                text_item.setStyleSheet("padding-left: 6px;")
                dot_item = QLabel(self._wave_label_panel)
                dot_item.setText("•" if label else "")
                dot_item.setAlignment(Qt.AlignCenter)
                self._wave_label_items.append((text_item, dot_item))
        row_h = max(int(host_geo.height() / n_rows), 1)
        for idx, (text_item, dot_item) in enumerate(self._wave_label_items):
            text_item.setGeometry(0, idx * row_h, panel_width - 14, row_h)
            dot_item.setGeometry(panel_width - 14, idx * row_h, 14, row_h)

    def _init_power_widget(self) -> None:
        host = get_ui_attr(self.ui, "widget_PowerBar")
        if host is None:
            return
        layout = host.layout()
        if layout is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
        self._power_widget = PowerBarWidget(host)
        layout.addWidget(self._power_widget)

    def set_wave_channel_labels_from_impedance(self, electrodes: list) -> None:
        """decoder.ImpedanceValue.params.electrode 与 EEG 通道顺序一致时，同步波形与侧栏标签。"""
        if not self._wave_widget or not isinstance(electrodes, list) or len(electrodes) == 0:
            return
        self._wave_widget.set_channel_labels(electrodes)
        self._wave_visible_rows_snapshot = len(self._wave_widget.get_visible_labels())
        self._refresh_wave_label_panel()

    def on_eeg_frame(self, frame: dict) -> None:
        if not self._wave_widget:
            return
        eeg_data = frame.get("eeg_data")
        timestamp = frame.get("timestamp")
        vis_rows = self._wave_widget.count_visible_eeg_rows(eeg_data)
        self._wave_widget.update_eeg(eeg_data, timestamp=timestamp)
        if vis_rows != self._wave_visible_rows_snapshot:
            self._wave_visible_rows_snapshot = vis_rows
            self._refresh_wave_label_panel()
        if self._power_widget:
            power_data = frame.get("power_data") or []
            self._power_widget.update_power(power_data)

    def on_intent_result(self, payload: dict) -> None:
        trial_index = payload.get("trial_index")
        complete_rate = payload.get("t_complete_r")
        reaction_time = payload.get("reaction_time")

        label_trial = get_ui_attr(self.ui, "label_trial")
        safe_call(self._logger, getattr(label_trial, "setText", None), str(trial_index) if trial_index is not None else "")
        label_complete = get_ui_attr(self.ui, "label_complete_rate")
        safe_call(self._logger, getattr(label_complete, "setText", None), str(complete_rate) if complete_rate is not None else "")
        label_reaction = get_ui_attr(self.ui, "label_reaction_rate")
        safe_call(self._logger, getattr(label_reaction, "setText", None), str(reaction_time) if reaction_time is not None else "")

        avg_label = get_ui_attr(self.ui, "label_reaction_rate_aver")
        try:
            session_id = None
            if self.session_app:
                session_id = self.session_app.get_current_session_id()
            if session_id != self._last_session_id:
                self._last_session_id = session_id
                self._reaction_sum = 0.0
                self._reaction_count = 0
                self._reaction_curve_points = []
                self._reaction_time_points = []
            trial_idx = int(trial_index) if trial_index is not None else (len(self._reaction_time_points) + 1)
            self._reaction_time_points.append((trial_idx, float(reaction_time) if reaction_time is not None else None))
            if reaction_time is not None:
                self._reaction_sum += float(reaction_time)
                self._reaction_count += 1
                avg_value = self._reaction_sum / max(self._reaction_count, 1)
                safe_call(self._logger, getattr(avg_label, "setText", None), f"{avg_value:.3f}")
                if self.session_app:
                    self.session_app.update_average_reaction_time(avg_value)
                    curve_path = self._save_average_reaction_curve(avg_value, session_id)
                    if curve_path:
                        self.session_app.update_average_reaction_time_curve(curve_path)
            curve_path = self._save_reaction_time_curve(session_id)
            if curve_path and self.session_app:
                self.session_app.update_reaction_time_curve(curve_path)
        except Exception:
            pass

    def start_countdown(self) -> None:
        if self._countdown_timer.isActive():
            return
        # 暂停状态下恢复：沿用当前剩余时间
        if self._countdown_remaining > 0 and self._countdown_total > 0:
            self._update_countdown_label()
            self._countdown_timer.start(1000)
            return
        minutes = self._load_countdown_minutes()
        total_seconds = int(float(minutes or 0) * 60)
        if total_seconds <= 0:
            return
        self._countdown_total = total_seconds
        self._countdown_remaining = total_seconds
        self._update_countdown_label()
        self._countdown_timer.start(1000)

    def pause_countdown(self) -> None:
        """暂停倒计时（保留剩余时间，收到 paradigm.start_decoding 后再继续）。"""
        if self._countdown_timer.isActive():
            self._countdown_timer.stop()
        # 不清零 _countdown_remaining / _countdown_total，便于恢复

    def stop_countdown(self) -> None:
        if self._countdown_timer.isActive():
            self._countdown_timer.stop()
        self._countdown_remaining = 0
        self._countdown_total = 0
        self._reset_trial_and_countdown_labels()

    def _reset_trial_and_countdown_labels(self) -> None:
        """收到 main.stop_session 时重置：label_trial / complete_rate / reaction_rate / reaction_rate_aver / Countdown。"""
        empty = ""
        for name in ("label_trial", "label_complete_rate", "label_reaction_rate", "label_reaction_rate_aver", "label_Countdown"):
            label = get_ui_attr(self.ui, name)
            safe_call(self._logger, getattr(label, "setText", None), empty)

    def _tick_countdown(self) -> None:
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self._send_stop_session_trigger()
            self._has_sent_paradigm_shut_down = True  # 倒计时完成已发 paradigm.shut_down，后续点结束不提示
            self._set_start_stop_to_start_state()
            self._show_countdown_finished_dialog()
            return
        self._countdown_remaining -= 1
        self._update_countdown_label()

    def _set_start_stop_to_start_state(self) -> None:
        """将开始/暂停按钮设为「开始」状态（倒计时完成或停止时）。"""
        start_stop_btn = get_ui_attr(self.ui, "pushButton_start_stop")
        if start_stop_btn:
            start_stop_btn.setStyleSheet("border-image: url(:/treat/pic/treat_start.png); color: #ffffff;")
            start_stop_btn.setText("          开始")

    def _show_countdown_finished_dialog(self) -> None:
        """倒计时结束时弹窗（tips.ui）：本次训练结束，是否返回主页面。确定：返回主页面，否：留在当前页。"""
        parent = self.ui.window() if self.ui else None
        if TipsDialog.show_confirm(parent, "本次训练结束，是否返回主页面？") and self._on_countdown_finished is not None:
            try:
                self._on_countdown_finished()
            except Exception:
                self._logger.exception("执行返回主页面回调失败")

    def _update_countdown_label(self) -> None:
        label = get_ui_attr(self.ui, "label_Countdown")
        if label is None:
            return
        minutes = max(self._countdown_remaining, 0) // 60
        seconds = max(self._countdown_remaining, 0) % 60
        safe_call(self._logger, getattr(label, "setText", None), f"{minutes:02d}:{seconds:02d}")

    def is_paused_state(self) -> bool:
        """
        判断训练是否处于暂停/未开始状态。
        - 计时器仍在运行视为未暂停
        - 按钮文本含有“暂停”视为正在运行（需要先暂停）
        """
        if self._countdown_timer.isActive():
            return False
        start_stop_btn = get_ui_attr(self.ui, "pushButton_start_stop")
        if start_stop_btn:
            text = start_stop_btn.text() or ""
            if "暂停" in text:
                return False
        return True

    def _on_start_stop_clicked(self) -> None:
        """开始/暂停按钮直接控制倒计时：点击开始 -> 开始计时；点击暂停 -> 暂停计时。不再依赖 paradigm.start_decoding / paradigm.Stage。"""
        start_stop_btn = get_ui_attr(self.ui, "pushButton_start_stop")
        if not start_stop_btn:
            return
        is_paused = "暂停" in (start_stop_btn.text() or "")
        if is_paused:
            if self.training_flow_app:
                ok, message = self.training_flow_app.check_pause_allowed(self._pretrain_full_completed)
                if not ok:
                    TipsDialog.show_tips(self.ui, message or "预训练未完成无法暂停")
                    return
            self.pause_countdown()
            start_stop_btn.setStyleSheet("border-image: url(:/treat/pic/treat_start.png); color: #ffffff;")
            start_stop_btn.setText("          开始")
            if self.training_flow_app:
                self.training_flow_app.notify_pause()
        else:
            start_stop_btn.setStyleSheet("border-image: url(:/treat/pic/treat_pause.png); color: #ffffff;")
            start_stop_btn.setText("          暂停")
            self.start_countdown()
            if self.training_flow_app:
                self.training_flow_app.notify_start()

    def _on_paradigm_shut_down_clicked(self) -> None:
        """点击结束按钮：本 session 未发过 paradigm.shut_down 则确认后发送并返回；已发过则直接返回主页面。退出前将开始/暂停恢复为开始状态。"""
        if self._has_sent_paradigm_shut_down:
            self._set_start_stop_to_start_state()
            if callable(self._on_shut_down_return_home):
                self._on_shut_down_return_home()
            return
        if not TipsDialog.show_confirm(self.ui.window() if self.ui else None, "本次训练未完成确定退出吗"):
            return
        if self.training_flow_app:
            self.training_flow_app.notify_shut_down()
        self._has_sent_paradigm_shut_down = True
        self._set_start_stop_to_start_state()
        if callable(self._on_shut_down_return_home):
            self._on_shut_down_return_home()

    def _send_stop_session_trigger(self) -> None:
        if self.training_flow_app:
            self.training_flow_app.notify_stop_and_shutdown()

    def _load_countdown_minutes(self) -> float:
        if not self.config_app:
            return 0.0
        try:
            value = self.config_app.get("Countdown_time_minutes", 0)
            return float(value or 0)
        except Exception:
            return 0.0

    def _save_reaction_time_curve(self, session_id: Optional[int]) -> str:
        """按试次序号画反应时间图：横坐标=试次 1..最后一试次，纵坐标=0-5s，无记录的试次用 5s 表示。"""
        if session_id is None or not self._reaction_time_points:
            return ""
        max_trial = max(t for t, _ in self._reaction_time_points)
        if max_trial <= 0:
            return ""
        record_map = {t: rt for t, rt in self._reaction_time_points}
        values = []
        for t in range(1, max_trial + 1):
            v = record_map.get(t)
            values.append(self._reaction_time_missing_sec if v is None else v)

        width, height = 600, 300
        margin_left = 42
        margin_right = 25
        margin_top = 25
        margin_bottom = 38
        plot_left = margin_left
        plot_right = width - margin_right
        plot_top = margin_top
        plot_bottom = height - margin_bottom
        plot_w = plot_right - plot_left
        plot_h = plot_bottom - plot_top

        y_min, y_max = 0.0, 7.0
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(QColor(255, 255, 255))
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            font = QFont()
            font.setPointSize(9)
            painter.setFont(font)
            axis_pen = QPen(QColor(120, 120, 120))
            axis_pen.setWidth(1)
            painter.setPen(axis_pen)
            painter.drawLine(plot_left, plot_bottom, plot_right, plot_bottom)
            painter.drawLine(plot_left, plot_top, plot_left, plot_bottom)

            # 纵坐标刻度与标签 0-7
            painter.setPen(QColor(80, 80, 80))
            for i in range(8):
                y_val = i
                y_pos = plot_bottom - (y_val - y_min) / (y_max - y_min) * plot_h
                painter.drawLine(int(plot_left), int(y_pos), int(plot_left) - 5, int(y_pos))
                label_rect = QRect(0, int(y_pos) - 10, margin_left - 8, 20)
                painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, str(y_val))

            # 横坐标刻度与标签（试次 1 .. max_trial）
            n = len(values)
            x_step = plot_w / max(n - 1, 1)
            for idx in range(n):
                trial_num = idx + 1
                x_pos = plot_left + idx * x_step
                painter.drawLine(int(x_pos), int(plot_bottom), int(x_pos), int(plot_bottom) + 5)
                label_rect = QRect(int(x_pos) - 12, int(plot_bottom) + 2, 24, 22)
                painter.drawText(label_rect, Qt.AlignCenter, str(trial_num))

            # 曲线与点（纵坐标固定 0-5）
            n = len(values)
            x_step = plot_w / max(n - 1, 1)
            _h = plot_bottom - plot_top
            line_pen = QPen(QColor(34, 139, 34))
            line_pen.setWidth(2)
            painter.setPen(line_pen)
            prev_x = plot_left
            prev_y = plot_bottom - (values[0] - y_min) / (y_max - y_min) * _h
            for idx in range(1, n):
                x = plot_left + idx * x_step
                y = plot_bottom - (values[idx] - y_min) / (y_max - y_min) * _h
                painter.drawLine(int(prev_x), int(prev_y), int(x), int(y))
                prev_x, prev_y = x, y

            dot_pen = QPen(QColor(255, 140, 0))
            dot_pen.setWidth(6)
            painter.setPen(dot_pen)
            for idx, val in enumerate(values):
                x = plot_left + idx * x_step
                y = plot_bottom - (val - y_min) / (y_max - y_min) * _h
                painter.drawPoint(int(x), int(y))
        finally:
            painter.end()

        image_bytes = self._image_to_png_bytes(image)
        if not image_bytes or not self.reaction_time_app:
            return ""
        saved = self.reaction_time_app.save_curve_bytes(session_id, image_bytes)
        return saved or ""

    def _save_average_reaction_curve(self, avg_value: float, session_id: Optional[int]) -> str:
        if session_id is None:
            return ""
        self._reaction_curve_points.append(float(avg_value))
        width, height = 600, 300
        margin = 30
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(QColor(255, 255, 255))
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            axis_pen = QPen(QColor(120, 120, 120))
            axis_pen.setWidth(1)
            painter.setPen(axis_pen)
            painter.drawLine(margin, height - margin, width - margin, height - margin)
            painter.drawLine(margin, margin, margin, height - margin)

            if self._reaction_curve_points:
                values = self._reaction_curve_points
                min_val = min(values)
                max_val = max(values)
                if min_val == max_val:
                    min_val -= 1.0
                    max_val += 1.0
                x_step = (width - 2 * margin) / max(len(values) - 1, 1)
                line_pen = QPen(QColor(30, 144, 255))
                line_pen.setWidth(2)
                painter.setPen(line_pen)
                prev_x = margin
                prev_y = self._map_value_to_y(values[0], min_val, max_val, height, margin)
                for idx, val in enumerate(values[1:], start=1):
                    x = margin + idx * x_step
                    y = self._map_value_to_y(val, min_val, max_val, height, margin)
                    painter.drawLine(int(prev_x), int(prev_y), int(x), int(y))
                    prev_x, prev_y = x, y

                dot_pen = QPen(QColor(255, 99, 71))
                dot_pen.setWidth(6)
                painter.setPen(dot_pen)
                for idx, val in enumerate(values):
                    x = margin + idx * x_step
                    y = self._map_value_to_y(val, min_val, max_val, height, margin)
                    painter.drawPoint(int(x), int(y))
        finally:
            painter.end()

        image_bytes = self._image_to_png_bytes(image)
        if not image_bytes or not self.reaction_time_app:
            return ""
        saved = self.reaction_time_app.save_curve_bytes(session_id, image_bytes)
        return saved or ""

    @staticmethod
    def _map_value_to_y(value: float, min_val: float, max_val: float, height: int, margin: int) -> float:
        usable_height = height - 2 * margin
        if max_val <= min_val:
            return height - margin
        ratio = (value - min_val) / (max_val - min_val)
        return height - margin - ratio * usable_height

    @staticmethod
    def _image_to_png_bytes(image: QImage) -> bytes:
        buffer = QBuffer()
        if not buffer.open(QBuffer.WriteOnly):
            return b""
        try:
            ok = image.save(buffer, "PNG")
            if not ok:
                return b""
            return bytes(buffer.data())
        finally:
            buffer.close()


class _WaveLabelPanelFollower(QObject):
    def __init__(self, host: QWidget, controller: TrainingMainController):
        super().__init__(host)
        self._host = host
        self._controller = controller

    def eventFilter(self, obj, event):
        if obj is self._host and event.type() in (QEvent.Resize, QEvent.Move):
            self._controller._refresh_wave_label_panel()
        return super().eventFilter(obj, event)

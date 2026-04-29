from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QMessageBox, QVBoxLayout

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

    def __init__(self, ui, session_app: Optional[SessionApp] = None, stim_app: Optional[StimTestApp] = None):
        self.ui = ui
        self.session_app = session_app
        self.stim_app = stim_app
        self._logger = logging.getLogger(__name__)

        # 控件联动保护：避免左右下拉框互相设置时触发递归回调
        self._is_syncing_scheme_freq = False

        # True=开始状态（stop可用/start不可用/next不可用）；False=停止状态（start可用/stop不可用/next可用）
        self._test_running = False
        # 设备在线状态（影响控件可用性）
        self._hardware_online = True

        # 频率默认第五档（index=4）。这里在绑定信号前设置，避免触发下发指令。
        self._set_default_freq_to_fifth()

        # 记录 UI 初始默认的方案/频率索引（用于患者第一次进入时初始化）
        self._default_params = {
            "left_scheme_idx": self._get_combo_index("comboBox_left_scheme") or 0,
            "right_scheme_idx": self._get_combo_index("comboBox_right_scheme") or 0,
            "left_freq_idx": self._get_combo_index("comboBox_left_freq") or 0,
            "right_freq_idx": self._get_combo_index("comboBox_right_freq") or 0,
        }

        self._current_patient_id: Optional[str] = None
        self._left_circle_widget: Optional[CircleLevelWidget] = None
        self._right_circle_widget: Optional[CircleLevelWidget] = None

    @property
    def is_test_running(self) -> bool:
        return bool(self._test_running)

    def bind_signals(self) -> None:
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
        safe_connect(self._logger, getattr(left_freq, "currentIndexChanged", None), self._on_left_freq_changed)
        left_scheme = get_ui_attr(self.ui, "comboBox_left_scheme")
        safe_connect(self._logger, getattr(left_scheme, "currentIndexChanged", None), self._on_left_scheme_changed)

        # 右通道等级调整按钮
        right_big = get_ui_attr(self.ui, "pushButton_right_turnbig")
        safe_connect(self._logger, getattr(right_big, "clicked", None), self._on_right_grade_increase)
        right_small = get_ui_attr(self.ui, "pushButton_right_turnsmall")
        safe_connect(self._logger, getattr(right_small, "clicked", None), self._on_right_grade_decrease)

        # 右通道频率/方案选择
        right_freq = get_ui_attr(self.ui, "comboBox_right_freq")
        safe_connect(self._logger, getattr(right_freq, "currentIndexChanged", None), self._on_right_freq_changed)
        right_scheme = get_ui_attr(self.ui, "comboBox_right_scheme")
        safe_connect(self._logger, getattr(right_scheme, "currentIndexChanged", None), self._on_right_scheme_changed)

        self._init_left_circle_widget()
        self._init_right_circle_widget()

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

    def _init_right_circle_widget(self) -> None:
        """在 widget_circle_level_right 中放入只读圆环，与 label_right_grade 联动，并裁剪为圆形区域。"""
        host = get_ui_attr(self.ui, "widget_circle_level_right")
        if host is None:
            return
        layout = host.layout()
        if layout is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
        self._right_circle_widget = CircleLevelWidget(host)
        self._right_circle_widget.set_level_range(0, 99)
        self._right_circle_widget.set_read_only(True)
        self._right_circle_widget.set_level(self._get_right_grade())
        layout.addWidget(self._right_circle_widget)

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
        self._current_patient_id = self._extract_patient_id(patient)
        if self.session_app:
            try:
                if self._current_patient_id:
                    self.session_app.set_current_patient(self._current_patient_id)
                else:
                    self.session_app.set_current_patient("")
            except Exception:
                self._logger.exception("设置当前患者失败")
        self._apply_cached_params()

    def on_enter(self) -> None:
        """进入电刺激页：强制回到停止态。"""
        self._apply_cached_params()
        self._set_running_state(running=False)

    def on_exit(self) -> None:
        """离开电刺激页：保存当前档位并停止。"""
        self._save_current_params()
        self._stop_treatment_safe()

    def reset_stimulus_grades(self) -> None:
        """清零左右刺激强度（0级）并同步到硬件与 session。从主页面进入新 session 时调用。"""
        self._set_left_grade(0)
        self._set_right_grade(0)
        self._send_left_channel_params(current_value=0)
        self._send_right_channel_params(current_value=0)
        self._save_current_params()

    # ----------------- UI 状态管理 -----------------
    def _set_default_freq_to_fifth(self) -> None:
        """将左右频率下拉框默认设置为第五档（index=4）"""
        for name in ("comboBox_left_freq", "comboBox_right_freq"):
            combo = get_ui_attr(self.ui, name)
            if combo is None:
                continue
            try:
                if int(combo.count()) >= 5:
                    old_block = combo.blockSignals(True)
                    combo.setCurrentIndex(4)
                    combo.blockSignals(old_block)
            except Exception:
                self._logger.exception("设置默认频率失败: %s", name)

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

        # 左右通道档位调节按钮：在线即可点，未开始测试时点击会弹提示
        for btn_name in (
            "pushButton_left_turnbig",
            "pushButton_left_turnsmall",
            "pushButton_right_turnbig",
            "pushButton_right_turnsmall",
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
            # 离线：重置档位为 0，恢复默认下拉框
            self._set_left_grade(0)
            self._set_right_grade(0)
            self._set_combo_index("comboBox_left_scheme", self._default_params.get("left_scheme_idx", 0))
            self._set_combo_index("comboBox_right_scheme", self._default_params.get("right_scheme_idx", 0))
            self._set_combo_index("comboBox_left_freq", self._default_params.get("left_freq_idx", 0))
            self._set_combo_index("comboBox_right_freq", self._default_params.get("right_freq_idx", 0))

        # 方案/频率下拉框：离线时不可选
        for name in (
            "comboBox_left_freq",
            "comboBox_left_scheme",
            "comboBox_right_freq",
            "comboBox_right_scheme",
        ):
            combo = get_ui_attr(self.ui, name)
            safe_call(self._logger, getattr(combo, "setEnabled", None), enabled)

        # 档位增减按钮：在线即可点，未开始测试时点击会弹提示
        for btn_name in (
            "pushButton_left_turnbig",
            "pushButton_left_turnsmall",
            "pushButton_right_turnbig",
            "pushButton_right_turnsmall",
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
            # 进入开始测试时：左右通道档位重置为 0
            self._set_left_grade(0)
            self._set_right_grade(0)
            # 同步保存（当前患者）
            self._save_current_params()
            # 下发一次当前参数（保证下位机拿到 current=0）
            self._send_left_channel_params(current_value=0)
            self._send_right_channel_params(current_value=0)

            if self.stim_app:
                self.stim_app.start_dual()
        finally:
            self._set_running_state(running=True)

    def _on_stop_test_clicked(self) -> None:
        try:
            if self.stim_app:
                self.stim_app.stop_dual()
        finally:
            self._set_running_state(running=False)

    def stop_safe(self) -> None:
        self._stop_treatment_safe()

    def _stop_treatment_safe(self) -> None:
        try:
            if self.stim_app:
                self.stim_app.stop_dual()
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

    def _get_right_grade(self) -> int:
        label = get_ui_attr(self.ui, "label_right_grade")
        if label is None:
            return 0
        text = label.text()
        try:
            grade_str = text.replace("级", "").strip()
            return int(grade_str)
        except (ValueError, AttributeError):
            return 0

    def _set_right_grade(self, grade: int) -> None:
        label = get_ui_attr(self.ui, "label_right_grade")
        if label is None:
            return
        grade = max(0, min(99, grade))
        safe_call(self._logger, getattr(label, "setText", None), f"{grade}级")
        if self._right_circle_widget is not None:
            self._right_circle_widget.set_level(grade)

    def _send_left_channel_params(self, current_value: int) -> None:
        if not self.stim_app:
            return
        scheme_idx = self._get_combo_index("comboBox_left_scheme") or 0
        scheme = 1 if scheme_idx <= 0 else 2
        freq_idx = self._get_combo_index("comboBox_left_freq") or 0
        frequency = int(freq_idx)
        current = max(0, min(0x99, int(current_value)))
        try:
            self.stim_app.set_params(scheme=scheme, frequency=frequency, current=current, channel="left")
        except Exception:
            self._logger.exception("下发左通道参数失败")

    def _send_right_channel_params(self, current_value: int) -> None:
        if not self.stim_app:
            return
        scheme_idx = self._get_combo_index("comboBox_right_scheme") or 0
        scheme = 1 if scheme_idx <= 0 else 2
        freq_idx = self._get_combo_index("comboBox_right_freq") or 0
        frequency = int(freq_idx)
        current = max(0, min(0x99, int(current_value)))
        try:
            self.stim_app.set_params(scheme=scheme, frequency=frequency, current=current, channel="right")
        except Exception:
            self._logger.exception("下发右通道参数失败")

    # ----------------- UI 事件：下拉框/按钮 -----------------
    def _on_left_freq_changed(self, index: int) -> None:
        if not self._is_syncing_scheme_freq:
            self._is_syncing_scheme_freq = True
            try:
                self._set_combo_index("comboBox_right_freq", index)
            finally:
                self._is_syncing_scheme_freq = False
        current_grade = self._get_left_grade()
        self._send_left_channel_params(current_value=current_grade)
        self._save_current_params()

    def _on_left_scheme_changed(self, index: int) -> None:
        if not self._is_syncing_scheme_freq:
            self._is_syncing_scheme_freq = True
            try:
                self._set_combo_index("comboBox_right_scheme", index)
            finally:
                self._is_syncing_scheme_freq = False
        current_grade = self._get_left_grade()
        self._send_left_channel_params(current_value=current_grade)
        self._save_current_params()

    def _on_right_freq_changed(self, index: int) -> None:
        if not self._is_syncing_scheme_freq:
            self._is_syncing_scheme_freq = True
            try:
                self._set_combo_index("comboBox_left_freq", index)
            finally:
                self._is_syncing_scheme_freq = False
        current_grade = self._get_right_grade()
        self._send_right_channel_params(current_value=current_grade)
        self._save_current_params()

    def _on_right_scheme_changed(self, index: int) -> None:
        if not self._is_syncing_scheme_freq:
            self._is_syncing_scheme_freq = True
            try:
                self._set_combo_index("comboBox_left_scheme", index)
            finally:
                self._is_syncing_scheme_freq = False
        current_grade = self._get_right_grade()
        self._send_right_channel_params(current_value=current_grade)
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

    def _on_right_grade_increase(self) -> None:
        if not self._test_running:
            TipsDialog.show_tips(self.ui, "请先点击“开始测试”按钮")
            return
        current_grade = self._get_right_grade()
        new_grade = current_grade + 1
        self._set_right_grade(new_grade)
        self._send_right_channel_params(current_value=new_grade)
        self._save_current_params()

    def _on_right_grade_decrease(self) -> None:
        if not self._test_running:
            TipsDialog.show_tips(self.ui, "请先点击“开始测试”按钮")
            return
        current_grade = self._get_right_grade()
        new_grade = current_grade - 1
        self._set_right_grade(new_grade)
        self._send_right_channel_params(current_value=new_grade)
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

    def _extract_patient_id(self, patient: dict | None) -> str | None:
        if not patient:
            return None
        return str(patient.get("PatientId") or patient.get("Name") or "")

    def _apply_cached_params(self) -> None:
        pid = self._current_patient_id
        if not pid:
            self._set_left_grade(0)
            self._set_right_grade(0)
            return
        params = None
        if self.session_app:
            try:
                params = self.session_app.load_treat_params(pid)
            except Exception:
                self._logger.exception("加载治疗参数失败: %s", pid)
                params = None

        if params is None:
            params = PatientTreatParams(
                patient_id=pid,
                left_grade=0,
                right_grade=0,
                left_scheme_idx=self._default_params.get("left_scheme_idx", 0),
                right_scheme_idx=self._default_params.get("right_scheme_idx", 0),
                left_freq_idx=self._default_params.get("left_freq_idx", 0),
                right_freq_idx=self._default_params.get("right_freq_idx", 0),
            )
            if self.session_app:
                try:
                    self.session_app.save_treat_params(params)
                except Exception:
                    self._logger.exception("初始化治疗参数失败: %s", pid)

        self._set_left_grade(getattr(params, "left_grade", 0))
        self._set_right_grade(getattr(params, "right_grade", 0))
        self._set_combo_index("comboBox_left_scheme", getattr(params, "left_scheme_idx", 0))
        self._set_combo_index("comboBox_right_scheme", getattr(params, "right_scheme_idx", 0))
        self._set_combo_index("comboBox_left_freq", getattr(params, "left_freq_idx", 0))
        self._set_combo_index("comboBox_right_freq", getattr(params, "right_freq_idx", 0))

    def _save_current_params(self) -> None:
        pid = self._current_patient_id
        if not pid or not self.session_app:
            return
        try:
            self.session_app.save_treat_params(
                PatientTreatParams(
                    patient_id=pid,
                    left_grade=self._get_left_grade(),
                    right_grade=self._get_right_grade(),
                    left_scheme_idx=self._get_combo_index("comboBox_left_scheme") or 0,
                    right_scheme_idx=self._get_combo_index("comboBox_right_scheme") or 0,
                    left_freq_idx=self._get_combo_index("comboBox_left_freq") or 0,
                    right_freq_idx=self._get_combo_index("comboBox_right_freq") or 0,
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

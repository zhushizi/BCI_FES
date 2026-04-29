from __future__ import annotations

import logging
from typing import Optional

from application.impedance_test_app import ImpedanceTestApp
from application.patient_app import PatientApp
from PySide6.QtWidgets import QLabel
from ui.core.utils import get_ui_attr, safe_call, safe_connect


class ImpedanceTestController:
    """
    脑阻抗测试模块（tabWidget_2 index=1 / tab_4）。
    """

    def __init__(self, ui, patient_app: Optional[PatientApp] = None, impedance_app: Optional[ImpedanceTestApp] = None):
        self.ui = ui
        self.patient_app = patient_app
        self.impedance_app = impedance_app
        self._logger = logging.getLogger(__name__)
        self._current_patient_id: Optional[str] = None
        self._last_impedance: dict[str, float] = {}
        self._checksafety_checked = False
        self._electrode_label_map: dict[str, QLabel] = {}

    def bind_signals(self) -> None:
        # 安全确认：选中后才允许开始评估
        radio = get_ui_attr(self.ui, "radioButton_checksafe")
        safe_connect(self._logger, getattr(radio, "toggled", None), self._on_checksafe_toggled)
        if radio is not None:
            self._apply_checksafe_style(False)

    def set_current_patient(self, patient_id: Optional[str]) -> None:
        self._current_patient_id = str(patient_id or "").strip() or None

    def on_enter(self) -> None:
        """进入阻抗页（占位）。"""
        self._sync_checksafe_state()
        # 进入页时，根据安全确认状态决定按钮可用性
        self._set_start_evaluate_enabled(True)
        self._open_impedance_mode()
        return

    def on_exit(self) -> None:
        """离开阻抗页（占位）。"""
        return

    # ---------- 阻抗检测 ----------
    def _open_impedance_mode(self) -> None:
        if self.impedance_app:
            safe_call(self._logger, self.impedance_app.start, self._current_patient_id)

    def stop_impedance(self) -> None:
        if self.impedance_app:
            safe_call(self._logger, self.impedance_app.stop)

    def apply_impedance_values(self, params: dict) -> None:
        """
        处理 decoder.ImpedanceValue 并更新 UI：
        - electrode 映射到 label_Electrode_xxx
        - <20 绿色边框，20-40 黄色边框，>40 红色边框
        - 全部 <20 时，开始评估按钮可用
        """
        electrodes = params.get("electrode") or params.get("Electrode") or []
        values = (
            params.get("ImpedanceValue")
            or params.get("Impedance")
            or params.get("impedance")
            or []
        )
        if not isinstance(electrodes, list) or not isinstance(values, list):
            return

        has_any = False

        for name, val in zip(electrodes, values):
            electrode_name = str(name or "").strip()
            if not electrode_name or electrode_name.upper() == "NONE":
                continue
            label = self._get_electrode_label(electrode_name)
            if label is None:
                continue
            try:
                value = float(val)
            except Exception:
                continue

            has_any = True
            if value < 20:
                color = "rgb(0, 200, 0)"
            elif value <= 40:
                color = "rgb(255, 200, 0)"
            else:
                color = "rgb(255, 0, 0)"
            safe_call(
                self._logger,
                label.setStyleSheet,
                f"background: #666666; color: #FFFFFF; "
                f"border-radius: 14px; "
                f"padding: 0px; "
                f"border: 4px solid {color}; ",
            )
            safe_call(self._logger, label.setToolTip, f"阻抗值: {value:.1f} Ω")

            self._last_impedance[str(name).strip()] = value

        # 取消“全绿才可点击”的限制：只要收到数据就保持可点
        self._set_start_evaluate_enabled(True if has_any else True)

    def _get_electrode_label(self, name: str) -> Optional[QLabel]:
        key = str(name or "").strip()
        if not key:
            return None
        if not self._electrode_label_map:
            try:
                for label in self.ui.findChildren(QLabel):
                    obj_name = label.objectName() or ""
                    if obj_name.startswith("label_Electrode_"):
                        electrode = obj_name.replace("label_Electrode_", "", 1).strip().lower()
                        if electrode:
                            self._electrode_label_map[electrode] = label
            except Exception:
                self._electrode_label_map = {}
        label = self._electrode_label_map.get(key.lower())
        if label is not None:
            return label
        return get_ui_attr(self.ui, f"label_Electrode_{key}")

    def _set_start_evaluate_enabled(self, enabled: bool) -> None:
        button = get_ui_attr(self.ui, "pushButton_startevaluate")
        safe_call(self._logger, getattr(button, "setEnabled", None), bool(enabled))

    def is_checksafe_checked(self) -> bool:
        return bool(self._checksafety_checked)

    def _on_checksafe_toggled(self, checked: bool) -> None:
        self._checksafety_checked = bool(checked)
        # 选中时文字变绿，未选中时保持红色加粗警示
        self._apply_checksafe_style(checked)

    def _sync_checksafe_state(self) -> None:
        radio = get_ui_attr(self.ui, "radioButton_checksafe")
        if radio is None:
            self._checksafety_checked = False
            return
        try:
            self._checksafety_checked = bool(radio.isChecked())
            self._apply_checksafe_style(self._checksafety_checked)
        except Exception:
            self._checksafety_checked = False

    def _apply_checksafe_style(self, checked: bool) -> None:
        radio = get_ui_attr(self.ui, "radioButton_checksafe")
        if radio is None:
            return
        if checked:
            radio.setStyleSheet(
                "QRadioButton { color: #059669; font-weight: bold; }\n"
                "QRadioButton::indicator { width: 16px; height: 16px; }"
            )
        else:
            radio.setStyleSheet(
                "QRadioButton { color: #ff0000; font-weight: bold; }\n"
                "QRadioButton::indicator { width: 16px; height: 16px; }"
            )

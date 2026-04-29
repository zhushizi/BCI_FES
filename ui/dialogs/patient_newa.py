"""
新建患者弹窗
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QDateTime
from ui.core.base_dialog import BaseUiDialog
from ui.core.utils import get_ui_attr, safe_call, safe_connect
from ui.dialogs.tips_dialog import TipsDialog

UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = UI_ROOT / "patient_newa.ui"

# 日历弹窗月份下拉箭头样式（只注入一次，供 dateTimeEdit 的 calendarPopup 使用）
_CALENDAR_ARROW_STYLE = """
QCalendarWidget QToolButton {
    padding-right: 20px;
    min-width: 60px;
}
QCalendarWidget QToolButton::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 4px;
    width: 14px;
    height: 14px;
}
"""


class PatientNewDialog(BaseUiDialog):
    """新建/编辑患者对话框"""

    def __init__(self, parent=None, data: Dict[str, Any] = None, is_edit: bool = False):
        super().__init__(parent=parent, ui_path=UI_PATH)
        self._logger = logging.getLogger(__name__)
        self._is_edit = is_edit

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 不为弹窗叠加阴影效果（避免四角出现 drop shadow）。
        self.ui.setGraphicsEffect(None)
        close_btn = get_ui_attr(self.ui, "label_close")
        safe_connect(self._logger, getattr(close_btn, "clicked", None), self.reject)

        date_edit = get_ui_attr(self.ui, "dateTimeEdit_visit")
        safe_call(self._logger, getattr(date_edit, "setDateTime", None), QDateTime.currentDateTime())

        pid_input = get_ui_attr(self.ui, "lineEdit_patientId")
        auto_pid = QDateTime.currentDateTime().toString("yyMMddHHmmss")
        safe_call(self._logger, getattr(pid_input, "setText", None), auto_pid)

        if self._is_edit:
            self.setWindowTitle("编辑患者")
            title_label = get_ui_attr(self.ui, "label")
            safe_call(
                self._logger,
                getattr(title_label, "setStyleSheet", None),
                "border-image: url(:/patient/pic/patient_revise_logo.png);",
            )
        if data:
            self.set_data(data)

        self._apply_calendar_arrow_style()

        cancel_btn = get_ui_attr(self.ui, "pushButton_cancel")
        safe_connect(self._logger, getattr(cancel_btn, "clicked", None), self.reject)
        ok_btn = get_ui_attr(self.ui, "pushButton_ok")
        if ok_btn:
            try:
                ok_btn.clicked.disconnect()
            except TypeError:
                pass
            safe_connect(self._logger, ok_btn.clicked, self._on_ok)

        # .ui 里设的是根控件的尺寸，实际窗口是 BaseUiDialog 的外层 QDialog，需在此固定大小以防拖动调整
        self.setFixedSize(1200, 612)

    @classmethod
    def _apply_calendar_arrow_style(cls) -> None:
        """为应用注入日历月份下拉箭头样式（只执行一次），修正箭头位置。"""
        if getattr(cls, "_calendar_style_applied", False):
            return
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet((app.styleSheet() or "") + _CALENDAR_ARROW_STYLE)
            cls._calendar_style_applied = True

    @staticmethod
    def _is_valid_id_card(s: str) -> bool:
        """15 位全数字，或 18 位（前 17 位数字，末位数字或 X）。"""
        t = (s or "").strip()
        if not t:
            return True  # 未填不强制（仅对已填内容校验格式）
        if len(t) == 15:
            return t.isdigit()
        if len(t) == 18:
            return t[:17].isdigit() and (t[17].isdigit() or t[17].upper() == "X")
        return False

    @staticmethod
    def _is_valid_phone(s: str) -> bool:
        """11 位纯数字；未填不强制。"""
        t = (s or "").strip()
        if not t:
            return True
        return len(t) == 11 and t.isdigit()

    def _on_ok(self):
        pid = self._get_text("lineEdit_patientId")
        name = self._get_text("lineEdit_name")
        if not pid or not name:
            TipsDialog.show_tips(self, "请填写姓名（必填项）")
            name_input = get_ui_attr(self.ui, "lineEdit_name")
            safe_call(self._logger, getattr(name_input, "setFocus", None))
            return
        id_card = self._get_text("lineEdit_idCard")
        if id_card and not self._is_valid_id_card(id_card):
            TipsDialog.show_tips(self, "身份证号不规范，请重新填写")
            id_input = get_ui_attr(self.ui, "lineEdit_idCard")
            safe_call(self._logger, getattr(id_input, "setFocus", None))
            return
        phone = self._get_text("lineEdit_phone")
        if phone and not self._is_valid_phone(phone):
            TipsDialog.show_tips(self, "手机号须为11位纯数字，请重新填写")
            phone_input = get_ui_attr(self.ui, "lineEdit_phone")
            safe_call(self._logger, getattr(phone_input, "setFocus", None))
            return
        self.accept()

    def _get_text(self, widget_name: str) -> str:
        widget = get_ui_attr(self.ui, widget_name)
        if widget is not None:
            try:
                return widget.text().strip()
            except Exception:
                return ""
        return ""

    def set_data(self, data: Dict[str, Any]):
        """将传入数据回填到表单中"""
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_patientId"), "setText", None), str(data.get("PatientId", "")))
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_name"), "setText", None), str(data.get("Name", "")))
        combo_gender = get_ui_attr(self.ui, "comboBox_gender")
        if combo_gender:
            sex = data.get("Sex", "")
            index = combo_gender.findText(sex)
            if index != -1:
                safe_call(self._logger, combo_gender.setCurrentIndex, index)
        spin_age = get_ui_attr(self.ui, "spinBox_age")
        if spin_age:
            age = data.get("Age")
            if age is not None:
                safe_call(self._logger, spin_age.setText, str(age))
        date_edit = get_ui_attr(self.ui, "dateTimeEdit_visit")
        if date_edit:
            visit_time = data.get("VisitTime", "")
            dt = QDateTime.fromString(visit_time, "yyyy/MM/dd HH:mm:ss")
            if dt.isValid():
                safe_call(self._logger, date_edit.setDateTime, dt)
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_phone"), "setText", None), str(data.get("PhoneNumber", "")))
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_idCard"), "setText", None), str(data.get("IdCard", "")))
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_notes"), "setText", None), str(data.get("Notes", "")))
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_diagnosisResult"), "setText", None), str(data.get("DiagnosisResult", "")))
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_durationOfIllness"), "setText", None), str(data.get("DurationOfillness", "")))
        safe_call(self._logger, getattr(get_ui_attr(self.ui, "lineEdit_underlyingHealthCondition"), "setText", None), str(data.get("UnderlyingHealthCondition", "")))

    def get_data(self) -> Dict[str, Any]:
        """获取表单数据"""
        sex = ""
        combo_gender = get_ui_attr(self.ui, "comboBox_gender")
        if combo_gender:
            sex = combo_gender.currentText()

        age = None
        spin_age = get_ui_attr(self.ui, "spinBox_age")
        if spin_age:
            age_text = ""
            try:
                age_text = (spin_age.text() or "").strip()
            except Exception:
                age_text = ""
            if age_text:
                try:
                    age = int(age_text)
                except (TypeError, ValueError):
                    age = None

        visit_time = ""
        date_edit = get_ui_attr(self.ui, "dateTimeEdit_visit")
        if date_edit:
            visit_time = date_edit.dateTime().toString("yyyy/MM/dd HH:mm:ss")

        return {
            "PatientId": self._get_text("lineEdit_patientId"),
            "Name": self._get_text("lineEdit_name"),
            "Sex": sex,
            "Age": age,
            "VisitTime": visit_time,
            "PhoneNumber": self._get_text("lineEdit_phone"),
            "IdCard": self._get_text("lineEdit_idCard"),
            "Notes": self._get_text("lineEdit_notes"),
            "DiagnosisResult": self._get_text("lineEdit_diagnosisResult"),
            "DurationOfillness": self._get_text("lineEdit_durationOfIllness"),
            "UnderlyingHealthCondition": self._get_text("lineEdit_underlyingHealthCondition"),
        }

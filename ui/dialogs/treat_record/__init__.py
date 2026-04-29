"""
诊疗记录对话框
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainterPath, QRegion

from ui.core.base_dialog import BaseUiDialog
from ui.core.utils import get_ui_attr, safe_connect
from ui.dialogs.treat_record.treat_record_actions import TreatRecordActions
from ui.dialogs.treat_record.treat_record_table import TreatRecordTable

UI_ROOT = Path(__file__).resolve().parents[2]
UI_PATH = UI_ROOT / "treat_record.ui"


class TreatRecordDialog(BaseUiDialog):
    """诊疗记录对话框"""
    # mask 半径略小于 ui/treat_record.ui 的 border-radius，
    # 避免裁切到表头左上角的全选复选框。
    _CORNER_RADIUS = 18

    def __init__(
        self,
        parent=None,
        patient_app=None,
        patient_id: str = None,
        patient_name: str = None,
        report_app=None,
        session_app=None,
    ):
        super().__init__(parent=parent, ui_path=UI_PATH, layout_spacing=0)
        self._logger = logging.getLogger(__name__)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        # 与 treat_record.ui 的圆角保持一致，避免外层窗口仍显示直角。
        QTimer.singleShot(0, self._apply_rounded_mask)

        self.patient_app = patient_app
        self.report_app = report_app
        self.session_app = session_app
        self.patient_id = patient_id
        self.patient_name = patient_name
        # 会话表无姓名字段；若未传入姓名则从患者表补全（供表格列与 PDF 等使用）
        if not (self.patient_name or "").strip() and self.patient_app and self.patient_id:
            try:
                p = self.patient_app.get_patient_by_id(self.patient_id)
                if p:
                    self.patient_name = (p.get("Name") or "").strip()
            except Exception:
                pass

        self._table = TreatRecordTable(self.ui, self._logger)
        self._actions = TreatRecordActions(
            session_app=self.session_app,
            report_app=self.report_app,
            patient_id=self.patient_id,
            patient_name=self.patient_name,
            logger=self._logger,
        )

        self._init_ui()

    def _init_ui(self):
        self._table.setup_header_checkbox()
        self._setup_connections()
        if self.patient_id:
            self._load_treat_records()

    def _setup_connections(self):
        back_btn = get_ui_attr(self.ui, "pushButton")
        safe_connect(self._logger, getattr(back_btn, "clicked", None), self.accept)

        export_btn = get_ui_attr(self.ui, "pushButton_2")
        safe_connect(self._logger, getattr(export_btn, "clicked", None), self._on_export_clicked)

        delete_btn = get_ui_attr(self.ui, "pushButton_3")
        safe_connect(self._logger, getattr(delete_btn, "clicked", None), self._on_delete_clicked)

        self._table.bind_header_click()

    def _load_treat_records(self):
        if not self.session_app or not self.patient_id:
            return
        records = self.session_app.get_patient_treat_sessions_by_patient(self.patient_id)
        self._table.load_records(
            records,
            on_pdf_clicked=self._on_pdf_clicked,
            on_export_pdf_clicked=self._on_export_pdf_clicked,
            on_print_clicked=self._on_print_clicked,
            patient_name=self.patient_name or "",
        )

    def _on_export_clicked(self):
        pass

    def _on_delete_clicked(self):
        self._actions.delete_selected(self._table)

    def _on_print_clicked(self, row: int):
        self._actions.print_row(row)

    def _on_pdf_clicked(self, row: int):
        self._actions.pdf_row(row, self._table)

    def _on_export_pdf_clicked(self, row: int):
        self._actions.export_pdf_row(row, self._table)

    def _apply_rounded_mask(self) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        radius = min(self._CORNER_RADIUS, min(w, h) / 2)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

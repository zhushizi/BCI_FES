"""
患者选择弹窗
"""

from __future__ import annotations

import logging
from math import ceil
from pathlib import Path
from typing import Dict, Any, Optional, List

from PySide6.QtWidgets import (
    QPushButton,
    QHBoxLayout,
    QWidget,
    QTableWidgetItem,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainterPath, QRegion

from ui.core.base_dialog import BaseUiDialog
from ui.core.utils import get_ui_attr, safe_call, safe_connect

UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = UI_ROOT / "patient_select.ui"


class PatientSelectDialog(BaseUiDialog):
    """患者选择对话框"""

    patient_selected = Signal(dict)
    _UI_CORNER_RADIUS = 30  # 与 `patient_select.ui` 中 QWidget#Form 的 border-radius 保持一致

    def __init__(self, parent=None, patient_app=None):
        super().__init__(parent=parent, ui_path=UI_PATH)
        self._logger = logging.getLogger(__name__)
        self.patient_app = patient_app
        self.selected_patient = None
        self._all_patients: List[Dict[str, Any]] = []
        self._page_index = 0
        self._page_size = 5

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 不为弹窗叠加阴影效果（避免四角出现 drop shadow）。
        # 圆角由 `patient_select.ui` 中 QWidget#Form 的 border-radius 控制。
        self.ui.setGraphicsEffect(None)
        # .ui 里设的是根控件尺寸（1200x612），而 frameless 窗口可能被拖动改变大小，
        # 这会导致阴影与圆角“比例感”不一致。
        self.setFixedSize(1200, 612)
        # 让阴影/裁切形状跟随圆角（仅用 blur 不足以让四角“更圆”）。
        QTimer.singleShot(0, self._apply_rounded_mask)
        close_btn = get_ui_attr(self.ui, "label_close")
        safe_connect(self._logger, getattr(close_btn, "clicked", None), self.reject)

        table = get_ui_attr(self.ui, "tableWidget")
        if table:
            self._setup_table_selection(table)

        self._load_patients()

        search_input = get_ui_attr(self.ui, "lineEdit_search")
        safe_connect(self._logger, getattr(search_input, "textChanged", None), self._on_search_text_changed)
        reset_btn = get_ui_attr(self.ui, "pushButton_reset")
        safe_connect(self._logger, getattr(reset_btn, "clicked", None), self._on_reset_search)
        prev_btn = get_ui_attr(self.ui, "pushButton_prev_page")
        safe_connect(self._logger, getattr(prev_btn, "clicked", None), self._on_prev_page)
        next_btn = get_ui_attr(self.ui, "pushButton_next_page")
        safe_connect(self._logger, getattr(next_btn, "clicked", None), self._on_next_page)

        if table:
            safe_connect(self._logger, getattr(table, "itemDoubleClicked", None), self._on_double_click)

    def _load_patients(self, patients: Optional[List[Dict[str, Any]]] = None):
        if patients is None:
            patients = []
            try:
                if self.patient_app:
                    patients = self.patient_app.get_patients()
            except Exception:
                self._logger.exception("加载患者数据失败")
                patients = []

        self._all_patients = list(patients or [])
        self._page_index = 0
        self._refresh_page()

    def _refresh_page(self):
        table = get_ui_attr(self.ui, "tableWidget")
        if table is None:
            return

        total = len(self._all_patients)
        total_pages = 0 if total == 0 else int(ceil(total / self._page_size))
        if total_pages > 0:
            self._page_index = min(max(self._page_index, 0), total_pages - 1)
        else:
            self._page_index = 0

        start = self._page_index * self._page_size
        end = start + self._page_size
        page_patients = self._all_patients[start:end]

        table.setRowCount(0)
        table.setRowCount(len(page_patients))

        for row, patient in enumerate(page_patients):
            item_name = QTableWidgetItem(patient.get("Name", ""))
            item_name.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, item_name)

            item_sex = QTableWidgetItem(patient.get("Sex", ""))
            item_sex.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, item_sex)

            age = patient.get("Age")
            age_text = "" if age is None else str(age)
            item_age = QTableWidgetItem(age_text)
            item_age.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 2, item_age)

            item_pid = QTableWidgetItem(patient.get("PatientId", ""))
            item_pid.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 3, item_pid)

            select_btn = QPushButton("选择")
            select_btn.setCursor(Qt.PointingHandCursor)
            select_btn.setStyleSheet(
                "QPushButton {"
                "    color: #4B86FC;"
                "    background: transparent;"
                "    border: 1px solid #4B86FC;"
                "    border-radius: 4px;"
                "    padding: 4px 12px;"
                "}"
                "QPushButton:hover {"
                "    background: #E6F0FF;"
                "}"
                "QPushButton:pressed {"
                "    background: #C8E0FF;"
                "}"
            )
            select_btn.setProperty("patient_data", patient)
            select_btn.clicked.connect(lambda checked, p=patient: self._on_select_clicked(p))

            op_container = QWidget()
            op_layout = QHBoxLayout(op_container)
            op_layout.setContentsMargins(0, 0, 0, 0)
            op_layout.setSpacing(0)
            op_layout.addStretch()
            op_layout.addWidget(select_btn)
            op_layout.addStretch()
            table.setCellWidget(row, 4, op_container)

        self._update_pagination(total, total_pages)

    def _update_pagination(self, total: int, total_pages: int):
        current_page = 0 if total_pages == 0 else self._page_index + 1
        label = get_ui_attr(self.ui, "label_page_info")
        safe_call(self._logger, getattr(label, "setText", None), f"共{total}条 {current_page}/{total_pages}页")
        prev_btn = get_ui_attr(self.ui, "pushButton_prev_page")
        safe_call(self._logger, getattr(prev_btn, "setEnabled", None), self._page_index > 0)
        next_btn = get_ui_attr(self.ui, "pushButton_next_page")
        safe_call(
            self._logger,
            getattr(next_btn, "setEnabled", None),
            total_pages > 0 and self._page_index < total_pages - 1,
        )

    def _on_prev_page(self):
        if self._page_index <= 0:
            return
        self._page_index -= 1
        self._refresh_page()

    def _on_next_page(self):
        total = len(self._all_patients)
        total_pages = 0 if total == 0 else int(ceil(total / self._page_size))
        if total_pages == 0 or self._page_index >= total_pages - 1:
            return
        self._page_index += 1
        self._refresh_page()

    def _on_double_click(self, item):
        row = item.row()
        table = get_ui_attr(self.ui, "tableWidget")
        if table is None:
            return

        name_item = table.item(row, 0)
        if name_item is None:
            return

        op_widget = table.cellWidget(row, 4)
        if op_widget:
            select_btn = op_widget.findChild(QPushButton)
            if select_btn:
                patient_data = select_btn.property("patient_data")
                if patient_data:
                    self._select_patient(patient_data)
                    return

        pid_item = table.item(row, 3)
        if pid_item:
            patient_id = pid_item.text()
            if self.patient_app:
                patients = self.patient_app.get_patients()
                for p in patients:
                    if p.get("PatientId") == patient_id:
                        self._select_patient(p)
                        break

    def _on_select_clicked(self, patient: Dict[str, Any]):
        self._select_patient(patient)

    def _select_patient(self, patient: Dict[str, Any]):
        self.selected_patient = patient
        self.patient_selected.emit(patient)
        self.accept()

    def _on_search_text_changed(self, text: str):
        keyword = text.strip() if text else ""
        patients: List[Dict[str, Any]] = []

        if self.patient_app:
            try:
                if keyword:
                    patients = self.patient_app.search_patients(keyword)
                else:
                    patients = self.patient_app.get_patients()
            except Exception:
                self._logger.exception("搜索患者失败")

        self._load_patients(patients)

    def _on_reset_search(self):
        search_input = get_ui_attr(self.ui, "lineEdit_search")
        safe_call(self._logger, getattr(search_input, "clear", None))
        self._load_patients()

    def _setup_table_selection(self, table):
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        header = table.horizontalHeader()
        if header:
            font = header.font()
            font.setBold(False)
            header.setFont(font)
            header.setHighlightSections(False)

        base_style = table.styleSheet()
        highlight_style = """
QTableWidget#tableWidget::item:selected {
    background: #E6F0FF;
    color: #000000;
}
"""
        table.setStyleSheet(f"{base_style}\n{highlight_style}")

    def get_selected_patient(self) -> Optional[Dict[str, Any]]:
        return self.selected_patient

    def _apply_rounded_mask(self) -> None:
        """给弹窗根控件设置圆角 mask，让四角阴影边界更圆润。"""
        w, h = self.ui.width(), self.ui.height()
        if w <= 0 or h <= 0:
            return

        radius = min(self._UI_CORNER_RADIUS, min(w, h) / 2)
        path = QPainterPath()
        path.addRoundedRect(self.ui.rect(), radius, radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.ui.setMask(region)

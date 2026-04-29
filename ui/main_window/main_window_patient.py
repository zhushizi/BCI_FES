from __future__ import annotations
'''
患者页（tabWidget 的 tab2）管理
'''
import logging
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, QDateTime, QRect, QSize, Signal
from PySide6.QtWidgets import (
    QWidget,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QHeaderView,
    QStyleOptionButton,
    QStyle,
    QTableWidgetItem,
    QDialog,
)

from ui.core.base_table_controller import BaseTableController
from ui.core.utils import get_ui_attr, safe_connect
from ui.dialogs.patient_newa import PatientNewDialog
from ui.dialogs.tips_dialog import TipsDialog
from ui.dialogs.treat_record import TreatRecordDialog


class CheckBoxHeader(QHeaderView):
    """带复选框的表头（仅用于第1列）"""

    checkStateChanged = Signal(Qt.CheckState)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._check_state = Qt.Unchecked
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex != 0:
            return
        option = QStyleOptionButton()
        option.state |= QStyle.State_Enabled
        if self._check_state == Qt.Checked:
            option.state |= QStyle.State_On
        elif self._check_state == Qt.PartiallyChecked:
            option.state |= QStyle.State_NoChange
        else:
            option.state |= QStyle.State_Off
        option.rect = self._checkbox_rect(rect)
        self.style().drawControl(QStyle.CE_CheckBox, option, painter)

    def mousePressEvent(self, event):
        index = self.logicalIndexAt(event.pos())
        if index == 0 and self._checkbox_rect(self._section_rect(0)).contains(event.pos()):
            self._toggle_state()
            return
        super().mousePressEvent(event)

    def _toggle_state(self):
        new_state = Qt.Unchecked if self._check_state == Qt.Checked else Qt.Checked
        self.setCheckState(new_state)
        if hasattr(self, "checkStateChanged"):
            self.checkStateChanged.emit(new_state)

    def setCheckState(self, state: Qt.CheckState):
        if state == self._check_state:
            return
        self._check_state = state
        self.updateSection(0)

    def checkState(self) -> Qt.CheckState:
        return self._check_state

    def _checkbox_rect(self, section_rect) -> QRect:
        option = QStyleOptionButton()
        check_box_size = self.style().sizeFromContents(QStyle.CT_CheckBox, option, QSize(), None)
        x = section_rect.x() + (section_rect.width() - check_box_size.width()) // 2
        y = section_rect.y() + (section_rect.height() - check_box_size.height()) // 2
        return QRect(x, y, check_box_size.width(), check_box_size.height())

    def _section_rect(self, logicalIndex: int) -> QRect:
        """兼容性包装：在 PySide6 中没有 sectionRect，手动构造"""
        return QRect(
            self.sectionPosition(logicalIndex),
            0,
            self.sectionSize(logicalIndex),
            self.height(),
        )


class PatientPageController(BaseTableController):
    """患者页（tabWidget 的 tab2）管理"""

    def __init__(
        self,
        parent: QWidget,
        ui,
        patient_app,
        user_app,
        logger: Optional[logging.Logger] = None,
        on_patient_selected: Optional[Callable[[dict], None]] = None,
        report_app=None,
    ):
        super().__init__(ui, table_name="tableWidget_patient_2")
        self.parent = parent
        self.patient_app = patient_app
        self.report_app = report_app  # 报告应用层
        self.user_app = user_app
        self.logger = logger or logging.getLogger(__name__)
        self._row_checkboxes: List[QCheckBox] = []
        self._header_checkbox: Optional[CheckBoxHeader] = None
        self._bulk_updating_checks = False
        self._patient_data: List[dict] = []
        self._on_patient_selected = on_patient_selected

    # ---------- 对外接口 ----------
    def bind_signals(self):
        """绑定患者页相关事件"""
        search = get_ui_attr(self.ui, "lineEdit_search")
        safe_connect(self.logger, getattr(search, "textChanged", None), self._on_search_text_changed)
        search2 = get_ui_attr(self.ui, "lineEdit_search_2")
        safe_connect(self.logger, getattr(search2, "textChanged", None), self._on_search_text_changed)
        reset_btn = get_ui_attr(self.ui, "pushButton_reset")
        safe_connect(self.logger, getattr(reset_btn, "clicked", None), self._on_reset_search)
        new_btn_tab = get_ui_attr(self.ui, "pushButton_tab1new")
        safe_connect(self.logger, getattr(new_btn_tab, "clicked", None), self._open_new_patient_dialog)
        new_btn = get_ui_attr(self.ui, "pushButton_new")
        safe_connect(self.logger, getattr(new_btn, "clicked", None), self._open_new_patient_dialog)

    def init_ui(self):
        """初始化表格与状态"""
        self._setup_patient_table()

    def refresh(self):
        """刷新患者数据"""
        if self._header_checkbox is None:
            self._setup_patient_table()
        else:
            self._load_patient_data()

    # ---------- 内部逻辑 ----------
    def get_table(self):
        table = get_ui_attr(self.ui, "tableWidget_patient_2")
        if table is not None:
            return table
        table = get_ui_attr(self.ui, "tableWidget_patient")
        return table if table is not None else None

    def _get_patient_table(self):
        return self.get_table()

    def _setup_patient_table(self):
        table = self._get_patient_table()
        if table is None:
            return

        column_count = table.columnCount()
        if column_count == 0:
            return

        old_header = table.horizontalHeader()
        section_sizes = [old_header.sectionSize(i) for i in range(column_count)]
        default_section_size = old_header.defaultSectionSize()
        stretch_last = old_header.stretchLastSection()

        header = CheckBoxHeader(table)
        header.setDefaultSectionSize(default_section_size)
        for idx, size in enumerate(section_sizes):
            header.resizeSection(idx, size)
        header.setStretchLastSection(stretch_last)
        table.setHorizontalHeader(header)
        self._header_checkbox = header
        header.checkStateChanged.connect(self._on_header_checkbox_state_changed)

        for col in range(column_count):
            item = table.horizontalHeaderItem(col)
            if item is None:
                item = QTableWidgetItem()
                table.setHorizontalHeaderItem(col, item)
            item.setTextAlignment(Qt.AlignCenter)

        table.setRowCount(0)
        self._row_checkboxes = []
        self._load_patient_data()

    def _load_patient_data(self):
        table = self._get_patient_table()
        if table is None:
            return

        patients: List[dict] = []
        try:
            patients = self.patient_app.get_patients()
        except Exception as e:
            self.logger.error(f"加载患者数据失败: {e}")
            TipsDialog.show_tips(self.parent, f"加载患者数据失败: {e}")
            patients = []

        self._populate_patient_table(table, patients)

    def _populate_patient_table(self, table, patients: List[dict]):
        table.blockSignals(True)
        self.clear_table()
        self._row_checkboxes = []

        if not patients:
            table.blockSignals(False)
            self._update_header_check_state()
            self._patient_data = []
            return

        table.setRowCount(len(patients))

        for row, patient in enumerate(patients):
            self.set_text_item(row, 1, patient.get("Name"))
            self.set_text_item(row, 2, patient.get("Sex"))

            age = patient.get("Age")
            age_text = "" if age is None else str(age)
            self.set_text_item(row, 3, age_text)

            self.set_text_item(row, 4, patient.get("PatientId"))
            self.set_text_item(row, 5, patient.get("VisitTime"))

            self._setup_patient_row_widgets(table, row)

        table.blockSignals(False)
        self._update_header_check_state()
        self._patient_data = patients

    def _setup_patient_row_widgets(self, table, row: int):
        checkbox = QCheckBox()
        checkbox.setTristate(False)
        checkbox.stateChanged.connect(lambda state, r=row: self._on_row_checkbox_changed(r, state))
        cb_container = QWidget()
        cb_layout = QHBoxLayout(cb_container)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setAlignment(Qt.AlignCenter)
        cb_layout.addWidget(checkbox)
        table.setCellWidget(row, 0, cb_container)
        self._row_checkboxes.append(checkbox)

        view_btn = QPushButton("查看")
        view_btn.setCursor(Qt.PointingHandCursor)
        view_btn.setFlat(True)
        view_btn.setStyleSheet(
            "QPushButton {"
            "    color: #4B86FC;"
            "    text-decoration: underline;"
            "    background: transparent;"
            "    border: none;"
            "    font-size: 20px;"
            "}"
            "QPushButton:pressed {"
            "    color: #2f64c8;"
            "}"
        )
        view_btn.clicked.connect(lambda checked, r=row: self._on_view_treat_record_clicked(r))
        view_container = QWidget()
        view_layout = QHBoxLayout(view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setAlignment(Qt.AlignCenter)
        view_layout.addWidget(view_btn)
        if table.columnCount() > 6:
            table.setCellWidget(row, 6, view_container)

        edit_btn = QPushButton()
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setFixedSize(35, 35)
        edit_btn.setStyleSheet(
            "QPushButton {"
            "    border: none;"
            "    background: transparent;"
            "    border-image: url(:/treat/pic/treat_edit.png);"
            "}"
        )
        edit_btn.clicked.connect(lambda checked, r=row: self._on_edit_patient_clicked(r))

        del_btn = QPushButton()
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setFixedSize(35, 35)
        del_btn.setStyleSheet(
            "QPushButton {"
            "    border: none;"
            "    background: transparent;"
            "    border-image: url(:/treat/pic/treat_del.png);"
            "}"
        )
        del_btn.clicked.connect(lambda checked, r=row: self._on_delete_patient_clicked(r))

        op_container = QWidget()
        op_layout = QHBoxLayout(op_container)
        op_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.setSpacing(35)
        op_layout.setAlignment(Qt.AlignCenter)
        op_layout.addWidget(edit_btn)
        op_layout.addWidget(del_btn)
        if table.columnCount() > 7:
            table.setCellWidget(row, 7, op_container)

    def _on_view_treat_record_clicked(self, row: int):
        if not self._patient_data or row >= len(self._patient_data):
            TipsDialog.show_tips(self.parent, "无法获取患者信息")
            return

        patient = self._patient_data[row]
        patient_id = patient.get("PatientId", "")
        patient_name = patient.get("Name", "")

        if not patient_id:
            TipsDialog.show_tips(self.parent, "患者病历号为空")
            return

        dialog = TreatRecordDialog(
            self.parent,
            self.patient_app,
            patient_id,
            patient_name,
            self.report_app,
            session_app=getattr(self.parent, "session_app", None),
        )
        dialog.exec()

    def _on_edit_patient_clicked(self, row: int):
        if not self._patient_data or row >= len(self._patient_data):
            TipsDialog.show_tips(self.parent, "无法获取患者信息")
            return

        patient = self._patient_data[row]
        dialog = PatientNewDialog(self.parent, data=patient, is_edit=True)
        if dialog.exec() != QDialog.Accepted:
            return

        updated = dialog.get_data()
        merged = {**patient, **updated}
        merged["PatientId"] = patient.get("PatientId", "")
        if self.user_app and self.user_app.current_user:
            merged["UserId"] = self.user_app.current_user.get("UserName", "")

        try:
            ok = self.patient_app.update_patient(merged)
        except Exception as e:
            self.logger.error(f"更新患者异常: {e}")
            TipsDialog.show_tips(self.parent, f"更新患者失败: {e}")
            return

        if ok:
            TipsDialog.show_tips(self.parent, "更新患者成功")
            self.refresh()
        else:
            TipsDialog.show_tips(self.parent, "更新患者失败")

    def _on_delete_patient_clicked(self, row: int):
        if not self._patient_data or row >= len(self._patient_data):
            TipsDialog.show_tips(self.parent, "无法获取患者信息")
            return

        patient = self._patient_data[row]
        patient_id = patient.get("PatientId", "")
        patient_name = patient.get("Name", "")

        if not patient_id:
            TipsDialog.show_tips(self.parent, "病历号为空，无法删除")
            return

        parent_win = self.parent.window() if self.parent else None
        if not TipsDialog.show_confirm(parent_win, f"确定删除患者「{patient_name or patient_id}」及其诊疗记录？"):
            return

        try:
            ok = self.patient_app.delete_patient(patient_id)
        except Exception as e:
            self.logger.error(f"删除患者异常: {e}")
            TipsDialog.show_tips(self.parent, f"删除患者失败: {e}")
            return

        if ok:
            TipsDialog.show_tips(self.parent, "删除患者成功")
            host = self.parent
            if hasattr(host, "clear_treat_context_if_patient_removed"):
                try:
                    host.clear_treat_context_if_patient_removed(patient_id)
                except Exception:
                    self.logger.exception("删除患者后清理当前治疗选择失败")
            self.refresh()
        else:
            TipsDialog.show_tips(self.parent, "删除患者失败")

    def _open_new_patient_dialog(self):
        dialog = PatientNewDialog(self.parent)
        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        if self.user_app and self.user_app.current_user:
            user_name = self.user_app.current_user.get("UserName", "")
            data.setdefault("UserId", user_name)
        if not data.get("VisitTime"):
            data["VisitTime"] = QDateTime.currentDateTime().toString("yyyy/MM/dd HH:mm:ss")

        ok = False
        try:
            ok = self.patient_app.add_patient(data)
        except Exception as e:
            self.logger.error(f"新增患者异常: {e}")
            TipsDialog.show_tips(self.parent, f"新增患者失败: {e}")
            return

        if ok:
            TipsDialog.show_tips(self.parent, "新增患者成功")
            self.refresh()
            if callable(self._on_patient_selected):
                self._on_patient_selected(data)
        else:
            TipsDialog.show_tips(self.parent, "新增患者失败")

    def _on_row_checkbox_changed(self, row: int, state: int):
        if self._bulk_updating_checks:
            return
        self._update_header_check_state()

    def _update_header_check_state(self):
        if not self._row_checkboxes or self._header_checkbox is None:
            return

        total = len(self._row_checkboxes)
        checked = sum(cb.checkState() == Qt.CheckState.Checked for cb in self._row_checkboxes)
        unchecked = sum(cb.checkState() == Qt.CheckState.Unchecked for cb in self._row_checkboxes)

        if checked == total:
            state = Qt.CheckState.Checked
        elif unchecked == total:
            state = Qt.CheckState.Unchecked
        else:
            state = Qt.CheckState.PartiallyChecked

        self._bulk_updating_checks = True
        self._header_checkbox.setCheckState(state)
        self._bulk_updating_checks = False

    def _on_header_checkbox_state_changed(self, state: Qt.CheckState):
        if self._bulk_updating_checks:
            return
        if state not in (Qt.CheckState.Checked, Qt.CheckState.Unchecked):
            return
        self._bulk_updating_checks = True
        for cb in self._row_checkboxes:
            cb.setCheckState(Qt.CheckState.Checked if state == Qt.CheckState.Checked else Qt.CheckState.Unchecked)
        self._bulk_updating_checks = False

    def _on_search_text_changed(self, text: str):
        keyword = text.strip() if text else ""
        patients: List[dict] = []
        try:
            if keyword:
                patients = self.patient_app.search_patients(keyword)
            else:
                patients = self.patient_app.get_patients()
        except Exception as e:
            self.logger.error(f"搜索患者失败: {e}")
            TipsDialog.show_tips(self.parent, f"搜索患者失败: {e}")
            patients = []

        table = self._get_patient_table()
        if table is not None:
            self._populate_patient_table(table, patients)

    def _on_reset_search(self):
        line_edit = get_ui_attr(self.ui, "lineEdit_search")
        if line_edit:
            line_edit.clear()
        line_edit_2 = get_ui_attr(self.ui, "lineEdit_search_2")
        if line_edit_2:
            line_edit_2.clear()
        self._load_patient_data()

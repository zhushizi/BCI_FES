"""
诊疗记录的操作行为（删除/打印/PDF 展示与导出）。
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog

from ui.dialogs.tips_dialog import TipsDialog
from ui.report import (
    build_report_html,
    default_pdf_filename,
    generate_and_open_pdf,
)
from ui.report.html_viewer_dialog import HtmlViewerDialog


class TreatRecordActions:
    def __init__(self, session_app, report_app, patient_id, patient_name, logger):
        self._session_app = session_app
        self._report_app = report_app
        self._patient_id = patient_id
        self._patient_name = patient_name
        self._logger = logger

    def delete_selected(self, table) -> None:
        if not self._session_app or not self._patient_id:
            return
        rows_to_delete, session_ids = table.get_selected_session_ids()
        if not rows_to_delete:
            return
        deleted = self._session_app.delete_patient_treat_sessions(session_ids)
        if deleted <= 0:
            return
        table.remove_rows(rows_to_delete)

    def print_row(self, row: int) -> None:
        self._logger.info("打印行: %s", row + 1)

    def pdf_row(self, row: int, table) -> None:
        """用网页打开报告（在软件内展示）。"""
        record_data, _treat_start_time, session_id = table.extract_row_data(row)
        html_content = build_report_html(
            session_app=self._session_app,
            report_app=self._report_app,
            patient_id=self._patient_id or "",
            patient_name=self._patient_name or "",
            session_id=session_id,
            record_data=record_data,
            embed_images_for_web=True,
        )
        title = f"诊疗报告 - {self._patient_name or '报告'}"
        parent_widget = table.ui.window() if table and getattr(table, "ui", None) else None
        dialog = HtmlViewerDialog(
            html_content=html_content,
            parent=parent_widget,
            title=title,
        )
        dialog.exec()

    def export_pdf_row(self, row: int, table) -> None:
        """导出 PDF：选择保存路径后生成并打开。"""
        record_data, _treat_start_time, session_id = table.extract_row_data(row)
        default_name = default_pdf_filename(self._patient_id or "", "诊疗报告")
        path, _ = QFileDialog.getSaveFileName(
            None,
            "导出 PDF",
            default_name,
            "PDF 文件 (*.pdf)",
        )
        if not path or not path.strip():
            return
        result = generate_and_open_pdf(
            session_app=self._session_app,
            report_app=self._report_app,
            patient_id=self._patient_id or "",
            patient_name=self._patient_name or "",
            session_id=session_id,
            record_data=record_data,
            save_path=path.strip(),
        )
        if result is None:
            TipsDialog.show_tips(None, "生成 PDF 失败，请查看日志。")

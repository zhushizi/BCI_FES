"""
诊疗报告相关（PDF 生成等）。
"""

from ui.report.report_pdf import (
    build_report_html,
    default_pdf_filename,
    generate_and_open_pdf,
    html_to_pdf,
    sanitize_filename,
)

__all__ = [
    "build_report_html",
    "default_pdf_filename",
    "generate_and_open_pdf",
    "html_to_pdf",
    "sanitize_filename",
]

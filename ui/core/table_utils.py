"""
表格相关的通用辅助函数。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem


def init_header_center(table: QTableWidget) -> None:
    """确保表头存在并居中显示。"""
    column_count = table.columnCount()
    if column_count == 0:
        return
    for col in range(column_count):
        item = table.horizontalHeaderItem(col)
        if item is None:
            item = QTableWidgetItem()
            table.setHorizontalHeaderItem(col, item)
        item.setTextAlignment(Qt.AlignCenter)


def clear_table(table: QTableWidget) -> None:
    """清空表格内容并重置行数。"""
    table.clearContents()
    table.setRowCount(0)


def set_text_item(table: QTableWidget, row: int, col: int, text: str):
    """创建居中文本单元格并返回 item。"""
    item = QTableWidgetItem(str(text) if text else "")
    item.setTextAlignment(Qt.AlignCenter)
    table.setItem(row, col, item)
    return item

"""
表格页面控制器基类：封装常见表头/清空/填充逻辑。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QTableWidget

from ui.core.table_utils import init_header_center, clear_table, set_text_item
from ui.core.utils import get_ui_attr


class BaseTableController:
    def __init__(self, ui, table_name: str) -> None:
        self.ui = ui
        self._table_name = table_name

    def get_table(self) -> Optional[QTableWidget]:
        table = get_ui_attr(self.ui, self._table_name)
        return table if table is not None else None

    def init_table(self) -> None:
        table = self.get_table()
        if table is None:
            return
        init_header_center(table)

    def clear_table(self) -> None:
        table = self.get_table()
        if table is None:
            return
        clear_table(table)

    def set_text_item(self, row: int, col: int, text: str):
        table = self.get_table()
        if table is None:
            return None
        return set_text_item(table, row, col, text)

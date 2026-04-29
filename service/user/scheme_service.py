"""
方案服务类 - 负责方案（SchemeManager 表）的业务逻辑
"""

import logging
from typing import List, Dict, Optional, Tuple, Any

from infrastructure.data import DatabaseService
from service.user._db_base import _DbBase


class SchemeService(_DbBase):
    """方案服务类"""

    TABLE_SCHEME = "SchemeManager"

    def __init__(self, db_service: DatabaseService):
        super().__init__(db_service)
        self.logger = logging.getLogger(__name__)
        self._scheme_fields = (
            "rowid AS SchemeId",
            "SchemeName",
            "Mode",
            "StimPosition",
            "StimInterval",
            "TreatTime",
        )

    def _scheme_select_sql(self) -> str:
        fields = ", ".join(self._scheme_fields)
        return f"SELECT {fields} FROM {self.TABLE_SCHEME}"

    @staticmethod
    def _normalize_name(value: Optional[str]) -> str:
        return str(value or "").strip()

    def _build_scheme_params(self, scheme: Dict[str, str]) -> Tuple[str, str, str, str, str]:
        return (
            self._normalize_name((scheme or {}).get("SchemeName")),
            (scheme or {}).get("Mode", ""),
            (scheme or {}).get("StimPosition", ""),
            (scheme or {}).get("StimInterval", ""),
            (scheme or {}).get("TreatTime", ""),
        )

    def get_schemes(self) -> List[Dict[str, str]]:
        """
        获取方案列表

        Returns:
            List[Dict[str, str]]: 方案列表，包含 SchemeId、SchemeName、Mode、StimPosition、StimInterval、TreatTime
        """
        sql = f"{self._scheme_select_sql()} ORDER BY rowid DESC"
        return self._execute_query_list(sql, (), "获取方案列表失败")

    def add_scheme(self, scheme: Dict[str, str]) -> bool:
        """
        新增方案
        """
        name = self._normalize_name((scheme or {}).get("SchemeName"))
        if not name:
            return False

        sql = f"""
            INSERT INTO {self.TABLE_SCHEME} (
                SchemeName, Mode, StimPosition, StimInterval, TreatTime
            ) VALUES (?, ?, ?, ?, ?)
        """
        params = self._build_scheme_params(scheme)
        return self._execute_update(sql, params, "新增方案失败") > 0

    def delete_scheme(self, scheme_id: int) -> bool:
        """
        根据 rowid 删除方案

        Args:
            scheme_id: SchemeManager 的 rowid（别名 SchemeId）
        """
        if scheme_id is None:
            return False

        sql = f"DELETE FROM {self.TABLE_SCHEME} WHERE rowid = ?"
        return self._execute_update(sql, (scheme_id,), "删除方案失败") > 0


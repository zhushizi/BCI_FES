from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.data import DatabaseService


class BaseSessionRepository:
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, db_service: DatabaseService, logger) -> None:
        self.db = db_service
        self.logger = logger

    @staticmethod
    def normalize_patient_id(patient_id: Any) -> str:
        return str(patient_id or "").strip()

    def now_str(self) -> str:
        return datetime.now().strftime(self.DATETIME_FORMAT)

    def _execute_update(self, sql: str, params: tuple, error_msg: str) -> int:
        try:
            return self.db.execute_update(sql, params)
        except Exception as e:
            self.logger.error(f"{error_msg}: {e}")
            return 0

    def _execute_query_one(
        self,
        sql: str,
        params: tuple,
        error_msg: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            rows = self.db.execute_query(sql, params)
            return rows[0] if rows else None
        except Exception as e:
            self.logger.error(f"{error_msg}: {e}")
            return None

    def _execute_query_list(
        self,
        sql: str,
        params: tuple,
        error_msg: str,
    ) -> List[Dict[str, Any]]:
        try:
            return self.db.execute_query(sql, params)
        except Exception as e:
            self.logger.error(f"{error_msg}: {e}")
            return []

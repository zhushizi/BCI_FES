import logging
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.data import DatabaseService


class _DbBase:
    def __init__(self, db_service: DatabaseService):
        self.db = db_service
        self.logger = logging.getLogger(__name__)

    def _execute_query_list(self, sql: str, params: Tuple[Any, ...], error_msg: str) -> List[Dict[str, Any]]:
        try:
            return self.db.execute_query(sql, params)
        except Exception as e:
            self.logger.error(f"{error_msg}: {e}")
            return []

    def _execute_query_one(self, sql: str, params: Tuple[Any, ...], error_msg: str) -> Optional[Dict[str, Any]]:
        try:
            rows = self.db.execute_query(sql, params)
            return rows[0] if rows else None
        except Exception as e:
            self.logger.error(f"{error_msg}: {e}")
            return None

    def _execute_update(self, sql: str, params: Tuple[Any, ...], error_msg: str) -> int:
        try:
            return self.db.execute_update(sql, params)
        except Exception as e:
            self.logger.error(f"{error_msg}: {e}")
            return 0

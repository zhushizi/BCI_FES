from __future__ import annotations

from typing import Any, Optional

from infrastructure.storage.erds_storage import ErdsStorage


class ErdsStorageService:
    """ERDs 存储服务（服务层）。"""

    def __init__(self, storage: ErdsStorage) -> None:
        self._storage = storage

    def save_erds_image(self, erds_base64: Any, patient_id: str, session_id: Any) -> Optional[str]:
        return self._storage.save_erds_image(erds_base64, patient_id, session_id)

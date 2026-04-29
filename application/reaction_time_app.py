from __future__ import annotations

from typing import Optional

from service.business.storage.reaction_time_storage_service import ReactionTimeStorageService


class ReactionTimeApp:
    """反应时曲线应用层：供 UI 调用。"""

    def __init__(self, storage: ReactionTimeStorageService) -> None:
        self._storage = storage

    def save_curve_bytes(self, session_id: Optional[int], image_bytes: bytes) -> Optional[str]:
        return self._storage.save_curve_bytes(session_id, image_bytes)

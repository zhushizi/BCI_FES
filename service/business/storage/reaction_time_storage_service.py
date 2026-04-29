from __future__ import annotations

from typing import Optional

from infrastructure.storage.reaction_time_storage import ReactionTimeStorage


class ReactionTimeStorageService:
    """反应时曲线存储服务（服务层）。"""

    def __init__(self, storage: ReactionTimeStorage) -> None:
        self._storage = storage

    def save_curve_bytes(self, session_id: Optional[int], image_bytes: bytes) -> Optional[str]:
        return self._storage.save_curve_bytes(session_id, image_bytes)

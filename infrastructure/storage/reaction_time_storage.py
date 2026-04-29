from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional


class ReactionTimeStorage:
    """反应时曲线图片存储（基础设施层）。"""

    def __init__(self, root_dir: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[2]
        self._logger = logger or logging.getLogger(__name__)

    def save_curve_bytes(self, session_id: Optional[int], image_bytes: bytes) -> Optional[str]:
        if not image_bytes:
            return None
        if session_id is None:
            return None
        curve_dir = self._root_dir / "db" / "ReactionTimeCurve"
        os.makedirs(curve_dir, exist_ok=True)
        file_name = f"session_{session_id}.png"
        file_path = curve_dir / file_name
        try:
            file_path.write_bytes(image_bytes)
        except Exception as exc:
            self._logger.warning("保存反应时曲线失败: %s", exc)
            return None
        return str(file_path.relative_to(self._root_dir))

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, Optional


class ErdsStorage:
    """ERDs 图片存储（基础设施层）。"""

    def __init__(self, root_dir: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[2]
        self._logger = logger or logging.getLogger(__name__)

    def save_erds_image(self, erds_base64: Any, patient_id: str, session_id: Any) -> Optional[str]:
        if not erds_base64:
            return None
        payload = self._extract_erds_payload(erds_base64)
        if not payload:
            return None
        if "," in payload:
            payload = payload.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(payload, validate=False)
        except Exception as exc:
            self._logger.warning("ERDs base64 解码失败: %s", exc)
            return None
        if not image_bytes:
            return None
        save_dir = self._root_dir / "db" / "ERDs"
        os.makedirs(save_dir, exist_ok=True)
        safe_patient = str(patient_id or "unknown").replace(":", "_").replace("/", "_").replace("\\", "_")
        session_label = session_id if session_id is not None else "unknown"
        file_name = f"erds_session_{session_label}_{safe_patient}.png"
        file_path = save_dir / file_name
        try:
            file_path.write_bytes(image_bytes)
        except Exception as exc:
            self._logger.warning("保存 ERDs 图片失败: %s", exc)
            return None
        return str(file_path.relative_to(self._root_dir))

    @staticmethod
    def _extract_erds_payload(erds_base64: Any) -> str:
        if isinstance(erds_base64, str):
            return erds_base64.strip()
        if isinstance(erds_base64, (bytes, bytearray)):
            try:
                return erds_base64.decode("utf-8", errors="ignore").strip()
            except Exception:
                return ""
        if isinstance(erds_base64, dict):
            for key in ("data", "base64", "image", "content"):
                value = erds_base64.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(erds_base64, list):
            for item in erds_base64:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    for key in ("data", "base64", "image", "content"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
        return str(erds_base64 or "").strip()

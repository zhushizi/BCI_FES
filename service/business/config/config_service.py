from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional


class ConfigService:
    """配置读写服务（服务层）。"""

    def __init__(self, config_path: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
        default_path = Path(__file__).resolve().parents[3] / "infrastructure" / "config" / "config.json"
        self._config_path = config_path or default_path
        self._logger = logger or logging.getLogger(__name__)

    @property
    def path(self) -> Path:
        return self._config_path

    def load(self) -> dict:
        if not self._config_path.is_file():
            self._logger.warning("配置文件不存在，无法读取: %s", self._config_path)
            return {}
        try:
            return json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception:
            self._logger.exception("读取配置失败: %s", self._config_path)
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        data = self.load()
        return data.get(key, default) if data else default

    def update(self, values: dict) -> bool:
        if not isinstance(values, dict):
            return False
        data = self.load()
        if not data:
            return False
        data.update(values)
        try:
            self._config_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            return True
        except Exception:
            self._logger.exception("写回配置失败: %s", self._config_path)
            return False

    def set(self, key: str, value: Any) -> bool:
        return self.update({key: value})

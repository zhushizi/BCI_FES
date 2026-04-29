from __future__ import annotations

from typing import Any

from service.business.config.config_service import ConfigService


class ConfigApp:
    """配置应用层：供 UI 调用。"""

    def __init__(self, config_service: ConfigService) -> None:
        self._service = config_service

    def load(self) -> dict:
        return self._service.load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._service.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        return self._service.set(key, value)

    def update(self, values: dict) -> bool:
        return self._service.update(values)

from __future__ import annotations

import logging
from typing import Callable, Optional

from infrastructure.communication.websocket_service import MainWebSocketService


class TrainingBaseService:
    """训练服务基类：封装 WebSocket 连接与前缀路由。"""

    def __init__(self, ws_service: MainWebSocketService) -> None:
        self.ws = ws_service
        self.logger = logging.getLogger(__name__)
        self._handler_registered = False

    def connect(self) -> None:
        self.ws.start()
        self._ensure_prefix_handler()

    def disconnect(self) -> None:
        self.ws.stop()

    def is_connected(self) -> bool:
        return self.ws.is_connected()

    def _ensure_prefix_handler(self) -> None:
        if self._handler_registered:
            return
        prefix = self._get_prefix()
        if not prefix:
            return
        try:
            self.ws.on_prefix(prefix, self._handle_prefix_message)
            self._handler_registered = True
        except Exception:
            pass

    def _get_prefix(self) -> str:
        raise NotImplementedError()

    def _handle_prefix_message(self, msg: dict) -> None:
        raise NotImplementedError()

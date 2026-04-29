from __future__ import annotations

from typing import Any, Dict

from infrastructure.communication.websocket_service import MainWebSocketService


class WsNotifyService:
    """WebSocket 通知服务（服务层）。"""

    def __init__(self, ws_service: MainWebSocketService) -> None:
        self._ws = ws_service

    def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        self._ws.send_notification(method, params)

    def send_jsonrpc(self, payload: Dict[str, Any]) -> None:
        self._ws.send_jsonrpc(payload)

    def set_decoder_ready(self, params: Dict[str, Any]) -> None:
        self._ws.decoder_ready = True
        self._ws.decoder_info = dict(params or {})

    def set_decoder_session_info(self, params: Dict[str, Any]) -> None:
        self._ws.decoder_session_info = dict(params or {})  # type: ignore[attr-defined]

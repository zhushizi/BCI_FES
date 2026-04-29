from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from service.business.ws.ws_notify_service import WsNotifyService

class WsMessageApp:
    """WebSocket 消息应用层：处理解码器状态与系统 ping。"""

    def __init__(
        self,
        ws_service: WsNotifyService,
        logger: Optional[logging.Logger] = None,
        summarize_session_info: Optional[Callable[[Dict[str, Any]], str]] = None,
        log_json: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self._ws = ws_service
        self._logger = logger or logging.getLogger(__name__)
        self._summarize_session_info = summarize_session_info
        self._log_json = log_json

    def handle_decoder_ready(self, msg: Dict[str, Any]) -> None:
        params = msg.get("params") or {}
        try:
            self._ws.set_decoder_ready(params)
        except Exception:
            pass
        if self._log_json:
            self._log_json("decoder.ready", params)

    def handle_decoder_session_info(self, msg: Dict[str, Any]) -> None:
        params = msg.get("params") or {}
        try:
            self._ws.set_decoder_session_info(params)
        except Exception:
            pass
        summary = self._summarize_session_info(params) if self._summarize_session_info else "params=<unavailable>"
        self._logger.info(f"收到 decoder.session_info: {summary}")

    def build_system_ping_result(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        params = msg.get("params") or {}
        return {
            "status": "pong",
            "battery_level": int(params.get("battery_level", 0) or 0),
            "connection_status": str(params.get("connection_status", "ok")),
        }

    # 日志与摘要策略由 UI 层注入

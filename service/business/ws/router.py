from __future__ import annotations

"""
WebSocket(JSON-RPC) 消息路由（服务层）。

目标：
- infrastructure 层的 `MainWebSocketService` 只做“连接/收发/通用分发”
- service 层集中承载“收到某些 method 后的解包/业务触发条件/后续动作”

当前落地的最小范围：
- decoder.ready：仅记录 params，并更新 ws.decoder_ready/decoder_info（保持兼容）
- decoder.session_info：记录 params，并更新 ws.decoder_session_info（保持兼容）；日志仅输出摘要避免刷屏
- system.ping：被动回 pong（可按需关闭/扩展）
- paradigm.action_command：按动作指令下发治疗命令/数据帧，收到 Treat_OK 后回 main.exo_action_complete
"""

import logging
from typing import Any, Callable, Dict, Optional, Tuple, TYPE_CHECKING

from infrastructure.communication.websocket_service import MainWebSocketService
from service.business.diagnostics.impedance_test_service import ImpedanceTestService
from service.business.ws.handlers import (
    ParadigmHandler,
    PendingActionStore,
    SerialHandler,
    StopSessionHandler,
)
from service.business.ws.utils import load_countdown_minutes

if TYPE_CHECKING:
    from infrastructure.hardware.serial_hardware import SerialHardware
    from service.business.hardware.stim_test_service import StimTestService


class WsMessageRouter:
    """服务层消息路由：把协议 method 映射到业务处理。"""

    ACTION_LEFT = "step_left"
    ACTION_RIGHT = "step_right"
    METHOD_DECODER_READY = "decoder.ready"
    METHOD_DECODER_SESSION_INFO = "decoder.session_info"
    METHOD_DECODER_IMPEDANCE_VALUE = "decoder.ImpedanceValue"
    METHOD_SYSTEM_PING = "system.ping"
    METHOD_PARADIGM_ACTION = "paradigm.action_command"
    METHOD_MAIN_STOP_SESSION = "main.stop_session"
    CHANNEL_LEFT = "left"
    CHANNEL_RIGHT = "right"
    TOKEN_TREAT_OK = "Treat_OK"

    def __init__(
        self,
        ws: MainWebSocketService,
        impedance_service: Optional[ImpedanceTestService] = None,
        stim_service: Optional["StimTestService"] = None,
        serial_hw: Optional["SerialHardware"] = None,
    ) -> None:
        self.ws = ws
        self.logger = logging.getLogger(__name__)
        self.impedance_service = impedance_service
        self.stim_service = stim_service
        self.serial_hw = serial_hw
        self._on_action_command: Optional[Callable[[int, str, str], bool]] = None
        self._on_stop_session: Optional[Callable[[Optional[float]], None]] = None
        self._on_decoder_ready: Optional[Callable[[Dict[str, Any]], None]] = None
        self._on_decoder_session_info: Optional[Callable[[Dict[str, Any]], None]] = None
        self._on_system_ping: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None
        self._pending_action_store = PendingActionStore()
        self._serial_callback_registered = False
        self._paradigm_handler = ParadigmHandler(
            logger=self.logger,
            on_action_command=self._handle_action_command,
            pending_action_store=self._pending_action_store,
            action_left=self.ACTION_LEFT,
            action_right=self.ACTION_RIGHT,
            channel_left=self.CHANNEL_LEFT,
            channel_right=self.CHANNEL_RIGHT,
        )
        self._serial_handler = SerialHandler(
            ws=self.ws,
            logger=self.logger,
            pending_action_store=self._pending_action_store,
            treat_ok_token=self.TOKEN_TREAT_OK,
        )
        self._stop_session_handler = StopSessionHandler(
            logger=self.logger,
            on_stop_session=self._handle_stop_session,
            load_countdown_minutes=load_countdown_minutes,
        )

    def register_handlers(self) -> None:
        """
        注册需要的 method 处理器。

        注意：handler 会在 WebSocket 后台线程中回调。
        若要更新 Qt UI，请在应用层用 signal 切回主线程。
        """
        self._register_ws_handlers()

        # 订阅串口回调（用于接收 Treat_OK）
        self._ensure_serial_callback()

    def set_on_action_command(self, handler: Callable[[int, str, str], bool]) -> None:
        self._on_action_command = handler

    def set_on_stop_session(self, handler: Callable[[Optional[float]], None]) -> None:
        self._on_stop_session = handler

    def set_on_decoder_ready(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._on_decoder_ready = handler

    def set_on_decoder_session_info(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._on_decoder_session_info = handler

    def set_on_system_ping(self, handler: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]) -> None:
        self._on_system_ping = handler

    def set_stim_service(self, stim_service: "StimTestService") -> None:
        self.stim_service = stim_service

    def set_serial_hw(self, serial_hw: "SerialHardware") -> None:
        self.serial_hw = serial_hw
        self._ensure_serial_callback()

    # ---------- handlers ----------
    def _on_decoder_ready(self, msg: Dict[str, Any]) -> None:
        if self._on_decoder_ready:
            self._on_decoder_ready(msg)

    def _on_decoder_session_info(self, msg: Dict[str, Any]) -> None:
        if self._on_decoder_session_info:
            self._on_decoder_session_info(msg)

    def _on_system_ping(self, msg: Dict[str, Any]) -> None:
        req_id = msg.get("id", None)
        result = None
        if self._on_system_ping:
            try:
                result = self._on_system_ping(msg)
            except Exception:
                result = None
        if result is None:
            params = msg.get("params") or {}
            result = {
                "status": "pong",
                "battery_level": int(params.get("battery_level", 0) or 0),
                "connection_status": str(params.get("connection_status", "ok")),
            }
        self.ws.send_jsonrpc({"jsonrpc": "2.0", "result": result, "id": req_id})

    def _on_decoder_impedance_value(self, msg: Dict[str, Any]) -> None:
        params = msg.get("params") or {}
        if not self.impedance_service:
            return
        try:
            self.impedance_service.update_from_decoder(params)
        except Exception as e:
            self.logger.error(f"处理 decoder.ImpedanceValue 异常: {e}")

    def _on_paradigm_action_command(self, msg: Dict[str, Any]) -> None:
        self._paradigm_handler.on_paradigm_action_command(msg)

    # ---------- helpers ----------
    def _ensure_serial_callback(self) -> None:
        if self._serial_callback_registered or not self.serial_hw:
            return
        try:
            self.serial_hw.add_data_received_callback(self._on_serial_data)
            self._serial_callback_registered = True
        except Exception as e:
            self.logger.error(f"注册串口回调失败: {e}")

    def _on_serial_data(self, data: bytes) -> None:
        self._serial_handler.on_serial_data(data)

    def _on_main_stop_session(self, msg: Dict[str, Any]) -> None:
        self._stop_session_handler.on_main_stop_session(msg)

    def _contains_treat_ok(self, data: bytes) -> bool:
        return self._serial_handler.contains_treat_ok(data)

    def _handle_action_command(self, trial_index: int, action: str, channel: str) -> bool:
        if not self._on_action_command:
            return False
        try:
            return bool(self._on_action_command(trial_index, action, channel))
        except Exception:
            return False

    def _handle_stop_session(self, countdown_minutes: Optional[float]) -> None:
        if not self._on_stop_session:
            return
        try:
            self._on_stop_session(countdown_minutes)
        except Exception:
            pass

    def _register_ws_handlers(self) -> None:
        handlers: Tuple[Tuple[str, Callable[[Dict[str, Any]], None]], ...] = (
            (self.METHOD_DECODER_READY, self._on_decoder_ready),
            (self.METHOD_DECODER_SESSION_INFO, self._on_decoder_session_info),
            (self.METHOD_DECODER_IMPEDANCE_VALUE, self._on_decoder_impedance_value),
            (self.METHOD_SYSTEM_PING, self._on_system_ping),
            (self.METHOD_PARADIGM_ACTION, self._on_paradigm_action_command),
            (self.METHOD_MAIN_STOP_SESSION, self._on_main_stop_session),
        )
        for method, handler in handlers:
            self.ws.on(method, handler)

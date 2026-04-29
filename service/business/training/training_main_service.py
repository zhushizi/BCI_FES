from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from infrastructure.communication.websocket_service import MainWebSocketService
from service.business.protocol.eeg_parser import EegBinaryParser
from service.business.training.base_service import TrainingBaseService


class TrainingMainService(TrainingBaseService):
    """
    训练主屏服务（业务层）：主要与解码器通信（WebSocket）。

    框架阶段：定义最小职责：连接/断连、开始/结束训练、接收解码器推送。
    """

    def __init__(self, ws_service: MainWebSocketService):
        super().__init__(ws_service)
        self._on_decoder_params: Optional[Callable[[dict[str, Any]], None]] = None
        self._on_eeg_frame: Optional[Callable[[dict[str, Any]], None]] = None
        self._binary_handler_registered = False
        self._decoder_prefix = "decoder."
        self._method_to_decoder = "main.to_decoder"
        self._eeg_parser = EegBinaryParser(self.logger)

    def set_on_decoder_params(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """应用层注册回调：用于把解码器参数写入 PatientApp 的患者绑定缓存。"""
        self._on_decoder_params = handler
        self._ensure_prefix_handler()

    def set_on_eeg_frame(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """应用层注册回调：用于接收 EEG 波形帧。"""
        self._on_eeg_frame = handler
        self._ensure_binary_handler()

    def _get_prefix(self) -> str:
        return self._decoder_prefix

    def _ensure_binary_handler(self) -> None:
        if self._binary_handler_registered:
            return
        try:
            self.ws.on_binary(self._handle_binary_frame)
            self._binary_handler_registered = True
        except Exception:
            pass
    
    def _handle_prefix_message(self, msg: dict[str, Any]) -> None:
        # 框架阶段：直接把整包 JSON-RPC dict 往上抛（应用层可自行取 params/method）
        if self._on_decoder_params:
            self._on_decoder_params(msg)

    def _handle_binary_frame(self, bytes_data: bytes) -> None:
        if not self._on_eeg_frame:
            return
        payload = self._eeg_parser.parse(bytes_data)
        if not payload:
            return
        try:
            self._on_eeg_frame(payload)
        except Exception:
            pass

    def start_training(self, patient_id: str) -> None:
        self.logger.info(f"TrainingMainService.start_training(patient_id={patient_id}) [TODO]")
        # 注意：按 PDF 流程一般不是主控直接触发 decoder 解码；这里先保留透传占位
        self.ws.send_notification(self._method_to_decoder, {"type": "start", "patient_id": patient_id})

    def stop_training(self) -> None:
        self.logger.info("TrainingMainService.stop_training() [TODO]")
        self.ws.send_notification(self._method_to_decoder, {"type": "stop"})

    def send_notification(self, method: str, params: dict) -> None:
        self.ws.send_notification(method, params)

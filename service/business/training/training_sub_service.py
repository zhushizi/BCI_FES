from __future__ import annotations

from typing import Any, Callable, Optional

from infrastructure.communication.websocket_service import MainWebSocketService
from service.business.training.base_service import TrainingBaseService


class TrainingSubService(TrainingBaseService):
    """
    训练副屏服务（业务层）：主要与范式模块通信（WebSocket）。

    框架阶段：只做接口定义与空流程。
    """

    def __init__(self, ws_service: MainWebSocketService):
        super().__init__(ws_service)
        self._on_paradigm_params: Optional[Callable[[dict[str, Any]], None]] = None
        self._paradigm_prefix = "paradigm."
        self._method_to_paradigm = "main.to_paradigm"

    def set_on_paradigm_params(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._on_paradigm_params = handler
        self._ensure_prefix_handler()
    
    def _handle_prefix_message(self, msg: dict[str, Any]) -> None:
        if self._on_paradigm_params:
            self._on_paradigm_params(msg)

    def _get_prefix(self) -> str:
        return self._paradigm_prefix

    def start_paradigm(self, patient_id: str) -> None:
        self.logger.info(f"TrainingSubService.start_paradigm(patient_id={patient_id}) [TODO]")
        # 注意：范式一般由主控启动外部 exe；这里先保留透传占位
        self.ws.send_notification(self._method_to_paradigm, {"type": "start", "patient_id": patient_id})

    def stop_paradigm(self) -> None:
        self.logger.info("TrainingSubService.stop_paradigm() [TODO]")
        self.ws.send_notification(self._method_to_paradigm, {"type": "stop"})

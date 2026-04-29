from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from infrastructure.communication.websocket_service import MainWebSocketService


class ImpedanceMode(Enum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class ImpedanceResult:
    raw: dict[str, Any]


class ImpedanceTestService:
    """
    脑阻抗测试服务（业务层）。

    框架阶段：仅占位。后续你明确阻抗数据来源（硬件/解码器/范式/下位机）后再落实现。
    """

    def __init__(self, ws_service: MainWebSocketService):
        self.logger = logging.getLogger(__name__)
        self.ws_service = ws_service
        self._latest: Optional[dict[str, Any]] = None
        self._update_callback: Optional[Callable[[dict[str, Any]], None]] = None
        self._update_listeners: list[Callable[[ImpedanceResult], None]] = []
        self._mode = ImpedanceMode.CLOSE

        # 协议常量：统一维护，便于后续扩展/切换来源
        self._method_set_mode = "main.set_ImpedanceMode"

    def start(self, patient_id: Optional[str] = None) -> bool:
        self.logger.info(f"ImpedanceTestService.start(patient_id={patient_id})")
        self._set_mode(ImpedanceMode.OPEN)
        return True

    def stop(self) -> bool:
        self.logger.info("ImpedanceTestService.stop()")
        self._set_mode(ImpedanceMode.CLOSE)
        return True

    def get_latest(self) -> Optional[dict[str, Any]]:
        """返回最近一次阻抗结果（占位）。"""
        return self._latest

    def get_latest_result(self) -> Optional[ImpedanceResult]:
        """返回最近一次阻抗结果（结构化）。"""
        if self._latest is None:
            return None
        return ImpedanceResult(raw=dict(self._latest))

    def get_mode(self) -> ImpedanceMode:
        """获取当前阻抗模式（仅本地状态）。"""
        return self._mode

    def set_update_callback(self, callback: Optional[Callable[[dict[str, Any]], None]]) -> None:
        """兼容旧接口：保持单回调写法。"""
        self._update_callback = callback

    def add_update_listener(self, listener: Callable[[ImpedanceResult], None]) -> None:
        if listener not in self._update_listeners:
            self._update_listeners.append(listener)

    def remove_update_listener(self, listener: Callable[[ImpedanceResult], None]) -> None:
        if listener in self._update_listeners:
            self._update_listeners.remove(listener)

    def update_from_decoder(self, params: dict[str, Any]) -> None:
        """由 WS 路由层回调，写入最新阻抗数据并通知 UI。"""
        self._latest = dict(params or {})
        self._notify_update(self._latest)

    def _set_mode(self, mode: ImpedanceMode) -> None:
        self._mode = mode
        self._send_set_mode(mode)

    def _send_set_mode(self, mode: ImpedanceMode) -> None:
        """发送阻抗模式开关命令（兼容后续协议变更）。"""
        payload = self._build_payload(mode)
        self.ws_service.send_notification(self._method_set_mode, payload)

    @staticmethod
    def _build_payload(mode: ImpedanceMode) -> dict[str, str]:
        return {"open_or_close": mode.value}

    def _notify_update(self, latest: dict[str, Any]) -> None:
        """安全地通知上层更新。"""
        if not self._update_callback:
            self._notify_listeners(latest)
            return
        try:
            self._update_callback(latest)
        except Exception as e:
            # 保持功能逻辑不变：吞掉回调异常，但记录日志便于排查
            self.logger.warning(f"阻抗更新回调异常: {e}")
        self._notify_listeners(latest)

    def _notify_listeners(self, latest: dict[str, Any]) -> None:
        if not self._update_listeners:
            return
        result = ImpedanceResult(raw=dict(latest))
        for listener in list(self._update_listeners):
            try:
                listener(result)
            except Exception as e:
                self.logger.warning(f"阻抗更新监听异常: {e}")

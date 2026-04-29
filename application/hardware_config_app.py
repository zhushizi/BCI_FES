from __future__ import annotations

import logging
from typing import Optional

from application.config_app import ConfigApp
from application.hardware_app import HardwareApp
from application.decoder_app import DecoderApp


class HardwareConfigApp:
    """硬件配置应用层：串口与解码器端口配置编排。"""

    def __init__(
        self,
        config_app: ConfigApp,
        hardware_app: Optional[HardwareApp] = None,
        decoder_app: Optional[DecoderApp] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config_app = config_app
        self._hardware_app = hardware_app
        self._decoder_app = decoder_app
        self._logger = logger or logging.getLogger(__name__)

    def list_available_ports(self) -> list[str]:
        if not self._hardware_app:
            return []
        try:
            return list(self._hardware_app.list_available_ports())
        except Exception as exc:
            self._logger.warning("读取串口列表失败: %s", exc)
            return []

    def list_available_port_details(self) -> list[dict[str, str]]:
        if not self._hardware_app:
            return []
        try:
            return list(self._hardware_app.list_available_port_details())
        except Exception as exc:
            self._logger.warning("读取串口详情失败: %s", exc)
            return []

    @staticmethod
    def classify_ports(port_details: list[dict[str, str]]) -> dict[str, Optional[str]]:
        """
        根据串口描述特征分类：
        - description/manufacturer/hwid 含“串行设备” -> decoder_port（脑机设备）
        - description/manufacturer/hwid 含“CH340” -> NES_port（神经肌肉电刺激设备）
        """
        decoder_port: Optional[str] = None
        nes_port: Optional[str] = None
        for item in port_details:
            device = str(item.get("device") or "").strip()
            if not device:
                continue
            haystack = " ".join(
                [
                    str(item.get("description") or ""),
                    str(item.get("manufacturer") or ""),
                    str(item.get("hwid") or ""),
                ]
            ).upper()
            if decoder_port is None and "串行设备" in haystack:
                decoder_port = device
            if nes_port is None and "CH340" in haystack:
                nes_port = device
            if decoder_port and nes_port:
                break
        return {"decoder_port": decoder_port, "NES_port": nes_port}

    def get_decoder_port(self) -> Optional[str]:
        return str(self._config_app.get("decoder_port") or "").strip() or None

    def get_nes_port(self) -> Optional[str]:
        return str(self._config_app.get("NES_port") or "").strip() or None

    def set_decoder_port(self, port: str) -> bool:
        next_port = str(port or "").strip()
        if not next_port:
            return False
        if not self._config_app.set("decoder_port", next_port):
            return False
        if self._decoder_app:
            try:
                return bool(self._decoder_app.restart(next_port))
            except Exception as exc:
                self._logger.warning("切换解码器端口异常: %s", exc)
                return False
        return True

    def set_nes_port(self, port: str) -> bool:
        next_port = str(port or "").strip()
        if not next_port:
            return False
        if not self._config_app.set("NES_port", next_port):
            return False
        if self._hardware_app:
            try:
                return bool(self._hardware_app.set_nes_port(next_port))
            except Exception as exc:
                self._logger.warning("切换串口异常: %s", exc)
                return False
        return True

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from infrastructure.hardware import SerialHardware
from service.business.protocol.stim_frame import StimFrame


class _Channel(Enum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"

    @classmethod
    def from_value(cls, value: Optional[str]) -> "_Channel":
        if value is None:
            return cls.UNKNOWN
        v = str(value).lower()
        if v == "left":
            return cls.LEFT
        if v == "right":
            return cls.RIGHT
        return cls.UNKNOWN


class StimTestService:
    """
    电刺激/治疗指令服务（业务层）。

    说明：
    - 这里承载原 `HardwareTreatmentService` 的协议构帧与发送逻辑（已迁移到本文件）
    - 上层（App/UI）只调用本服务暴露的用例接口，不直接依赖串口/协议细节
    """

    # 协议常量
    FRAME_HEADER = StimFrame.FRAME_HEADER
    FRAME_LENGTH = StimFrame.FRAME_LENGTH
    RESERVED_BYTE = StimFrame.RESERVED_BYTE
    RESERVED_LEFT = StimFrame.RESERVED_LEFT
    RESERVED_RIGHT = StimFrame.RESERVED_RIGHT
    FRAME_DATA_SIZE = StimFrame.FRAME_DATA_SIZE

    # 帧类型
    FRAME_TYPE_COMMAND = StimFrame.FRAME_TYPE_COMMAND
    FRAME_TYPE_DATA = StimFrame.FRAME_TYPE_DATA

    # 命令类型
    CMD_START_TREATMENT = 0x01  # 开始治疗
    CMD_STOP_TREATMENT = 0x10   # 停止治疗

    # 方案类型
    SCHEME_ONE = 0x01  # 方案一
    SCHEME_TWO = 0x02  # 方案二

    def __init__(self, serial_hardware: SerialHardware):
        self.serial_hw = serial_hardware
        self.logger = logging.getLogger(__name__)
        self.log_send_enabled = False  # 不打印发送给 hardware 的指令

    # --------- 串口管理（供应用层调用） ---------
    def list_available_ports(self) -> list[str]:
        try:
            return [port.device for port in SerialHardware.list_available_ports()]
        except Exception as exc:
            self.logger.warning("获取串口列表失败: %s", exc)
            return []

    def list_available_port_details(self) -> list[dict[str, str]]:
        try:
            return SerialHardware.list_available_port_details()
        except Exception as exc:
            self.logger.warning("获取串口详情失败: %s", exc)
            return []

    def switch_port(self, next_port: str) -> bool:
        """切换串口端口并重连。"""
        port = str(next_port or "").strip()
        if not port:
            return False
        if self.serial_hw.port == port and self.serial_hw.is_connected():
            return True
        try:
            self.serial_hw.disconnect()
        except Exception:
            pass
        self.serial_hw.port = port
        return bool(self.serial_hw.connect())

    # --------- 兼容接口（原 HardwareTreatmentService） ---------
    def start_treatment(self) -> bool:
        """开始治疗（发送命令帧）"""
        return self._send_command(self.CMD_START_TREATMENT, desc="开始治疗命令")

    def start_treatment_channel(self, channel: str) -> bool:
        """
        按通道发送开始治疗命令帧，保留位区分左右通道
        channel: 'left' 使用 0x0A，'right' 使用 0x0B，其他默认 0x00
        """
        reserved = self._channel_reserved(channel)
        return self._send_command(
            self.CMD_START_TREATMENT,
            reserved_byte=reserved,
            desc=f"开始治疗命令 channel={channel}, reserved=0x{reserved:02X}",
        )

    def start_treatment_dual(self) -> bool:
        """左右通道各发送一次开始治疗命令帧"""
        left_ok = self.start_treatment_channel("left")
        right_ok = self.start_treatment_channel("right")
        return left_ok and right_ok

    def stop_treatment(self) -> bool:
        """停止治疗（发送命令帧）"""
        return self._send_command(self.CMD_STOP_TREATMENT, desc="停止治疗命令")

    def stop_treatment_channel(self, channel: str) -> bool:
        """
        按通道发送停止治疗命令帧，保留位区分左右通道
        channel: 'left' 使用 0x0A，'right' 使用 0x0B，其他默认 0x00
        """
        reserved = self._channel_reserved(channel)
        return self._send_command(
            self.CMD_STOP_TREATMENT,
            reserved_byte=reserved,
            desc=f"停止治疗命令 channel={channel}, reserved=0x{reserved:02X}",
        )

    def stop_treatment_dual(self) -> bool:
        """左右通道各发送一次停止治疗命令帧"""
        left_ok = self.stop_treatment_channel("left")
        right_ok = self.stop_treatment_channel("right")
        return left_ok and right_ok

    def set_treatment_params(
        self,
        scheme: int,
        frequency: int,
        current: int,
        channel: Optional[str] = None,
        time_byte: Optional[int] = None,
    ) -> bool:
        """
        设置治疗参数（发送数据帧）

        scheme: 1/2
        frequency: 20~100，单位 ms，写入数据帧频率字段时按单字节值发送（0x14~0x64）
        current: 0~0x99
        """
        # 参数验证
        if scheme not in [self.SCHEME_ONE, self.SCHEME_TWO]:
            raise ValueError(f"方案参数无效: {scheme}，应为 {self.SCHEME_ONE} 或 {self.SCHEME_TWO}")
        if not (20 <= frequency <= 100):
            raise ValueError(f"频率参数无效: {frequency}，应为 20~100ms")
        if not (0 <= current <= 0x99):
            raise ValueError(f"电流无效: {current}，应为 0~153 (0x00~0x99)")

        reserved = self._channel_reserved(channel) if channel else self.RESERVED_BYTE
        time_desc = f", time=0x{int(time_byte):02X}" if time_byte is not None else ""
        return self._send_data(
            scheme=scheme,
            frequency=frequency,
            current=current,
            reserved_byte=reserved,
            time_byte=time_byte,
            desc=f"治疗参数 方案={scheme}, 频率={frequency}ms(0x{frequency:02X}), 电流={current}, reserved=0x{reserved:02X}{time_desc}",
        )

    def start_dual(self) -> bool:
        """电刺激测试：双通道开始（兼容旧接口）"""
        return self.start_treatment_dual()

    def stop_dual(self) -> bool:
        """电刺激测试：双通道停止（兼容旧接口）"""
        return self.stop_treatment_dual()

    def set_params(
        self,
        scheme: int,
        frequency: int,
        current: int,
        channel: Optional[str] = None,
        time_byte: Optional[int] = None,
    ) -> bool:
        """电刺激测试：设置参数（兼容旧接口）"""
        return self.set_treatment_params(
            scheme=scheme,
            frequency=frequency,
            current=current,
            channel=channel,
            time_byte=time_byte,
        )

    # ------------------ 协议构帧 ------------------
    def _build_command_frame(self, command: int, reserved_byte: int = None) -> bytes:
        """
        帧格式：
        [帧头(2)] [长度(1)] [保留(1)] [帧类型(1)] [命令(1)] [保留(5)] [校验和(2)]
        """
        rb = self.RESERVED_BYTE if reserved_byte is None else reserved_byte
        return StimFrame.build_command(command, rb)

    def _build_data_frame(
        self,
        scheme: int,
        frequency: int,
        current: int,
        reserved_byte: int = None,
        time_byte: Optional[int] = None,
    ) -> bytes:
        """
        帧格式：
        [帧头(2)] [长度(1)] [保留(1)] [帧类型(1)] [方案(1)] [频率(1)] [电流(1)] [时间(1)] [保留(2)] [校验和(2)]
        """
        rb = self.RESERVED_BYTE if reserved_byte is None else reserved_byte
        return StimFrame.build_data(
            scheme=scheme,
            frequency=frequency,
            current=current,
            reserved_byte=rb,
            time_byte=time_byte,
        )

    def _channel_reserved(self, channel: Optional[str]) -> int:
        ch = _Channel.from_value(channel)
        if ch is _Channel.LEFT:
            return self.RESERVED_LEFT
        if ch is _Channel.RIGHT:
            return self.RESERVED_RIGHT
        return self.RESERVED_BYTE

    def _calculate_checksum(self, data: bytearray) -> bytes:
        return StimFrame._calculate_checksum(data)

    # ------------------ 内部工具 ------------------
    def _log_send(self, packet: bytes, success: bool, desc: str = "") -> None:
        if not self.log_send_enabled:
            return
        status = "成功" if success else "失败"
        hex_str = packet.hex()
        if desc:
            self.logger.info(f"[发送{status}] {desc} | data={hex_str}")
        else:
            self.logger.info(f"[发送{status}] data={hex_str}")

    def _send_command(self, command: int, reserved_byte: int = None, desc: str = "") -> bool:
        packet = self._build_command_frame(command, reserved_byte=reserved_byte)
        success = self.serial_hw.send_data(packet)
        self._log_send(packet, success, desc=desc)
        return success

    def _send_data(
        self,
        *,
        scheme: int,
        frequency: int,
        current: int,
        reserved_byte: int,
        time_byte: Optional[int],
        desc: str,
    ) -> bool:
        packet = self._build_data_frame(
            scheme,
            frequency,
            current,
            reserved_byte=reserved_byte,
            time_byte=time_byte,
        )
        success = self.serial_hw.send_data(packet)
        self._log_send(packet, success, desc=desc)
        return success

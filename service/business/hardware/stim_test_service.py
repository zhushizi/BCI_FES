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
    FRAME_DATA_SIZE = StimFrame.FRAME_DATA_SIZE

    DEVICE_LEFT_THIGH = StimFrame.DEVICE_LEFT_THIGH
    DEVICE_LEFT_CALF = StimFrame.DEVICE_LEFT_CALF
    DEVICE_RIGHT_THIGH = StimFrame.DEVICE_RIGHT_THIGH
    DEVICE_RIGHT_CALF = StimFrame.DEVICE_RIGHT_CALF

    FRAME_TYPE_BASIC = StimFrame.FRAME_TYPE_BASIC
    FRAME_TYPE_ADVANCED = StimFrame.FRAME_TYPE_ADVANCED
    WAVEFORM_SYMMETRIC = StimFrame.WAVEFORM_SYMMETRIC
    WAVEFORM_ASYMMETRIC = StimFrame.WAVEFORM_ASYMMETRIC
    CURRENT_MODE_START = StimFrame.CURRENT_MODE_START
    CURRENT_MODE_STOP = StimFrame.CURRENT_MODE_STOP
    CURRENT_MAX_OUTPUT = 0x50
    DEFAULT_PULSE_WIDTH = 1
    DEFAULT_FREQUENCY = 20
    DEFAULT_STIM_TIME = 10
    DEFAULT_RISE_TIME = 5
    DEFAULT_DOWN_TIME = 5

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
        """开始治疗（发送高级参数帧，默认左小腿）"""
        return self.start_treatment_channel("left")

    def start_treatment_channel(self, channel: str) -> bool:
        """
        按通道发送开始治疗高级参数帧。
        旧接口无法得知大小腿和 UI 时间，默认按小腿及默认时间发送。
        """
        device = self.device_code_for(channel, "小腿")
        return self.send_advanced_params(
            device=device,
            current=self.CURRENT_MODE_START,
            stim_time=self.DEFAULT_STIM_TIME,
            rise_time=self.DEFAULT_RISE_TIME,
            down_time=self.DEFAULT_DOWN_TIME,
        )

    def start_treatment_dual(self) -> bool:
        """左右通道各发送一次开始治疗高级参数帧"""
        left_ok = self.start_treatment_channel("left")
        right_ok = self.start_treatment_channel("right")
        return left_ok and right_ok

    def stop_treatment(self) -> bool:
        """停止治疗（发送高级参数帧，默认左小腿）"""
        return self.stop_treatment_channel("left")

    def stop_treatment_channel(self, channel: str) -> bool:
        """
        按通道发送停止治疗高级参数帧。
        旧接口无法得知大小腿和 UI 时间，默认按小腿及默认时间发送。
        """
        device = self.device_code_for(channel, "小腿")
        return self.send_advanced_params(
            device=device,
            current=self.CURRENT_MODE_STOP,
            stim_time=self.DEFAULT_STIM_TIME,
            rise_time=self.DEFAULT_RISE_TIME,
            down_time=self.DEFAULT_DOWN_TIME,
        )

    def stop_treatment_dual(self) -> bool:
        """左右通道各发送一次停止治疗高级参数帧"""
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
        设置治疗参数（兼容旧接口：发送基础参数帧 + 高级参数帧）

        scheme: 1/2，对应新协议波形 0x01/0x02
        frequency/current/time_byte 直接按单字节参数下发
        """
        device = self.device_code_for(channel or "left", "小腿")
        stim_time = self.DEFAULT_STIM_TIME if time_byte is None else int(time_byte)
        basic_ok = self.send_basic_params(
            device=device,
            waveform=scheme,
            pulse_width=self.DEFAULT_PULSE_WIDTH,
            frequency=frequency,
        )
        advanced_ok = self.send_advanced_params(
            device=device,
            current=current,
            stim_time=stim_time,
            rise_time=self.DEFAULT_RISE_TIME,
            down_time=self.DEFAULT_DOWN_TIME,
        )
        return basic_ok and advanced_ok

    def send_basic_params(self, device: int, waveform: int, pulse_width: int, frequency: int) -> bool:
        self._validate_device(device)
        waveform = self._normalize_waveform(waveform)
        pulse_width = self._normalize_byte(pulse_width, "脉冲宽度")
        frequency = self._normalize_byte(frequency, "频率")
        return self._send_basic(
            device=device,
            waveform=waveform,
            pulse_width=pulse_width,
            frequency=frequency,
            desc=(
                f"基础参数 device=0x{device:02X}, waveform=0x{waveform:02X}, "
                f"pulse_width={pulse_width}, frequency={frequency}"
            ),
        )

    def send_advanced_params(
        self,
        device: int,
        current: int,
        stim_time: int,
        rise_time: int,
        down_time: int,
    ) -> bool:
        self._validate_device(device)
        current = self._normalize_current(current)
        stim_time = self._normalize_byte(stim_time, "刺激时间")
        rise_time = self._normalize_byte(rise_time, "上升时间")
        down_time = self._normalize_byte(down_time, "下降时间")
        return self._send_advanced(
            device=device,
            current=current,
            stim_time=stim_time,
            rise_time=rise_time,
            down_time=down_time,
            desc=(
                f"高级参数 device=0x{device:02X}, current=0x{current:02X}, "
                f"stim_time={stim_time}, rise_time={rise_time}, down_time={down_time}"
            ),
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
    def _build_basic_frame(self, device: int, waveform: int, pulse_width: int, frequency: int) -> bytes:
        """
        基础参数帧：
        [55 AA] [0D] [设备位置] [0x01] [波形] [波宽] [频率] [保留3字节] [校验2字节]
        """
        return StimFrame.build_basic_params(
            device=device,
            waveform=waveform,
            pulse_width=pulse_width,
            frequency=frequency,
        )

    def _build_advanced_frame(self, device: int, current: int, stim_time: int, rise_time: int, down_time: int) -> bytes:
        """
        高级参数帧：
        [55 AA] [0D] [设备位置] [0x02] [治疗模式] [电流/启停模式] [刺激时间] [保留] [上升时间] [下降时间] [校验2字节]
        """
        return StimFrame.build_advanced_params(
            device=device,
            current=current,
            stim_time=stim_time,
            rise_time=rise_time,
            down_time=down_time,
        )

    @classmethod
    def device_code_for(cls, channel: Optional[str], leg_part: Optional[str]) -> int:
        ch = _Channel.from_value(channel)
        part = str(leg_part or "").strip().lower()
        is_thigh = "大腿" in part or "tai" in part or "thigh" in part
        if ch is _Channel.RIGHT:
            return cls.DEVICE_RIGHT_THIGH if is_thigh else cls.DEVICE_RIGHT_CALF
        return cls.DEVICE_LEFT_THIGH if is_thigh else cls.DEVICE_LEFT_CALF

    def _calculate_checksum(self, data: bytearray) -> bytes:
        return StimFrame._calculate_checksum(data)

    def _validate_device(self, device: int) -> None:
        valid = {
            self.DEVICE_LEFT_THIGH,
            self.DEVICE_LEFT_CALF,
            self.DEVICE_RIGHT_THIGH,
            self.DEVICE_RIGHT_CALF,
        }
        if int(device) not in valid:
            raise ValueError(f"设备位置无效: 0x{int(device):02X}")

    def _normalize_waveform(self, value: int) -> int:
        waveform = int(value)
        if waveform in (self.WAVEFORM_SYMMETRIC, self.WAVEFORM_ASYMMETRIC):
            return waveform
        raise ValueError(
            f"波形参数无效: {value}，应为 0x{self.WAVEFORM_SYMMETRIC:02X} 或 0x{self.WAVEFORM_ASYMMETRIC:02X}"
        )

    def _normalize_byte(self, value: int, name: str) -> int:
        ivalue = int(value)
        if not (0 <= ivalue <= 0xFF):
            raise ValueError(f"{name}参数无效: {value}，应为 0~255")
        return ivalue

    def _normalize_current(self, value: int) -> int:
        current = int(value)
        if current in (self.CURRENT_MODE_START, self.CURRENT_MODE_STOP):
            return current
        return max(0, min(self.CURRENT_MAX_OUTPUT, current))

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

    def _send_basic(
        self,
        *,
        device: int,
        waveform: int,
        pulse_width: int,
        frequency: int,
        desc: str,
    ) -> bool:
        packet = self._build_basic_frame(
            device=device,
            waveform=waveform,
            pulse_width=pulse_width,
            frequency=frequency,
        )
        success = self.serial_hw.send_data(packet)
        self._log_send(packet, success, desc=desc)
        return success

    def _send_advanced(
        self,
        *,
        device: int,
        current: int,
        stim_time: int,
        rise_time: int,
        down_time: int,
        desc: str,
    ) -> bool:
        packet = self._build_advanced_frame(
            device=device,
            current=current,
            stim_time=stim_time,
            rise_time=rise_time,
            down_time=down_time,
        )
        success = self.serial_hw.send_data(packet)
        self._log_send(packet, success, desc=desc)
        return success

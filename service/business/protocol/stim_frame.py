from __future__ import annotations

from typing import Optional


class StimFrame:
    FRAME_HEADER = bytes([0x55, 0xAA])  # 帧头
    FRAME_LENGTH = 0x0D  # 帧长度（13字节，定长）
    RESERVED_BYTE = 0x00  # 默认保留字节
    RESERVED_LEFT = 0x0A  # 左通道保留位
    RESERVED_RIGHT = 0x0B  # 右通道保留位
    FRAME_DATA_SIZE = 11  # 不含校验和的前11字节

    FRAME_TYPE_COMMAND = 0xCD  # 命令帧
    FRAME_TYPE_DATA = 0xDA     # 数据帧

    @classmethod
    def build_command(cls, command: int, reserved_byte: int) -> bytes:
        payload = [command] + [cls.RESERVED_BYTE] * 5
        return cls._build_frame(cls.FRAME_TYPE_COMMAND, payload, reserved_byte)

    @classmethod
    def build_data(
        cls,
        scheme: int,
        frequency: int,
        current: int,
        reserved_byte: int,
        time_byte: Optional[int],
    ) -> bytes:
        tb = cls.RESERVED_BYTE if time_byte is None else (int(time_byte) & 0xFF)
        payload = [scheme, frequency, current, tb] + [cls.RESERVED_BYTE] * 2
        return cls._build_frame(cls.FRAME_TYPE_DATA, payload, reserved_byte)

    @classmethod
    def _build_frame(cls, frame_type: int, payload: list[int], reserved_byte: int) -> bytes:
        frame_data = bytearray()
        frame_data.extend(cls.FRAME_HEADER)
        frame_data.append(cls.FRAME_LENGTH)
        frame_data.append(reserved_byte)
        frame_data.append(frame_type)
        frame_data.extend(payload)
        checksum = cls._calculate_checksum(frame_data)
        frame_data.extend(checksum)
        return bytes(frame_data)

    @classmethod
    def _calculate_checksum(cls, data: bytearray) -> bytes:
        if len(data) != cls.FRAME_DATA_SIZE:
            raise ValueError(f"校验和计算错误：数据长度应为{cls.FRAME_DATA_SIZE}字节，实际为{len(data)}字节")
        checksum_value = sum(data) & 0xFFFF
        return checksum_value.to_bytes(2, "big")

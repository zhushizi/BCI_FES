from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DeviceHeartbeatStatus:
    """下位机心跳状态载体。"""

    side: str
    frame_flag: int
    thigh_connected: bool
    calf_connected: bool
    trigger_connected: bool


class HeartbeatFrame:
    """心跳协议帧工具类：负责构建/校验/解析"""

    FRAME_HEADER = bytes([0x55, 0xAA])  # 帧头
    FRAME_LENGTH = 0x0D  # 帧长度（13字节，定长）
    FRAME_SIZE = 13
    FRAME_DATA_SIZE = 11  # 不含校验和的前11字节

    SIDE_LEFT = 0xE0
    SIDE_RIGHT = 0xF0
    SIDE_MAP = {
        SIDE_LEFT: "left",
        SIDE_RIGHT: "right",
    }

    HEARTBEAT_FLAG_FROM_DEVICE = 0xFB
    THIGH_CONNECTED = 0xA1
    THIGH_DISCONNECTED = 0xA0
    CALF_CONNECTED = 0xB1
    CALF_DISCONNECTED = 0xB0
    TRIGGER_CONNECTED = 0xC1
    TRIGGER_DISCONNECTED = 0xC0
    RESERVED_FILL = 0xFF
    SET_TIME_COMMAND = 0xCE

    @classmethod
    def is_heartbeat_request(cls, data: bytes, logger: logging.Logger) -> bool:
        """判断数据是否为下位机心跳包（并校验校验和）"""
        if len(data) < cls.FRAME_SIZE:
            return False
        if data[0:2] != cls.FRAME_HEADER:
            return False
        if data[2] != cls.FRAME_LENGTH:
            return False
        if data[3] not in cls.SIDE_MAP:
            return False
        if data[4] != cls.HEARTBEAT_FLAG_FROM_DEVICE:
            return False
        if data[5] not in (cls.THIGH_CONNECTED, cls.THIGH_DISCONNECTED):
            return False
        if data[6] not in (cls.CALF_CONNECTED, cls.CALF_DISCONNECTED):
            return False
        if data[7] not in (cls.TRIGGER_CONNECTED, cls.TRIGGER_DISCONNECTED):
            return False
        if data[8:11] != bytes([cls.RESERVED_FILL, cls.RESERVED_FILL, cls.RESERVED_FILL]):
            return False

        frame_data = bytearray(data[0:cls.FRAME_DATA_SIZE])
        expected_checksum = cls.calculate_crc16(frame_data)
        actual_checksum = data[cls.FRAME_DATA_SIZE:cls.FRAME_SIZE]
        if expected_checksum != actual_checksum:
            logger.warning(f"心跳包校验和错误: 期望={expected_checksum.hex()}, 实际={actual_checksum.hex()}")
            return False

        return True

    @classmethod
    def parse_heartbeat_status(cls, data: bytes, logger: logging.Logger) -> DeviceHeartbeatStatus | None:
        """解析下位机心跳状态，失败时返回 None。"""
        if not cls.is_heartbeat_request(data, logger):
            return None
        return DeviceHeartbeatStatus(
            side=cls.SIDE_MAP.get(data[3], "unknown"),
            frame_flag=data[4],
            thigh_connected=data[5] == cls.THIGH_CONNECTED,
            calf_connected=data[6] == cls.CALF_CONNECTED,
            trigger_connected=data[7] == cls.TRIGGER_CONNECTED,
        )

    @classmethod
    def build_heartbeat_response(cls, now: datetime | None = None) -> bytes:
        """构建上位机校时响应包（0xCE + yy MM dd HH mm ss + 0x00 + CRC16）。"""
        current = now or datetime.now()
        frame_data = bytearray()
        frame_data.extend(cls.FRAME_HEADER)                      # 字节1-2: 帧头
        frame_data.append(cls.FRAME_LENGTH)                      # 字节3: 帧长度
        frame_data.append(cls.SET_TIME_COMMAND)                  # 字节4: 帧类型（校时）
        frame_data.append(int(current.strftime("%y")))           # 字节5: 年(yy)
        frame_data.append(int(current.strftime("%m")))           # 字节6: 月
        frame_data.append(int(current.strftime("%d")))           # 字节7: 日
        frame_data.append(int(current.strftime("%H")))           # 字节8: 时
        frame_data.append(int(current.strftime("%M")))           # 字节9: 分
        frame_data.append(int(current.strftime("%S")))           # 字节10: 秒
        frame_data.append(0x00)                                  # 字节11: 保留

        checksum = cls.calculate_crc16(frame_data)
        frame_data.extend(checksum)                              # 字节12-13: CRC16(低位在前)
        return bytes(frame_data)

    @classmethod
    def calculate_crc16(cls, data: bytearray | bytes) -> bytes:
        """计算 CRC16(Modbus, 0xA001)，返回 [low, high]。"""
        if len(data) != cls.FRAME_DATA_SIZE:
            raise ValueError(
                f"CRC16 计算错误：数据长度应为{cls.FRAME_DATA_SIZE}字节，实际为{len(data)}字节"
            )
        crc = 0xFFFF
        for value in data:
            crc ^= value
            for _ in range(8):
                bit = crc & 0x0001
                crc = (crc >> 1) & 0x7FFF
                if bit == 1:
                    crc ^= 0xA001
                crc &= 0xFFFF
        return bytes([(crc & 0xFF), (crc >> 8) & 0xFF])

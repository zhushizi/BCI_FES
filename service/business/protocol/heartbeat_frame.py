from __future__ import annotations

import logging


class HeartbeatFrame:
    """心跳协议帧工具类：负责构建/校验/解析"""

    FRAME_HEADER = bytes([0x55, 0xAA])  # 帧头
    FRAME_LENGTH = 0x0D  # 帧长度（13字节，定长）
    RESERVED_BYTE = 0x00  # 保留字节
    FRAME_SIZE = 13
    FRAME_DATA_SIZE = 11  # 不含校验和的前11字节
    RESERVED_COUNT = 5

    HEARTBEAT_MODE = 0xAB  # 心跳模式标识
    HEARTBEAT_FROM_DEVICE = 0x01  # 下位机->上位机
    HEARTBEAT_TO_DEVICE = 0x02    # 上位机->下位机

    @classmethod
    def is_heartbeat_request(cls, data: bytes, logger: logging.Logger) -> bool:
        """判断数据是否为下位机心跳包（并校验校验和）"""
        if len(data) < cls.FRAME_SIZE:
            return False
        if data[0:2] != cls.FRAME_HEADER:
            return False
        if data[2] != cls.FRAME_LENGTH:
            return False
        if data[4] != cls.HEARTBEAT_MODE:
            return False
        if data[5] != cls.HEARTBEAT_FROM_DEVICE:
            return False

        frame_data = bytearray(data[0:cls.FRAME_DATA_SIZE])
        expected_checksum = cls.calculate_checksum(frame_data)
        actual_checksum = data[cls.FRAME_DATA_SIZE:cls.FRAME_SIZE]
        if expected_checksum != actual_checksum:
            logger.warning(f"心跳包校验和错误: 期望={expected_checksum.hex()}, 实际={actual_checksum.hex()}")
            return False

        return True

    @classmethod
    def build_heartbeat_response(cls) -> bytes:
        """构建上位机心跳响应包"""
        frame_data = bytearray()
        frame_data.extend(cls.FRAME_HEADER)                 # 字节1-2: 帧头
        frame_data.append(cls.FRAME_LENGTH)                 # 字节3: 帧长度
        frame_data.append(cls.RESERVED_BYTE)                # 字节4: 保留
        frame_data.append(cls.HEARTBEAT_MODE)               # 字节5: 心跳模式
        frame_data.append(cls.HEARTBEAT_TO_DEVICE)          # 字节6: 上位机->下位机
        frame_data.extend([cls.RESERVED_BYTE] * cls.RESERVED_COUNT)  # 字节7-11: 保留

        checksum = cls.calculate_checksum(frame_data)
        frame_data.extend(checksum)
        return bytes(frame_data)

    @classmethod
    def calculate_checksum(cls, data: bytearray) -> bytes:
        """计算校验和（前11字节的和，返回2字节）"""
        if len(data) != cls.FRAME_DATA_SIZE:
            raise ValueError(
                f"校验和计算错误：数据长度应为{cls.FRAME_DATA_SIZE}字节，实际为{len(data)}字节"
            )
        checksum_value = sum(data) & 0xFFFF
        return checksum_value.to_bytes(2, "big")

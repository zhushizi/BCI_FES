from __future__ import annotations

class StimFrame:
    FRAME_HEADER = bytes([0x55, 0xAA])  # 帧头
    FRAME_LENGTH = 0x0D  # 帧长度（13字节，定长）
    RESERVED_BYTE = 0x00  # 默认保留字节
    FRAME_DATA_SIZE = 11  # 不含校验和的前11字节

    DEVICE_LEFT_THIGH = 0xEA
    DEVICE_LEFT_CALF = 0xEB
    DEVICE_RIGHT_THIGH = 0xFA
    DEVICE_RIGHT_CALF = 0xFB

    FRAME_TYPE_BASIC = 0x01
    FRAME_TYPE_ADVANCED = 0x02

    WAVEFORM_SYMMETRIC = 0x01
    WAVEFORM_ASYMMETRIC = 0x02
    TREATMENT_MODE = 0x01
    CURRENT_MODE_START = 0xEF
    CURRENT_MODE_STOP = 0xFF

    @classmethod
    def build_basic_params(cls, device: int, waveform: int, pulse_width: int, frequency: int) -> bytes:
        payload = [
            cls._byte(waveform),
            cls._byte(pulse_width),
            cls._byte(frequency),
            cls.RESERVED_BYTE,
            cls.RESERVED_BYTE,
            cls.RESERVED_BYTE,
        ]
        return cls._build_frame(device, cls.FRAME_TYPE_BASIC, payload)

    @classmethod
    def build_advanced_params(
        cls,
        device: int,
        current: int,
        stim_time: int,
        rise_time: int,
        down_time: int,
        treatment_mode: int = TREATMENT_MODE,
    ) -> bytes:
        payload = [
            cls._byte(treatment_mode),
            cls._byte(current),
            cls._byte(stim_time),
            cls.RESERVED_BYTE,
            cls._byte(rise_time),
            cls._byte(down_time),
        ]
        return cls._build_frame(device, cls.FRAME_TYPE_ADVANCED, payload)

    @classmethod
    def _build_frame(cls, device: int, frame_type: int, payload: list[int]) -> bytes:
        frame_data = bytearray()
        frame_data.extend(cls.FRAME_HEADER)
        frame_data.append(cls.FRAME_LENGTH)
        frame_data.append(cls._byte(device))
        frame_data.append(cls._byte(frame_type))
        frame_data.extend(payload)
        checksum = cls._calculate_checksum(frame_data)
        frame_data.extend(checksum)
        return bytes(frame_data)

    @staticmethod
    def _byte(value: int) -> int:
        return int(value) & 0xFF

    @classmethod
    def _calculate_checksum(cls, data: bytearray) -> bytes:
        if len(data) != cls.FRAME_DATA_SIZE:
            raise ValueError(f"校验和计算错误：数据长度应为{cls.FRAME_DATA_SIZE}字节，实际为{len(data)}字节")
        checksum_value = sum(data) & 0xFFFF
        return checksum_value.to_bytes(2, "big")
